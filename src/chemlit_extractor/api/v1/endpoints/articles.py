"""Unified article creation endpoint with consolidated functionality."""

import warnings
from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
)
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from chemlit_extractor.database import ArticleCRUD, CompoundCRUD, get_db
from chemlit_extractor.models.schemas import (
    Article,
    ArticleCreate,
    ArticleCreateWithFiles,
    ArticleSearchQuery,
    ArticleSearchResponse,
    ArticleUpdate,
)
from chemlit_extractor.services.crossref import CrossRefService

router = APIRouter()


# ==================== New Unified Schemas ====================


class FileUrls(BaseModel):
    """File URLs for downloading."""

    pdf_url: str | None = Field(default=None, description="URL to PDF file")
    html_url: str | None = Field(default=None, description="URL to HTML file")
    supplementary_urls: list[str] = Field(
        default_factory=list, description="URLs to supplementary files"
    )


class UnifiedArticleCreateRequest(BaseModel):
    """Unified request schema for article creation."""

    # Option 1: Direct article data
    article_data: ArticleCreate | None = Field(
        default=None, description="Direct article data for creation"
    )

    # Option 2: Fetch from CrossRef
    doi: str | None = Field(
        default=None,
        min_length=5,
        max_length=255,
        description="DOI to fetch from CrossRef (required if fetch_from_crossref=True)",
    )
    fetch_from_crossref: bool = Field(
        default=False, description="Whether to fetch article data from CrossRef"
    )

    # Option 3: File downloads
    download_files: bool = Field(
        default=False, description="Whether to trigger file downloads"
    )
    file_urls: FileUrls | None = Field(
        default=None, description="URLs for files to download"
    )

    @field_validator("doi")
    @classmethod
    def validate_doi(cls, v: str | None) -> str | None:
        """Validate and normalize DOI format."""
        if v is None:
            return None
        doi = v.strip().lower()
        if not doi.startswith("10."):
            raise ValueError("DOI must start with '10.'")
        return doi

    @field_validator("article_data", mode="after")
    @classmethod
    def validate_request(cls, v, values):
        """Validate that request has either article_data or doi."""
        fetch_from_crossref = values.data.get("fetch_from_crossref", False)
        doi = values.data.get("doi")

        if fetch_from_crossref and not doi:
            raise ValueError("DOI is required when fetch_from_crossref is True")

        if not fetch_from_crossref and not v:
            raise ValueError(
                "article_data is required when fetch_from_crossref is False"
            )

        return v


class DownloadStatus(BaseModel):
    """Status of file downloads."""

    triggered: bool = Field(default=False)
    file_count: int = Field(default=0)
    files: dict[str, str] = Field(
        default_factory=dict, description="Mapping of file types to download status"
    )
    message: str | None = Field(default=None)


class UnifiedArticleCreateResponse(BaseModel):
    """Unified response for article creation."""

    success: bool
    article: Article | None = None
    message: str
    operation_type: str = Field(
        description="Type of operation performed: created|fetched|existed"
    )
    source: str = Field(description="Data source: direct|crossref")
    download_status: DownloadStatus | None = None
    warnings: list[str] = Field(default_factory=list)


# ==================== Unified Endpoint ====================


@router.post("/", response_model=UnifiedArticleCreateResponse, status_code=201)
def create_article_unified(
    request: UnifiedArticleCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> UnifiedArticleCreateResponse:
    """
    Unified endpoint for article creation with multiple options.

    This endpoint consolidates all article creation functionality:
    - Direct creation with provided data
    - Fetching from CrossRef by DOI
    - Optional file downloads

    Args:
        request: Unified request with creation options.
        background_tasks: FastAPI background tasks for file downloads.
        db: Database session.

    Returns:
        Unified response with article and operation status.

    Raises:
        400: If article already exists or validation fails.
        404: If DOI not found in CrossRef.
        502: If CrossRef API is unavailable.
    """
    warnings = []
    article = None
    operation_type = "created"
    source = "direct"
    download_status = None

    try:
        # Determine article data source
        if request.fetch_from_crossref:
            # Fetch from CrossRef
            if not request.doi:
                raise HTTPException(
                    status_code=400,
                    detail="DOI is required when fetch_from_crossref is True",
                )

            # Check if article already exists
            existing_article = ArticleCRUD.get_by_doi(db, request.doi)
            if existing_article:
                article = existing_article
                operation_type = "existed"
                warnings.append(f"Article with DOI '{request.doi}' already exists")

                # Allow file downloads for existing articles
                if not request.download_files:
                    return UnifiedArticleCreateResponse(
                        success=True,
                        article=article,
                        message=f"Article with DOI '{request.doi}' already exists",
                        operation_type=operation_type,
                        source="database",
                        warnings=warnings,
                    )
            else:
                # Fetch from CrossRef
                service = CrossRefService()
                try:
                    result = service.fetch_and_convert_article(request.doi)
                    if not result:
                        raise HTTPException(
                            status_code=404,
                            detail=f"Article with DOI '{request.doi}' not found in CrossRef",
                        )

                    article_data, authors_data = result
                    source = "crossref"
                    operation_type = "fetched"

                    # Create article with authors
                    try:
                        article = ArticleCRUD.create(db, article_data, authors_data)
                    except ValueError as e:
                        raise HTTPException(status_code=400, detail=str(e))

                except HTTPException:
                    raise
                except Exception as e:
                    raise HTTPException(
                        status_code=502,
                        detail=f"Failed to fetch from CrossRef: {str(e)}",
                    )
                finally:
                    service.close()

        else:
            # Direct creation with provided data
            if not request.article_data:
                raise HTTPException(
                    status_code=400,
                    detail="article_data is required when fetch_from_crossref is False",
                )

            # Check if article already exists
            existing_article = ArticleCRUD.get_by_doi(db, request.article_data.doi)
            if existing_article:
                raise HTTPException(
                    status_code=400,
                    detail=f"Article with DOI '{request.article_data.doi}' already exists",
                )

            try:
                article = ArticleCRUD.create(db, request.article_data)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

        # Handle file downloads if requested
        if request.download_files and article:
            download_status = _handle_file_downloads(
                article.doi,
                request.file_urls,
                background_tasks,
            )

        # Construct success message
        message_parts = []
        if operation_type == "created":
            message_parts.append("Article created successfully")
        elif operation_type == "fetched":
            message_parts.append("Article fetched from CrossRef and created")
        elif operation_type == "existed":
            message_parts.append("Article already exists")

        if download_status and download_status.triggered:
            message_parts.append(
                f"{download_status.file_count} file downloads triggered"
            )

        return UnifiedArticleCreateResponse(
            success=True,
            article=article,
            message=". ".join(message_parts),
            operation_type=operation_type,
            source=source,
            download_status=download_status,
            warnings=warnings,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error during article creation: {str(e)}",
        )


def _handle_file_downloads(
    doi: str,
    file_urls: FileUrls | None,
    background_tasks: BackgroundTasks,
) -> DownloadStatus:
    """
    Handle file downloads for an article.

    Args:
        doi: Article DOI.
        file_urls: URLs for files to download.
        background_tasks: FastAPI background tasks.

    Returns:
        Download status information.
    """
    if not file_urls:
        return DownloadStatus(
            triggered=False, message="No file URLs provided for download"
        )

    # Count files to download
    files_to_download = {}
    file_count = 0

    if file_urls.pdf_url:
        files_to_download["pdf"] = file_urls.pdf_url
        file_count += 1

    if file_urls.html_url:
        files_to_download["html"] = file_urls.html_url
        file_count += 1

    if file_urls.supplementary_urls:
        files_to_download["supplementary"] = (
            f"{len(file_urls.supplementary_urls)} files"
        )
        file_count += len(file_urls.supplementary_urls)

    if file_count == 0:
        return DownloadStatus(
            triggered=False, message="No file URLs provided for download"
        )

    # Trigger background downloads
    background_tasks.add_task(
        _download_files_for_article,
        doi,
        file_urls.pdf_url,
        file_urls.html_url,
        file_urls.supplementary_urls,
    )

    return DownloadStatus(
        triggered=True,
        file_count=file_count,
        files=files_to_download,
        message=f"Download started for {file_count} files",
    )


# ==================== Deprecated Endpoints (Backward Compatibility) ====================


@router.post("/from-doi", response_model=Article, status_code=201, deprecated=True)
def create_article_from_doi(
    doi: str = Query(..., description="DOI to fetch from CrossRef"),
    db: Session = Depends(get_db),
) -> Article:
    """
    DEPRECATED: Use POST /api/v1/articles/ with fetch_from_crossref=true instead.

    Create an article by fetching metadata from CrossRef API.
    """
    warnings.warn(
        "This endpoint is deprecated. Use POST /api/v1/articles/ with fetch_from_crossref=true",
        DeprecationWarning,
        stacklevel=2,
    )

    # Call unified endpoint
    request = UnifiedArticleCreateRequest(
        doi=doi,
        fetch_from_crossref=True,
        download_files=False,
    )

    response = create_article_unified(
        request=request,
        background_tasks=BackgroundTasks(),
        db=db,
    )

    if not response.success or not response.article:
        raise HTTPException(status_code=400, detail=response.message)

    return response.article


@router.post(
    "/from-doi-with-files", response_model=Article, status_code=201, deprecated=True
)
def create_article_from_doi_with_files(
    request: ArticleCreateWithFiles,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Article:
    """
    DEPRECATED: Use POST /api/v1/articles/ with fetch_from_crossref=true and download_files=true.

    Create an article from CrossRef and optionally download files.
    """
    warnings.warn(
        "This endpoint is deprecated. Use POST /api/v1/articles/ with appropriate options",
        DeprecationWarning,
        stacklevel=2,
    )

    # Convert to unified request
    unified_request = UnifiedArticleCreateRequest(
        doi=request.doi,
        fetch_from_crossref=True,
        download_files=request.download_files,
        file_urls=(
            FileUrls(
                pdf_url=request.pdf_url,
                html_url=request.html_url,
                supplementary_urls=request.supplementary_urls,
            )
            if request.download_files
            else None
        ),
    )

    response = create_article_unified(
        request=unified_request,
        background_tasks=background_tasks,
        db=db,
    )

    if not response.success or not response.article:
        raise HTTPException(status_code=400, detail=response.message)

    return response.article


@router.post("/{doi:path}/trigger-downloads", deprecated=True)
def trigger_article_downloads(
    doi: str,
    background_tasks: BackgroundTasks,
    pdf_url: str | None = Query(default=None, description="URL to PDF file"),
    html_url: str | None = Query(default=None, description="URL to HTML file"),
    supplementary_urls: list[str] = Query(
        default_factory=list, description="URLs to supplementary files"
    ),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    DEPRECATED: Use POST /api/v1/articles/ with the existing DOI and download_files=true.

    Trigger file downloads for an existing article.
    """
    warnings.warn(
        "This endpoint is deprecated. Use POST /api/v1/articles/ with download_files=true",
        DeprecationWarning,
        stacklevel=2,
    )

    # Verify article exists
    article = ArticleCRUD.get_by_doi(db, doi)
    if not article:
        raise HTTPException(
            status_code=404, detail=f"Article with DOI '{doi}' not found"
        )

    # Use unified endpoint for consistency
    file_urls = FileUrls(
        pdf_url=pdf_url,
        html_url=html_url,
        supplementary_urls=supplementary_urls,
    )

    download_status = _handle_file_downloads(doi, file_urls, background_tasks)

    if not download_status.triggered:
        raise HTTPException(
            status_code=400, detail="At least one download URL must be provided"
        )

    return {
        "doi": doi,
        "download_triggered": download_status.triggered,
        "download_count": download_status.file_count,
        "message": download_status.message,
    }


# ==================== Keep existing endpoints below ====================


@router.get("/", response_model=ArticleSearchResponse)
def search_articles(
    doi: str | None = Query(None, description="DOI to search for"),
    title: str | None = Query(None, description="Title keywords to search for"),
    author: str | None = Query(None, description="Author name to search for"),
    journal: str | None = Query(None, description="Journal name to search for"),
    year: int | None = Query(None, description="Publication year"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: Session = Depends(get_db),
) -> ArticleSearchResponse:
    """Search articles in the database."""
    search_query = ArticleSearchQuery(
        doi=doi,
        title=title,
        author=author,
        journal=journal,
        year=year,
        limit=limit,
        offset=offset,
    )

    articles, total_count = ArticleCRUD.search(db, search_query)

    return ArticleSearchResponse(
        articles=articles,
        total_count=total_count,
        limit=limit,
        offset=offset,
    )


@router.get("/{doi:path}/compounds")
def get_article_compounds(
    doi: str,
    db: Session = Depends(get_db),
):
    """Get all compounds for a specific article."""
    article = ArticleCRUD.get_by_doi(db, doi)
    if not article:
        raise HTTPException(
            status_code=404, detail=f"Article with DOI '{doi}' not found"
        )

    compounds = CompoundCRUD.get_by_article(db, doi)
    return compounds


@router.get("/{doi:path}", response_model=Article)
def get_article(
    doi: str,
    db: Session = Depends(get_db),
) -> Article:
    """Get a specific article by DOI."""
    article = ArticleCRUD.get_by_doi(db, doi)
    if not article:
        raise HTTPException(
            status_code=404, detail=f"Article with DOI '{doi}' not found"
        )
    return article


@router.put("/{doi:path}", response_model=Article)
def update_article(
    doi: str,
    article_update: ArticleUpdate,
    db: Session = Depends(get_db),
) -> Article:
    """Update an existing article."""
    updated_article = ArticleCRUD.update(db, doi, article_update)
    if not updated_article:
        raise HTTPException(
            status_code=404, detail=f"Article with DOI '{doi}' not found"
        )
    return updated_article


@router.delete("/{doi:path}", status_code=204)
def delete_article(
    doi: str,
    db: Session = Depends(get_db),
) -> None:
    """Delete an article and all associated compounds/properties."""
    success = ArticleCRUD.delete(db, doi)
    if not success:
        raise HTTPException(
            status_code=404, detail=f"Article with DOI '{doi}' not found"
        )


# Helper function from original code
def _download_files_for_article(
    doi: str,
    pdf_url: str | None,
    html_url: str | None,
    supplementary_urls: list[str],
) -> None:
    """Background task for downloading files after article creation."""
    import logging

    logger = logging.getLogger(__name__)

    try:
        from chemlit_extractor.services.file_management import FileManagementService

        with FileManagementService() as file_service:
            results = file_service.download_from_urls(
                doi=doi,
                pdf_url=pdf_url,
                html_url=html_url,
                supplementary_urls=supplementary_urls,
            )

            # Log results
            successful = sum(1 for result in results.values() if result.success)
            failed = len(results) - successful

            logger.info(
                f"File download completed for {doi}: "
                f"{successful} successful, {failed} failed"
            )

            # Log any failures
            for url, result in results.items():
                if not result.success:
                    logger.warning(f"Failed to download {url}: {result.error}")

    except Exception as e:
        logger.error(f"Background download task failed for {doi}: {e}")
