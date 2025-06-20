"""API endpoints for article operations."""

from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
)
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from chemlit_extractor.database import ArticleCRUD, CompoundCRUD, get_db
from chemlit_extractor.models.schemas import (
    Article,
    ArticleCreate,
    ArticleCreateResponse,
    ArticleCreateWithFiles,
    ArticleSearchQuery,
    ArticleSearchResponse,
    ArticleUpdate,
)
from chemlit_extractor.services.crossref import CrossRefService

router = APIRouter()


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
    """
    Search articles in the database.

    Supports searching by DOI, title, author name, journal, and year.
    Results are paginated with configurable limit and offset.
    """
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


@router.post("/", response_model=Article, status_code=201)
def create_article(
    article: ArticleCreate,
    db: Session = Depends(get_db),
) -> Article:
    """
    Create a new article.

    Args:
        article: Article data to create.

    Returns:
        Created article with assigned ID and timestamps.

    Raises:
        400: If article with the same DOI already exists.
    """
    try:
        return ArticleCRUD.create(db, article)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/from-doi", response_model=Article, status_code=201)
def create_article_from_doi(
    doi: str = Query(..., description="DOI to fetch from CrossRef"),
    db: Session = Depends(get_db),
) -> Article:
    """
    Create an article by fetching metadata from CrossRef API.

    This is the main workflow endpoint for adding new articles.
    It fetches metadata from CrossRef and creates the article with authors.

    Args:
        doi: DOI to fetch from CrossRef.

    Returns:
        Created article with fetched metadata and authors.

    Raises:
        400: If DOI is invalid or article already exists.
        404: If DOI not found in CrossRef.
        502: If CrossRef API is unavailable.
    """
    # Check if article already exists
    existing_article = ArticleCRUD.get_by_doi(db, doi)
    if existing_article:
        raise HTTPException(
            status_code=400, detail=f"Article with DOI '{doi}' already exists"
        )

    # Fetch from CrossRef
    service = CrossRefService()
    try:
        result = service.fetch_and_convert_article(doi)
        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Article with DOI '{doi}' not found in CrossRef",
            )

        article_data, authors_data = result

        # Create article with authors
        try:
            return ArticleCRUD.create(db, article_data, authors_data)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"Failed to fetch from CrossRef: {str(e)}"
        )
    finally:
        service.close()


@router.post("/{doi:path}/trigger-downloads")
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
    Trigger file downloads for an existing article.

    Convenience endpoint to download files for articles that were
    registered without file URLs.

    Args:
        doi: Article DOI.
        pdf_url: Optional PDF URL.
        html_url: Optional HTML URL.
        supplementary_urls: Optional list of supplementary file URLs.
        background_tasks: FastAPI background tasks.
        db: Database session.

    Returns:
        Download trigger status.

    Raises:
        404: If article not found.
        400: If no URLs provided.
    """
    # Verify article exists
    article = ArticleCRUD.get_by_doi(db, doi)
    if not article:
        raise HTTPException(
            status_code=404, detail=f"Article with DOI '{doi}' not found"
        )

    # Check if any URLs provided
    urls_provided = bool(pdf_url or html_url or supplementary_urls)

    if not urls_provided:
        raise HTTPException(
            status_code=400, detail="At least one download URL must be provided"
        )

    # Count downloads
    download_count = 0
    if pdf_url:
        download_count += 1
    if html_url:
        download_count += 1
    download_count += len(supplementary_urls)

    # Trigger background downloads
    background_tasks.add_task(
        _download_files_for_article,
        doi,
        pdf_url,
        html_url,
        supplementary_urls,
    )

    return {
        "doi": doi,
        "download_triggered": True,
        "download_count": download_count,
        "message": f"Download started for {download_count} files",
    }


def _download_files_for_article(
    doi: str,
    pdf_url: str | None,
    html_url: str | None,
    supplementary_urls: list[str],
) -> None:
    """
    Background task for downloading files after article creation.

    Args:
        doi: Article DOI.
        pdf_url: Optional PDF URL.
        html_url: Optional HTML URL.
        supplementary_urls: List of supplementary file URLs.
    """
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


# IMPORTANT: Specific routes (like /compounds) must come BEFORE general {doi:path} routes
@router.get("/{doi:path}/compounds")
def get_article_compounds(
    doi: str,
    db: Session = Depends(get_db),
):
    """
    Get all compounds for a specific article.

    Args:
        doi: DOI of the article.

    Returns:
        List of compounds associated with the article.

    Raises:
        404: If article with the given DOI is not found.
    """
    # First check if article exists
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
    """
    Get a specific article by DOI.

    Args:
        doi: The DOI of the article to retrieve.

    Returns:
        Article details including associated authors.

    Raises:
        404: If article with the given DOI is not found.
    """
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
    """
    Update an existing article.

    Args:
        doi: DOI of the article to update.
        article_update: Updated article data.

    Returns:
        Updated article.

    Raises:
        404: If article with the given DOI is not found.
    """
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
    """
    Delete an article and all associated compounds/properties.

    This will cascade delete all compounds and their properties.

    Args:
        doi: DOI of the article to delete.

    Raises:
        404: If article with the given DOI is not found.
    """
    success = ArticleCRUD.delete(db, doi)
    if not success:
        raise HTTPException(
            status_code=404, detail=f"Article with DOI '{doi}' not found"
        )


@router.post(
    "/from-doi-with-files", response_model=ArticleCreateResponse, status_code=201
)
def create_article_from_doi_with_files(
    request: ArticleCreateWithFiles,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ArticleCreateResponse:
    """
    Create an article from CrossRef and optionally download files.

    This enhanced endpoint combines article registration with file downloads.
    It fetches metadata from CrossRef, creates the article, and optionally
    triggers background downloads of provided file URLs.

    Args:
        request: Article creation request with optional file URLs.
        background_tasks: FastAPI background tasks for file downloads.
        db: Database session.

    Returns:
        Created article with download status information.

    Raises:
        400: If DOI is invalid or article already exists.
        404: If DOI not found in CrossRef.
        502: If CrossRef API is unavailable.
    """
    # Check if article already exists
    existing_article = ArticleCRUD.get_by_doi(db, request.doi)
    if existing_article:
        raise HTTPException(
            status_code=400, detail=f"Article with DOI '{request.doi}' already exists"
        )

    # Fetch from CrossRef and create article
    service = CrossRefService()
    try:
        result = service.fetch_and_convert_article(request.doi)
        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Article with DOI '{request.doi}' not found in CrossRef",
            )

        article_data, authors_data = result

        # Create article with authors
        try:
            article = ArticleCRUD.create(db, article_data, authors_data)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Handle file downloads if requested
        download_triggered = False
        download_count = 0
        download_message = None

        if request.download_files:
            # Count available URLs
            urls_available = []
            if request.pdf_url:
                urls_available.append("PDF")
                download_count += 1
            if request.html_url:
                urls_available.append("HTML")
                download_count += 1
            if request.supplementary_urls:
                urls_available.append(
                    f"{len(request.supplementary_urls)} supplementary files"
                )
                download_count += len(request.supplementary_urls)

            if download_count > 0:
                # Trigger background downloads
                background_tasks.add_task(
                    _download_files_for_article,
                    request.doi,
                    request.pdf_url,
                    request.html_url,
                    request.supplementary_urls,
                )
                download_triggered = True
                download_message = f"Download started for {', '.join(urls_available)}"
            else:
                download_message = "No file URLs provided for download"

        return ArticleCreateResponse(
            article=article,
            download_triggered=download_triggered,
            download_count=download_count,
            download_message=download_message,
        )

    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"Failed to fetch from CrossRef: {str(e)}"
        )
    finally:
        service.close()


def _download_files_for_article(
    doi: str,
    pdf_url: str | None,
    html_url: str | None,
    supplementary_urls: list[str],
) -> None:
    """
    Background task for downloading files after article creation.

    Args:
        doi: Article DOI.
        pdf_url: Optional PDF URL.
        html_url: Optional HTML URL.
        supplementary_urls: List of supplementary file URLs.
    """
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


@router.post("/add-supplementary-field")
def add_supplementary_field() -> HTMLResponse:
    """Add another supplementary file input field."""
    return HTMLResponse(
        content="""
    <div class="supplementary-url-input">
        <input type="url" name="supplementary_urls" 
               placeholder="https://example.com/supplementary.zip">
    </div>
    """
    )
