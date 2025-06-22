"""Unified article registration with file handling."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from chemlit_extractor.database import ArticleCRUD, get_db
from chemlit_extractor.models.schemas import Article
from chemlit_extractor.services.crossref import CrossRefService
from chemlit_extractor.services.file_downloader import FileDownloader

router = APIRouter()


class ArticleRegistrationRequest(BaseModel):
    """Request for article registration."""

    doi: str = Field(..., description="DOI to register")
    # Optional manual URLs - only used if automatic download fails
    pdf_url: str | None = Field(
        None, description="Manual PDF URL if auto-download fails"
    )
    html_url: str | None = Field(
        None, description="Manual HTML URL if auto-download fails"
    )
    supplementary_urls: list[str] = Field(
        default_factory=list, description="Manual supplementary URLs"
    )
    # Control flags
    auto_download: bool = Field(True, description="Try automatic file discovery")
    force_manual_urls: bool = Field(
        False, description="Skip auto-discovery, use provided URLs only"
    )


class ArticleRegistrationResponse(BaseModel):
    """Response for article registration."""

    article: Article
    file_status: dict[str, Any]
    message: str


@router.post("/articles/register")
async def register_article(
    request: Request,
    db: Session = Depends(get_db),
) -> ArticleRegistrationResponse:
    """
    Register an article with smart file downloading.

    Handles both form data (from HTMX) and JSON (from API).
    """
    # Handle both form data and JSON
    if request.headers.get("content-type", "").startswith(
        "application/x-www-form-urlencoded"
    ):
        form_data = await request.form()

        # Parse form data
        doi = form_data.get("doi", "").strip()
        auto_download = form_data.get("auto_download") == "on"
        force_manual_urls = form_data.get("force_manual_urls") == "on"
        pdf_url = form_data.get("pdf_url", "").strip() or None
        html_url = form_data.get("html_url", "").strip() or None

        # Handle multiple supplementary URLs from form
        supplementary_urls = []
        for key, value in form_data.items():
            if key == "supplementary_urls" and value.strip():
                supplementary_urls.append(value.strip())

        # Create request object
        req_data = ArticleRegistrationRequest(
            doi=doi,
            auto_download=auto_download,
            force_manual_urls=force_manual_urls,
            pdf_url=pdf_url,
            html_url=html_url,
            supplementary_urls=supplementary_urls,
        )

        # HTMX request - will return HTML
        accept_html = True
    else:
        # JSON request
        json_data = await request.json()
        req_data = ArticleRegistrationRequest(**json_data)
        accept_html = False
    """
    Register an article and optionally download associated files.
    
    Process:
    1. Fetch metadata from CrossRef
    2. Create article in database
    3. If auto_download is True: Try to automatically find and download files
    4. If automatic download fails or force_manual_urls is True: Use provided URLs
    5. Return article and file download status
    """
    # Check if article already exists
    existing = ArticleCRUD.get_by_doi(db, request.doi)
    if existing:
        error_msg = f"Article with DOI '{request.doi}' already exists"
        if accept and "text/html" in accept:
            from .response_formatter import format_registration_response

            html = format_registration_response(None, {}, error_msg, error=True)
            return HTMLResponse(content=html, status_code=400)
        raise HTTPException(status_code=400, detail=error_msg)

    # Step 1: Fetch metadata from CrossRef
    with CrossRefService() as crossref:
        result = crossref.fetch_and_convert_article(request.doi)
        if not result:
            error_msg = f"Article with DOI '{request.doi}' not found in CrossRef"
            if accept and "text/html" in accept:
                from .response_formatter import format_registration_response

                html = format_registration_response(None, {}, error_msg, error=True)
                return HTMLResponse(content=html, status_code=404)
            raise HTTPException(status_code=404, detail=error_msg)

        article_data, authors_data = result

    # Step 2: Create article in database
    try:
        article = ArticleCRUD.create(db, article_data, authors_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Step 3: Handle file downloads
    file_status = {"attempted": False, "results": {}}

    if request.auto_download and not request.force_manual_urls:
        # Try automatic file discovery
        with FileDownloader() as downloader:
            auto_results = downloader.auto_discover_and_download(
                doi=request.doi,
                publisher=article.publisher,
                url=article.url,
            )
            file_status["attempted"] = True
            file_status["results"] = auto_results
            file_status["method"] = "automatic"

    # Step 4: Use manual URLs if provided and auto-download didn't work (or was skipped)
    manual_needed = (
        request.force_manual_urls
        or not file_status["attempted"]
        or not _check_download_success(file_status["results"])
    )

    if manual_needed and _has_manual_urls(request):
        with FileDownloader() as downloader:
            manual_results = downloader.download_from_urls(
                doi=request.doi,
                pdf_url=request.pdf_url,
                html_url=request.html_url,
                supplementary_urls=request.supplementary_urls,
            )

            # Merge or replace results
            if file_status["attempted"]:
                file_status["results"].update(manual_results)
                file_status["method"] = "combined"
            else:
                file_status["results"] = manual_results
                file_status["method"] = "manual"
            file_status["attempted"] = True

    # Prepare response message
    message = _build_status_message(article, file_status)

    # Prepare response
    response = ArticleRegistrationResponse(
        article=article,
        file_status=file_status,
        message=message,
    )

    # Return HTML for HTMX requests
    if accept and "text/html" in accept:
        from .response_formatter import format_registration_response

        html = format_registration_response(article, file_status, message)
        return HTMLResponse(content=html)

    # Return JSON for API requests
    return response


def _check_download_success(results: dict) -> bool:
    """Check if any files were successfully downloaded."""
    if not results:
        return False

    for file_type in ["pdf", "html", "supplementary"]:
        if results.get(file_type, {}).get("success"):
            return True

    return False


def _has_manual_urls(request: ArticleRegistrationRequest) -> bool:
    """Check if request has any manual URLs."""
    return bool(request.pdf_url or request.html_url or request.supplementary_urls)


def _build_status_message(article: Article, file_status: dict) -> str:
    """Build a human-readable status message."""
    msg_parts = [f"Article '{article.title}' registered successfully."]

    if not file_status["attempted"]:
        msg_parts.append("No file downloads were attempted.")
    else:
        results = file_status["results"]
        successful = sum(
            1 for r in results.values() if isinstance(r, dict) and r.get("success")
        )
        total = len(results)

        if successful == 0:
            msg_parts.append("No files could be downloaded.")
        elif successful == total:
            msg_parts.append(f"All {successful} files downloaded successfully.")
        else:
            msg_parts.append(f"{successful} of {total} files downloaded successfully.")

    return " ".join(msg_parts)
