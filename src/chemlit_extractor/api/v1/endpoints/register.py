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


"""Register preview endpoint for the new unified article API."""

from fastapi import Form
from fastapi.templating import Jinja2Templates


router = APIRouter(tags=["registration"])
templates = Jinja2Templates(directory="templates")


@router.post("/fetch-preview", response_class=HTMLResponse)
async def fetch_article_preview(
    request: Request,
    doi: str = Form(...),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """
    Fetch article data from CrossRef and return editable preview form.

    This endpoint is called by HTMX to fetch article metadata and return
    an editable form that the user can review and modify before submission.
    """
    try:
        # Check if article already exists
        existing_article = ArticleCRUD.get_by_doi(db, doi.strip())
        if existing_article:
            return HTMLResponse(
                content=f"""
                <div class="bg-yellow-50 border border-yellow-200 rounded-xl p-6">
                    <div class="flex items-center">
                        <div class="flex-shrink-0">
                            <span class="text-yellow-400 text-2xl">⚠️</span>
                        </div>
                        <div class="ml-3">
                            <h3 class="text-lg font-medium text-yellow-800">Article Already Exists</h3>
                            <p class="text-yellow-700 mt-1">This article is already in your database.</p>
                            <div class="mt-4 flex space-x-3">
                                <a href="/articles/{doi}" 
                                   class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-yellow-800 bg-yellow-100 hover:bg-yellow-200 transition-colors">
                                    View Article
                                </a>
                                <button onclick="location.reload()" 
                                        class="inline-flex items-center px-4 py-2 border border-yellow-300 text-sm font-medium rounded-md text-yellow-700 bg-white hover:bg-yellow-50 transition-colors">
                                    Try Another DOI
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
                """
            )

        # Fetch from CrossRef
        service = CrossRefService()
        try:
            result = service.fetch_and_convert_article(doi.strip())
            if not result:
                return HTMLResponse(
                    content=f"""
                    <div class="bg-red-50 border border-red-200 rounded-xl p-6">
                        <div class="flex items-center">
                            <div class="flex-shrink-0">
                                <span class="text-red-400 text-2xl">❌</span>
                            </div>
                            <div class="ml-3">
                                <h3 class="text-lg font-medium text-red-800">Article Not Found</h3>
                                <p class="text-red-700 mt-1">Could not find article with DOI '{doi}' in CrossRef.</p>
                                <p class="text-red-600 text-sm mt-2">Please check the DOI and try again.</p>
                                <button onclick="location.reload()" 
                                        class="mt-4 inline-flex items-center px-4 py-2 border border-red-300 text-sm font-medium rounded-md text-red-700 bg-white hover:bg-red-50 transition-colors">
                                    Try Again
                                </button>
                            </div>
                        </div>
                    </div>
                    """
                )

            article_data, authors_data = result

            # Convert Pydantic models to dicts for template
            article_dict = article_data.model_dump()
            authors_list = [author.model_dump() for author in authors_data]

            # Clean up any JATS markup in the abstract if present
            if article_dict.get("abstract"):
                abstract = article_dict["abstract"]
                # Remove common JATS tags
                jats_tags = [
                    "<jats:p>",
                    "</jats:p>",
                    "<jats:sub>",
                    "</jats:sub>",
                    "<jats:sup>",
                    "</jats:sup>",
                    "<jats:italic>",
                    "</jats:italic>",
                    "<jats:bold>",
                    "</jats:bold>",
                ]
                for tag in jats_tags:
                    abstract = abstract.replace(tag, "")
                article_dict["abstract"] = abstract.strip()

            # Render the editable form
            return templates.TemplateResponse(
                "article_preview_form.html",
                {
                    "request": request,
                    "article": article_dict,
                    "authors": authors_list,
                },
            )

        except Exception as e:
            return HTMLResponse(
                content=f"""
                <div class="bg-red-50 border border-red-200 rounded-xl p-6">
                    <div class="flex items-center">
                        <div class="flex-shrink-0">
                            <span class="text-red-400 text-2xl">🚨</span>
                        </div>
                        <div class="ml-3">
                            <h3 class="text-lg font-medium text-red-800">CrossRef Error</h3>
                            <p class="text-red-700 mt-1">Failed to fetch article data from CrossRef.</p>
                            <p class="text-red-600 text-sm mt-2">Error: {str(e)}</p>
                            <button onclick="location.reload()" 
                                    class="mt-4 inline-flex items-center px-4 py-2 border border-red-300 text-sm font-medium rounded-md text-red-700 bg-white hover:bg-red-50 transition-colors">
                                Try Again
                            </button>
                        </div>
                    </div>
                </div>
                """
            )
        finally:
            service.close()

    except Exception as e:
        return HTMLResponse(
            content=f"""
            <div class="bg-red-50 border border-red-200 rounded-xl p-6">
                <div class="flex items-center">
                    <div class="flex-shrink-0">
                        <span class="text-red-400 text-2xl">❌</span>
                    </div>
                    <div class="ml-3">
                        <h3 class="text-lg font-medium text-red-800">Unexpected Error</h3>
                        <p class="text-red-700 mt-1">An unexpected error occurred.</p>
                        <p class="text-red-600 text-sm mt-2">Error: {str(e)}</p>
                        <button onclick="location.reload()" 
                                class="mt-4 inline-flex items-center px-4 py-2 border border-red-300 text-sm font-medium rounded-md text-red-700 bg-white hover:bg-red-50 transition-colors">
                            Try Again
                        </button>
                    </div>
                </div>
            </div>
            """
        )


@router.post("/success-response", response_class=HTMLResponse)
async def format_success_response(
    request: Request,
    response_data: dict,
) -> HTMLResponse:
    """
    Format the successful registration response for display.

    This would be called after successful article creation to show
    a nice success message with the results.
    """
    article = response_data.get("article", {})
    download_status = response_data.get("download_status", {})

    # Build file download status HTML if applicable
    download_html = ""
    if download_status and download_status.get("triggered"):
        download_html = f"""
        <div class="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
            <div class="flex items-center">
                <div class="flex-shrink-0">
                    <span class="text-blue-400 text-xl">📥</span>
                </div>
                <div class="ml-3">
                    <h4 class="text-sm font-medium text-blue-800">File Downloads</h4>
                    <p class="text-blue-700 text-sm">
                        {download_status.get('file_count', 0)} files queued for download
                    </p>
                </div>
            </div>
        </div>
        """

    return HTMLResponse(
        content=f"""
        <div class="bg-green-50 border border-green-200 rounded-xl p-8">
            <div class="flex items-center">
                <div class="flex-shrink-0">
                    <span class="text-green-400 text-3xl">✅</span>
                </div>
                <div class="ml-4 flex-1">
                    <h3 class="text-xl font-medium text-green-800 mb-2">Article Registered Successfully!</h3>
                    <div class="text-green-700 space-y-1">
                        <p><strong>Title:</strong> {article.get('title', 'N/A')}</p>
                        <p><strong>DOI:</strong> <code class="bg-green-100 px-2 py-1 rounded text-sm">{article.get('doi', 'N/A')}</code></p>
                        <p><strong>Authors:</strong> {len(article.get('authors', []))} author(s) registered</p>
                    </div>
                    
                    {download_html}
                    
                    <div class="mt-6 flex space-x-3">
                        <a href="/articles/{article.get('doi', '')}" 
                           class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-green-600 hover:bg-green-700 transition-colors">
                            View Article
                        </a>
                        <button onclick="location.reload()" 
                                class="inline-flex items-center px-4 py-2 border border-green-300 text-sm font-medium rounded-md text-green-700 bg-white hover:bg-green-50 transition-colors">
                            Register Another
                        </button>
                    </div>
                </div>
            </div>
        </div>
        """
    )
