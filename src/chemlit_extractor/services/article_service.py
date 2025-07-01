"""Unified ArticleService with dependency injection and transaction management."""

import logging
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from chemlit_extractor.database import ArticleCRUD, get_db_session
from chemlit_extractor.models.schemas import Article, ArticleCreate, AuthorCreate
from chemlit_extractor.services.crossref import CrossRefService
from chemlit_extractor.services.file_downloader import FileDownloader
from chemlit_extractor.services.file_management import FileManagementService

logger = logging.getLogger(__name__)


from collections.abc import Generator
from fastapi import Depends
from chemlit_extractor.database import get_db


def get_article_service_dependency(
    db: Session = Depends(get_db),
) -> Generator[ArticleService, None, None]:
    """
    FastAPI dependency for ArticleService with proper cleanup.

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
        # Don't close the database session - FastAPI manages it
        # Only close other services
        if hasattr(service.crossref_service, "close"):
            service.crossref_service.close()
        if hasattr(service.file_downloader, "close"):
            service.file_downloader.close()
        if hasattr(service.file_manager, "close"):
            service.file_manager.close()


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

    def register_article(
        self,
        doi: str,
        fetch_metadata: bool = True,
        download_files: bool = False,
        file_urls: FileUrls | None = None,
        article_data: ArticleCreate | None = None,
        force_refresh: bool = False,
    ) -> ArticleRegistrationResult:
        """
        Register an article with complete workflow management.

        Args:
            doi: Article DOI.
            fetch_metadata: Whether to fetch metadata from CrossRef.
            download_files: Whether to download associated files.
            file_urls: URLs for file downloads.
            article_data: Direct article data (used if fetch_metadata=False).
            force_refresh: Whether to refresh existing articles.

        Returns:
            ArticleRegistrationResult with operation status and details.
        """
        warnings = []

        try:
            # Clean and validate DOI
            clean_doi = self._clean_doi(doi)
            if not clean_doi:
                return ArticleRegistrationResult(
                    status=RegistrationStatus.ERROR,
                    source="validation",
                    message="Invalid DOI format",
                    error_details="DOI must start with '10.'",
                )

            # Begin transaction
            transaction = self.db.begin()

            try:
                # Check if article already exists
                existing_article = ArticleCRUD.get_by_doi(self.db, clean_doi)

                if existing_article and not force_refresh:
                    # Article exists - handle files if requested
                    download_status = None
                    if download_files:
                        download_status = self._handle_file_downloads(
                            clean_doi, file_urls
                        )

                    return ArticleRegistrationResult(
                        status=RegistrationStatus.ALREADY_EXISTS,
                        operation_type=OperationType.EXISTED,
                        article=existing_article,
                        source="database",
                        message=f"Article with DOI '{clean_doi}' already exists",
                        download_status=download_status,
                        warnings=["Article already exists in database"],
                    )

                # Determine article data source and fetch if needed
                if fetch_metadata:
                    result = self._fetch_from_crossref(clean_doi)
                    if not result.success:
                        transaction.rollback()
                        return ArticleRegistrationResult(
                            status=RegistrationStatus.NOT_FOUND,
                            source="crossref",
                            message=result.message,
                            error_details=result.error_details,
                        )

                    article_create_data = result.article_data
                    authors_data = result.authors_data
                    source = "crossref"
                    operation_type = OperationType.FETCHED

                elif article_data:
                    article_create_data = article_data
                    authors_data = []
                    source = "direct"
                    operation_type = OperationType.CREATED

                else:
                    transaction.rollback()
                    return ArticleRegistrationResult(
                        status=RegistrationStatus.ERROR,
                        source="validation",
                        message="Either fetch_metadata must be True or article_data must be provided",
                        error_details="No data source specified",
                    )

                # Create or update article
                if existing_article and force_refresh:
                    # Update existing article
                    article = self._update_article(
                        existing_article, article_create_data, authors_data
                    )
                    operation_type = OperationType.UPDATED
                else:
                    # Create new article
                    article = ArticleCRUD.create(
                        self.db, article_create_data, authors_data
                    )

                # Commit the database transaction
                transaction.commit()
                logger.info(f"Successfully registered article: {clean_doi}")

                # Handle file downloads (outside transaction)
                download_status = None
                if download_files:
                    download_status = self._handle_file_downloads(clean_doi, file_urls)

                # Build success message
                message = self._build_success_message(operation_type, download_status)

                return ArticleRegistrationResult(
                    status=RegistrationStatus.SUCCESS,
                    operation_type=operation_type,
                    article=article,
                    source=source,
                    message=message,
                    download_status=download_status,
                    warnings=warnings,
                )

            except Exception as e:
                transaction.rollback()
                logger.error(f"Transaction failed for DOI {clean_doi}: {e}")
                raise

        except Exception as e:
            logger.error(f"Article registration failed for {doi}: {e}")
            return ArticleRegistrationResult(
                status=RegistrationStatus.ERROR,
                source="service",
                message=f"Registration failed: {str(e)}",
                error_details=str(e),
                warnings=warnings,
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


def get_article_service_for_endpoint() -> ArticleService:
    """
    Get ArticleService for FastAPI endpoint dependency injection.

    Returns:
        ArticleService instance that will be automatically closed.
    """
    service = ArticleService()
    try:
        yield service
    finally:
        service.close()
