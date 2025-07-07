"""Unified ArticleService with dependency injection and transaction management."""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from enum import Enum
from typing import Any

from fastapi import Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from chemlit_extractor.database import ArticleCRUD, get_db, get_db_session
from chemlit_extractor.models.schemas import (
    Article,
    ArticleCreate,
    AuthorCreate,
    ArticleRegistrationData,
)
from chemlit_extractor.services.crossref import CrossRefService
from chemlit_extractor.services.file_downloader import FileDownloader
from chemlit_extractor.services.file_management import FileManagementService

logger = logging.getLogger(__name__)


class ServiceContainer:
    """Container for managing service lifecycle."""

    def __init__(self):
        self.services = []

    def register(self, service):
        """Register a service for cleanup."""
        self.services.append(service)
        return service

    def close(self):
        """Close all registered services."""
        for service in self.services:
            try:
                if hasattr(service, "close"):
                    service.close()
            except Exception as e:
                logger.warning(f"Error closing service: {e}")


# Global service container
_service_container = ServiceContainer()


def get_service_container() -> ServiceContainer:
    """Get the global service container."""
    return _service_container


@contextmanager
def get_article_service_context(db_session: Session | None = None):
    """
    Context manager for ArticleService.

    Args:
        db_session: Optional database session.

    Yields:
        ArticleService instance.
    """
    service = ArticleService(db_session=db_session)
    try:
        yield service
    finally:
        service.close()


class OperationType(str, Enum):
    """Types of operations performed on articles."""

    CREATED = "created"
    EXISTED = "existed"
    FETCHED = "fetched"
    UPDATED = "updated"


class RegistrationStatus(str, Enum):
    """Registration status outcomes."""

    SUCCESS = "success"
    ERROR = "error"
    ALREADY_EXISTS = "already_exists"
    NOT_FOUND = "not_found"


class FileDownloadStatus(BaseModel):
    """Status of file download operations."""

    attempted: bool = Field(default=False)
    successful_downloads: int = Field(default=0)
    failed_downloads: int = Field(default=0)
    download_method: str | None = Field(default=None)
    results: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = Field(default=None)


class ArticleRegistrationResult(BaseModel):
    """Result of article registration operation."""

    status: RegistrationStatus
    operation_type: OperationType | None = None
    article: Article | None = None
    source: str = Field(description="Data source: direct|crossref|database")
    message: str
    download_status: FileDownloadStatus | None = None
    warnings: list[str] = Field(default_factory=list)
    error_details: str | None = None


class FileUrls(BaseModel):
    """File URLs for downloading."""

    pdf_url: str | None = Field(default=None)
    html_url: str | None = Field(default=None)
    supplementary_urls: list[str] = Field(default_factory=list)


class ArticleService:
    """
    Unified service for article management operations.

    Implements facade pattern to consolidate article registration,
    metadata fetching, and file downloading with proper transaction
    management and dependency injection.
    """

    def __init__(
        self,
        db_session: Session | None = None,
        crossref_service: CrossRefService | None = None,
        file_downloader: FileDownloader | None = None,
        file_manager: FileManagementService | None = None,
    ):
        """
        Initialize ArticleService with dependency injection.

        Args:
            db_session: Database session (will create if None).
            crossref_service: CrossRef service instance.
            file_downloader: File downloader service.
            file_manager: File management service.
        """
        self._own_db_session = db_session is None
        self.db = db_session or get_db_session()
        self.crossref_service = crossref_service or CrossRefService()
        self.file_downloader = file_downloader or FileDownloader()
        self.file_manager = file_manager or FileManagementService()

    def __enter__(self) -> "ArticleService":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit with cleanup."""
        self.close()

    def close(self) -> None:
        """Close all services and database connections."""
        try:
            if hasattr(self.crossref_service, "close"):
                self.crossref_service.close()
            if hasattr(self.file_downloader, "close"):
                self.file_downloader.close()
            if hasattr(self.file_manager, "close"):
                self.file_manager.close()
            if self._own_db_session:
                self.db.close()
        except Exception as e:
            logger.warning(f"Error during service cleanup: {e}")

    def _handle_existing_article(
        self,
        existing_article: Article,
        doi: str,
        download_files: bool,
        file_urls: FileUrls | None,
    ) -> ArticleRegistrationResult:
        """Handle the case where an article already exists."""
        download_status = None
        if download_files:
            download_status = self._handle_file_downloads(doi, file_urls)

        return ArticleRegistrationResult(
            status=RegistrationStatus.ALREADY_EXISTS,
            operation_type=OperationType.EXISTED,
            article=existing_article,
            source="database",
            message=f"Article with DOI '{doi}' already exists",
            download_status=download_status,
            warnings=["Article already exists in database"],
        )

    def register_article_from_doi(
        self,
        doi: str,
        download_files: bool = False,
        file_urls: FileUrls | None = None,
    ) -> ArticleRegistrationResult:
        """
        Register an article by fetching its data from CrossRef.

        This maintains the unity of article and author data throughout
        the process.
        """
        # Clean DOI
        clean_doi = self._clean_doi(doi)
        if not clean_doi:
            return ArticleRegistrationResult(
                status=RegistrationStatus.ERROR,
                source="validation",
                message="Invalid DOI format",
                error_details="DOI must start with '10.'",
            )

        # Check if already exists
        existing = ArticleCRUD.get_by_doi(self.db, clean_doi)
        if existing:
            return self._handle_existing_article(
                existing, clean_doi, download_files, file_urls
            )

        # Fetch from CrossRef - this gets article AND authors together
        fetch_result = self._fetch_from_crossref(clean_doi)
        if not fetch_result.success:
            return ArticleRegistrationResult(
                status=RegistrationStatus.NOT_FOUND,
                source="crossref",
                message=fetch_result.message,
                error_details=fetch_result.error_details,
            )

        # Create the article with its authors as an atomic operation
        try:
            article = ArticleCRUD.create_with_authors(
                self.db, fetch_result.article_data, fetch_result.authors_data
            )

            # Handle file downloads if requested
            download_status = None
            if download_files:
                download_status = self._handle_file_downloads(clean_doi, file_urls)

            return ArticleRegistrationResult(
                status=RegistrationStatus.SUCCESS,
                operation_type=OperationType.FETCHED,
                article=article,
                source="crossref",
                message="Article fetched from CrossRef and registered successfully",
                download_status=download_status,
            )

        except Exception as e:
            logger.error(f"Failed to create article {clean_doi}: {e}")
            return ArticleRegistrationResult(
                status=RegistrationStatus.ERROR,
                source="database",
                message=f"Failed to save article: {str(e)}",
                error_details=str(e),
            )

    def register_article_with_data(
        self,
        registration_data: ArticleRegistrationData,
        download_files: bool = False,
        file_urls: FileUrls | None = None,
    ) -> ArticleRegistrationResult:
        """
        Register an article with directly provided data.

        The registration_data contains both article and author information
        as a unified whole.
        """
        clean_doi = self._clean_doi(registration_data.doi)

        # Check if already exists
        existing = ArticleCRUD.get_by_doi(self.db, clean_doi)
        if existing:
            return self._handle_existing_article(
                existing, clean_doi, download_files, file_urls
            )

        # Convert registration data to separate article and author objects
        # Note: We're doing this conversion here in the service layer,
        # not in the endpoint or form processing
        article_data = ArticleCreate(
            doi=registration_data.doi,
            title=registration_data.title,
            journal=registration_data.journal,
            year=registration_data.year,
            volume=registration_data.volume,
            issue=registration_data.issue,
            pages=registration_data.pages,
            abstract=registration_data.abstract,
            url=registration_data.url,
            publisher=registration_data.publisher,
        )

        # Authors are already validated by the schema
        authors_data = registration_data.authors

        try:
            # Create article and authors together
            article = ArticleCRUD.create_with_authors(
                self.db, article_data, authors_data
            )

            # Handle file downloads if requested
            download_status = None
            if download_files:
                download_status = self._handle_file_downloads(clean_doi, file_urls)

            return ArticleRegistrationResult(
                status=RegistrationStatus.SUCCESS,
                operation_type=OperationType.CREATED,
                article=article,
                source="direct",
                message=f"Article registered successfully with {len(authors_data)} authors",
                download_status=download_status,
            )

        except Exception as e:
            logger.error(f"Failed to create article {clean_doi}: {e}")
            return ArticleRegistrationResult(
                status=RegistrationStatus.ERROR,
                source="database",
                message=f"Failed to save article: {str(e)}",
                error_details=str(e),
            )

    def get_article(self, doi: str) -> Article | None:
        """
        Get an article by DOI.

        Args:
            doi: Article DOI.

        Returns:
            Article instance or None if not found.
        """
        clean_doi = self._clean_doi(doi)
        if not clean_doi:
            return None

        return ArticleCRUD.get_by_doi(self.db, clean_doi)

    def article_exists(self, doi: str) -> bool:
        """
        Check if an article exists in the database.

        Args:
            doi: Article DOI.

        Returns:
            True if article exists.
        """
        return self.get_article(doi) is not None

    def _clean_doi(self, doi: str) -> str | None:
        """Clean and validate DOI format."""
        if not doi:
            return None

        clean_doi = doi.strip().lower()

        # Remove common prefixes
        prefixes = [
            "https://doi.org/",
            "http://doi.org/",
            "https://dx.doi.org/",
            "http://dx.doi.org/",
            "doi:",
        ]

        for prefix in prefixes:
            if clean_doi.startswith(prefix):
                clean_doi = clean_doi[len(prefix) :]
                break

        # Validate DOI format
        if not clean_doi.startswith("10."):
            return None

        return clean_doi

    def _fetch_from_crossref(self, doi: str) -> "CrossRefFetchResult":
        """Fetch article data from CrossRef."""
        try:
            result = self.crossref_service.fetch_and_convert_article(doi)
            if not result:
                return CrossRefFetchResult(
                    success=False,
                    message=f"Article with DOI '{doi}' not found in CrossRef",
                    error_details="CrossRef API returned no data",
                )

            article_data, authors_data = result
            return CrossRefFetchResult(
                success=True,
                article_data=article_data,
                authors_data=authors_data,
                message="Successfully fetched from CrossRef",
            )

        except Exception as e:
            logger.error(f"CrossRef fetch failed for {doi}: {e}")
            return CrossRefFetchResult(
                success=False,
                message=f"Failed to fetch from CrossRef: {str(e)}",
                error_details=str(e),
            )

    def _update_article(
        self,
        existing_article: Article,
        new_data: ArticleCreate,
        authors_data: list[AuthorCreate],
    ) -> Article:
        """Update an existing article with new data."""
        # Update article fields
        for field, value in new_data.model_dump(exclude_unset=True).items():
            if field != "doi":  # Don't update DOI
                setattr(existing_article, field, value)

        # Clear existing authors and add new ones
        existing_article.authors.clear()

        from chemlit_extractor.database import AuthorCRUD

        for author_data in authors_data:
            author = AuthorCRUD.get_or_create(self.db, author_data)
            existing_article.authors.append(author)

        self.db.commit()
        self.db.refresh(existing_article)
        return existing_article

    def _handle_file_downloads(
        self, doi: str, file_urls: FileUrls | None
    ) -> FileDownloadStatus:
        """Handle file downloads for an article."""
        if not file_urls:
            return FileDownloadStatus(
                attempted=False,
                download_method="none",
                error_message="No file URLs provided",
            )

        try:
            # Try automatic discovery first if no URLs provided
            if not any(
                [file_urls.pdf_url, file_urls.html_url, file_urls.supplementary_urls]
            ):
                # Get article for publisher info
                article = self.get_article(doi)
                if article:
                    auto_results = self.file_downloader.auto_discover_and_download(
                        doi=doi,
                        publisher=article.publisher,
                        url=article.url,
                    )

                    successful = sum(
                        1
                        for result in auto_results.values()
                        if isinstance(result, dict) and result.get("success")
                    )

                    return FileDownloadStatus(
                        attempted=True,
                        successful_downloads=successful,
                        failed_downloads=len(auto_results) - successful,
                        download_method="automatic",
                        results=auto_results,
                    )

            # Manual URL downloads
            manual_results = self.file_downloader.download_from_urls(
                doi=doi,
                pdf_url=file_urls.pdf_url,
                html_url=file_urls.html_url,
                supplementary_urls=file_urls.supplementary_urls,
            )

            successful = sum(
                1
                for result in manual_results.values()
                if isinstance(result, dict) and result.get("success")
            )

            return FileDownloadStatus(
                attempted=True,
                successful_downloads=successful,
                failed_downloads=len(manual_results) - successful,
                download_method="manual",
                results=manual_results,
            )

        except Exception as e:
            logger.error(f"File download failed for {doi}: {e}")
            return FileDownloadStatus(
                attempted=True,
                successful_downloads=0,
                failed_downloads=1,
                error_message=str(e),
            )

    def _build_success_message(
        self, operation_type: OperationType, download_status: FileDownloadStatus | None
    ) -> str:
        """Build a success message based on operation results."""
        messages = []

        if operation_type == OperationType.CREATED:
            messages.append("Article created successfully")
        elif operation_type == OperationType.FETCHED:
            messages.append("Article fetched from CrossRef and created")
        elif operation_type == OperationType.UPDATED:
            messages.append("Article updated successfully")
        elif operation_type == OperationType.EXISTED:
            messages.append("Article already exists")

        if download_status and download_status.attempted:
            if download_status.successful_downloads > 0:
                messages.append(
                    f"{download_status.successful_downloads} files downloaded successfully"
                )
            else:
                messages.append("File downloads were attempted but failed")

        return ". ".join(messages)


class CrossRefFetchResult(BaseModel):
    """Result of CrossRef fetch operation."""

    success: bool
    article_data: ArticleCreate | None = None
    authors_data: list[AuthorCreate] = Field(default_factory=list)
    message: str
    error_details: str | None = None


# Dependency injection helpers
def get_article_service(
    db_session: Session | None = None,
) -> ArticleService:
    """
    Get ArticleService instance with dependency injection.

    Args:
        db_session: Optional database session.

    Returns:
        Configured ArticleService instance.
    """
    return ArticleService(db_session=db_session)


def get_article_service_dependency(
    db: Session = Depends(get_db),
) -> Generator[ArticleService, None, None]:
    """
    FastAPI dependency for ArticleService.

    This is the MAIN dependency function to use in FastAPI endpoints.

    Args:
        db: Injected database session from FastAPI.

    Yields:
        ArticleService instance configured with the database session.
    """
    service = ArticleService(db_session=db)
    try:
        yield service
    finally:
        # Only close the services, not the db session (FastAPI manages it)
        if hasattr(service.crossref_service, "close"):
            service.crossref_service.close()
        if hasattr(service.file_downloader, "close"):
            service.file_downloader.close()
        if hasattr(service.file_manager, "close"):
            service.file_manager.close()
