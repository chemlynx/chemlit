# Add these endpoints to your FastAPI application
# You can put them in a new file like `register.py` or add to existing endpoints

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Query,
    Request,
)
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from chemlit_extractor.database import ArticleCRUD, get_db
from chemlit_extractor.services.crossref import CrossRefService

router = APIRouter(tags=["registration"])


@router.get("/toggle-download-fields")
def toggle_download_fields(enabled: bool = Query(default=True)) -> HTMLResponse:
    """Toggle visibility of download fields based on checkbox state."""
    if enabled:
        return HTMLResponse(
            content="""
        <div id="download-fields">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <div>
                    <label for="pdf_url" class="block text-sm font-medium text-gray-700 mb-1">
                        PDF URL
                    </label>
                    <input type="url" 
                           id="pdf_url" 
                           name="pdf_url" 
                           placeholder="https://example.com/article.pdf"
                           class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-chem-blue focus:border-chem-blue text-sm">
                </div>

                <div>
                    <label for="html_url" class="block text-sm font-medium text-gray-700 mb-1">
                        HTML URL
                    </label>
                    <input type="url" 
                           id="html_url" 
                           name="html_url" 
                           placeholder="https://example.com/article.html"
                           class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-chem-blue focus:border-chem-blue text-sm">
                </div>
            </div>

            <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">
                    Supplementary Files
                </label>
                <div id="supplementary-urls" class="space-y-2 mb-3">
                    <div class="supplementary-url-input">
                        <input type="url" 
                               name="supplementary_urls" 
                               placeholder="https://example.com/supplementary1.zip"
                               class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-chem-blue focus:border-chem-blue text-sm">
                    </div>
                </div>
                <button type="button" 
                        class="text-sm text-chem-blue hover:text-chem-dark font-medium"
                        hx-post="/register/add-supplementary-field"
                        hx-target="#supplementary-urls"
                        hx-swap="beforeend">
                    + Add Another Supplementary File
                </button>
            </div>

            <div class="mt-4 p-3 bg-blue-50 rounded-md">
                <p class="text-sm text-blue-700">
                    <strong>Tip:</strong> Files will be downloaded in the background after article registration. 
                    You can check download progress in the file status section below.
                </p>
            </div>
        </div>
        """
        )
    else:
        return HTMLResponse(
            content="""
        <div id="download-fields">
            <div class="p-3 bg-gray-50 rounded-md text-center">
                <p class="text-sm text-gray-600">File downloads disabled. Check the box above to enable file downloads.</p>
            </div>
        </div>
        """
        )


@router.post("/add-supplementary-field")
def add_supplementary_field() -> HTMLResponse:
    """Add another supplementary file input field."""
    return HTMLResponse(
        content="""
    <div class="supplementary-url-input">
        <input type="url" 
               name="supplementary_urls" 
               placeholder="https://example.com/supplementary.zip"
               class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-chem-blue focus:border-chem-blue text-sm">
    </div>
    """
    )


# Replace your main register endpoint with this fixed version


@router.post("/from-doi-with-files")
async def create_article_from_doi_with_files_styled(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Create an article from CrossRef with optional file downloads (Fixed version)."""

    try:
        # Get form data manually to handle edge cases
        form_data = await request.form()

        # Extract and validate required fields
        doi = form_data.get("doi", "").strip()
        if not doi:
            return HTMLResponse(
                content="""
                <div id="article-form" class="bg-red-50 border border-red-200 rounded-xl p-8">
                    <div class="flex items-center">
                        <div class="flex-shrink-0">
                            <span class="text-red-400 text-2xl">❌</span>
                        </div>
                        <div class="ml-3">
                            <h3 class="text-lg font-medium text-red-800">Error</h3>
                            <p class="text-red-700">DOI is required.</p>
                        </div>
                    </div>
                </div>
                """,
                status_code=400,
            )

        # Handle checkbox - checkbox only sends value when checked
        download_files = "download_files" in form_data

        # Handle optional URL fields
        pdf_url = form_data.get("pdf_url", "").strip() or None
        html_url = form_data.get("html_url", "").strip() or None

        # Handle multiple supplementary URLs
        supplementary_urls = []
        for url in form_data.getlist("supplementary_urls"):
            url = url.strip()
            if url:  # Only add non-empty URLs
                supplementary_urls.append(url)

        # Check if article already exists
        existing_article = ArticleCRUD.get_by_doi(db, doi)
        if existing_article:
            return HTMLResponse(
                content=f"""
                <div id="article-form" class="bg-yellow-50 border border-yellow-200 rounded-xl p-8">
                    <div class="flex items-center">
                        <div class="flex-shrink-0">
                            <span class="text-yellow-400 text-2xl">⚠️</span>
                        </div>
                        <div class="ml-3">
                            <h3 class="text-lg font-medium text-yellow-800">Article Already Exists</h3>
                            <p class="text-yellow-700">Article with DOI '{doi}' already exists in the database.</p>
                            <div class="mt-4">
                                <a href="/articles/{doi}" 
                                   class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-yellow-800 bg-yellow-100 hover:bg-yellow-200 transition-colors">
                                    View Existing Article
                                </a>
                            </div>
                        </div>
                    </div>
                </div>
                """,
                status_code=400,
            )

        # Fetch from CrossRef and create article
        service = CrossRefService()
        try:
            result = service.fetch_and_convert_article(doi)
            if not result:
                return HTMLResponse(
                    content=f"""
                    <div id="article-form" class="bg-red-50 border border-red-200 rounded-xl p-8">
                        <div class="flex items-center">
                            <div class="flex-shrink-0">
                                <span class="text-red-400 text-2xl">🔍</span>
                            </div>
                            <div class="ml-3">
                                <h3 class="text-lg font-medium text-red-800">Article Not Found</h3>
                                <p class="text-red-700">Article with DOI '{doi}' not found in CrossRef database.</p>
                                <p class="text-red-600 text-sm mt-1">Please check the DOI and try again.</p>
                            </div>
                        </div>
                    </div>
                    """,
                    status_code=404,
                )

            article_data, authors_data = result

            # FIXED: Proper HttpUrl to string conversion
            # Convert the Pydantic model to dict, then fix the URL field
            article_dict = article_data.model_dump()
            if "url" in article_dict and article_dict["url"] is not None:
                # Handle both HttpUrl objects and strings
                url_value = article_dict["url"]
                if hasattr(url_value, "__str__") and not isinstance(url_value, str):
                    article_dict["url"] = str(url_value)

            # Convert authors data to dicts as well
            authors_list = []
            if authors_data:
                for author in authors_data:
                    if hasattr(author, "model_dump"):
                        authors_list.append(author.model_dump())
                    else:
                        authors_list.append(author)

            # Create article using the dict data instead of Pydantic models
            try:
                # Import the model classes
                from chemlit_extractor.database.models import Article as ArticleModel
                from chemlit_extractor.database.models import Author as AuthorModel
                from chemlit_extractor.database.models import (
                    ArticleAuthor as ArticleAuthorModel,
                )

                # Create article directly using SQLAlchemy model
                db_article = ArticleModel(**article_dict)
                db.add(db_article)

                # Handle authors if provided
                if authors_list:
                    for author_data in authors_list:
                        # Create or get existing author
                        existing_author = None

                        if author_data.get("orcid"):
                            existing_author = (
                                db.query(AuthorModel)
                                .filter(AuthorModel.orcid == author_data["orcid"])
                                .first()
                            )

                        if not existing_author:
                            existing_author = (
                                db.query(AuthorModel)
                                .filter(
                                    AuthorModel.first_name == author_data["first_name"],
                                    AuthorModel.last_name == author_data["last_name"],
                                )
                                .first()
                            )

                        if not existing_author:
                            existing_author = AuthorModel(**author_data)
                            db.add(existing_author)
                            db.flush()  # Get the ID

                        # Create association
                        association = ArticleAuthorModel(
                            article_doi=doi,
                            author_id=existing_author.id,
                            author_order=len(db_article.authors) + 1,
                        )
                        db.add(association)

                db.commit()
                db.refresh(db_article)

            except Exception as e:
                db.rollback()
                return HTMLResponse(
                    content=f"""
                    <div id="article-form" class="bg-red-50 border border-red-200 rounded-xl p-8">
                        <div class="flex items-center">
                            <div class="flex-shrink-0">
                                <span class="text-red-400 text-2xl">💾</span>
                            </div>
                            <div class="ml-3">
                                <h3 class="text-lg font-medium text-red-800">Database Error</h3>
                                <p class="text-red-700">Failed to save article to database.</p>
                                <p class="text-red-600 text-sm mt-1">Error: {str(e)}</p>
                            </div>
                        </div>
                    </div>
                    """,
                    status_code=500,
                )

            # Handle downloads
            download_html = ""
            if download_files:
                download_count = 0
                urls_available = []

                if pdf_url:
                    urls_available.append("PDF")
                    download_count += 1
                if html_url:
                    urls_available.append("HTML")
                    download_count += 1
                if supplementary_urls:
                    urls_available.append(
                        f"{len(supplementary_urls)} supplementary files"
                    )
                    download_count += len(supplementary_urls)

                if download_count > 0:
                    # Import the background task function
                    from chemlit_extractor.api.v1.endpoints.articles import (
                        _download_files_for_article,
                    )

                    background_tasks.add_task(
                        _download_files_for_article,
                        doi,
                        pdf_url,
                        html_url,
                        supplementary_urls,
                    )
                    download_html = f"""
                    <div class="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-4">
                        <div class="flex items-center">
                            <div class="flex-shrink-0">
                                <span class="text-blue-400 text-xl">📥</span>
                            </div>
                            <div class="ml-3">
                                <h4 class="text-sm font-medium text-blue-800">Downloads Started</h4>
                                <p class="text-blue-700 text-sm">{', '.join(urls_available)} are downloading in the background.</p>
                            </div>
                        </div>
                    </div>
                    """
                else:
                    download_html = """
                    <div class="mt-6 bg-gray-50 border border-gray-200 rounded-lg p-4">
                        <p class="text-gray-600 text-sm">Downloads enabled but no URLs provided.</p>
                    </div>
                    """

            # Format authors list
            authors_display = (
                ", ".join(
                    [
                        f"{author.get('first_name', '')} {author.get('last_name', '')}"
                        for author in authors_list
                    ]
                )
                if authors_list
                else "N/A"
            )

            return HTMLResponse(
                content=f"""
                <div id="article-form" class="bg-green-50 border border-green-200 rounded-xl p-8">
                    <div class="flex items-center mb-6">
                        <div class="flex-shrink-0">
                            <span class="text-green-400 text-2xl">✅</span>
                        </div>
                        <div class="ml-3">
                            <h3 class="text-lg font-medium text-green-800">Article Registered Successfully!</h3>
                            <p class="text-green-700">Article metadata has been fetched and saved to your database.</p>
                        </div>
                    </div>
                    
                    <div class="bg-white rounded-lg p-6 shadow-sm">
                        <h4 class="text-lg font-semibold text-gray-900 mb-4">Article Details</h4>
                        <dl class="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                            <div>
                                <dt class="font-medium text-gray-700">Title</dt>
                                <dd class="text-gray-900 mt-1">{article_dict.get('title', 'N/A')}</dd>
                            </div>
                            <div>
                                <dt class="font-medium text-gray-700">Journal</dt>
                                <dd class="text-gray-900 mt-1">{article_dict.get('journal', 'N/A')}</dd>
                            </div>
                            <div>
                                <dt class="font-medium text-gray-700">Year</dt>
                                <dd class="text-gray-900 mt-1">{article_dict.get('year', 'N/A')}</dd>
                            </div>
                            <div>
                                <dt class="font-medium text-gray-700">Authors</dt>
                                <dd class="text-gray-900 mt-1">{authors_display}</dd>
                            </div>
                            <div class="md:col-span-2">
                                <dt class="font-medium text-gray-700">DOI</dt>
                                <dd class="text-gray-900 mt-1 font-mono text-sm">{doi}</dd>
                            </div>
                        </dl>
                    </div>
                    
                    {download_html}
                    
                    <div class="mt-6 flex space-x-3">
                        <button class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-chem-blue hover:bg-chem-dark transition-colors" 
                                hx-get="/api/v1/files/{doi}/stats/html" 
                                hx-target="#file-status"
                                hx-swap="innerHTML">
                            Check File Status
                        </button>
                        <a href="/articles/{doi}" 
                           class="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 transition-colors">
                            View Article Details
                        </a>
                        <button class="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 transition-colors"
                                onclick="location.reload()">
                            Register Another Article
                        </button>
                    </div>
                </div>
                """,
                status_code=201,
            )

        except Exception as e:
            return HTMLResponse(
                content=f"""
                <div id="article-form" class="bg-red-50 border border-red-200 rounded-xl p-8">
                    <div class="flex items-center">
                        <div class="flex-shrink-0">
                            <span class="text-red-400 text-2xl">🚨</span>
                        </div>
                        <div class="ml-3">
                            <h3 class="text-lg font-medium text-red-800">CrossRef Error</h3>
                            <p class="text-red-700">Failed to fetch article data from CrossRef.</p>
                            <p class="text-red-600 text-sm mt-1">Error: {str(e)}</p>
                        </div>
                    </div>
                </div>
                """,
                status_code=502,
            )
        finally:
            service.close()

    except Exception as e:
        return HTMLResponse(
            content=f"""
            <div id="article-form" class="bg-red-50 border border-red-200 rounded-xl p-8">
                <div class="flex items-center">
                    <div class="flex-shrink-0">
                        <span class="text-red-400 text-2xl">❌</span>
                    </div>
                    <div class="ml-3">
                        <h3 class="text-lg font-medium text-red-800">Unexpected Error</h3>
                        <p class="text-red-700">An unexpected error occurred while processing your request.</p>
                        <p class="text-red-600 text-sm mt-1">Error: {str(e)}</p>
                    </div>
                </div>
            </div>
            """,
            status_code=500,
        )


# Add this TEMPORARY debug endpoint to your register.py file
# (You can replace the existing from-doi-with-files endpoint temporarily)


@router.post("/from-doi-with-files-debug")
async def debug_form_submission(request: Request) -> HTMLResponse:
    """Debug endpoint to see what form data is being sent."""

    try:
        form_data = await request.form()

        debug_info = "<h3>Debug - Form Data Received:</h3><ul>"
        for key, value in form_data.items():
            debug_info += f"<li><strong>{key}:</strong> '{value}' (type: {type(value).__name__})</li>"
        debug_info += "</ul>"

        # Also check if multiple values for same key
        debug_info += "<h3>All Form Data (including multiples):</h3><ul>"
        for key in form_data.keys():
            values = form_data.getlist(key)
            debug_info += f"<li><strong>{key}:</strong> {values}</li>"
        debug_info += "</ul>"

        # Check specific fields
        doi = form_data.get("doi", "").strip()
        download_files = "download_files" in form_data
        pdf_url = form_data.get("pdf_url", "").strip() or None
        html_url = form_data.get("html_url", "").strip() or None

        debug_info += "<h3>Parsed Values:</h3><ul>"
        debug_info += f"<li><strong>DOI:</strong> '{doi}' (length: {len(doi)})</li>"
        debug_info += f"<li><strong>Download files:</strong> {download_files}</li>"
        debug_info += f"<li><strong>PDF URL:</strong> {pdf_url}</li>"
        debug_info += f"<li><strong>HTML URL:</strong> {html_url}</li>"
        debug_info += "</ul>"

        return HTMLResponse(
            content=f"""
        <div id="article-form" class="bg-blue-50 border border-blue-200 rounded-xl p-8">
            <h2>Debug Information</h2>
            {debug_info}
        </div>
        """
        )

    except Exception as e:
        return HTMLResponse(
            content=f"""
        <div id="article-form" class="bg-red-50 border border-red-200 rounded-xl p-8">
            <h2>Debug Error</h2>
            <p>Error processing form: {str(e)}</p>
        </div>
        """,
            status_code=500,
        )


# Also add this simple test endpoint
@router.post("/test-simple")
async def test_simple_endpoint(request: Request) -> HTMLResponse:
    """Simple test endpoint."""
    return HTMLResponse(
        content="""
    <div id="article-form" class="bg-green-50 border border-green-200 rounded-xl p-8">
        <h2>✅ Simple Test Success!</h2>
        <p>The endpoint is reachable and working.</p>
    </div>
    """
    )


# Add this step-by-step debug endpoint to your register.py


@router.post("/from-doi-with-files-step-debug")
async def step_by_step_debug(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Step-by-step debug to isolate the 400 error."""

    debug_steps = []

    try:
        # Step 1: Get form data
        form_data = await request.form()
        doi = form_data.get("doi", "").strip()
        debug_steps.append(f"✅ Step 1: Got DOI '{doi}'")

        if not doi:
            debug_steps.append("❌ Step 1 FAILED: DOI is empty")
            return HTMLResponse(
                content=f"""
            <div id="article-form" class="bg-red-50 border border-red-200 rounded-xl p-8">
                <h3>Debug Steps:</h3>
                <ul>{"".join([f"<li>{step}</li>" for step in debug_steps])}</ul>
            </div>
            """,
                status_code=400,
            )

        # Step 2: Check DOI validation (if you implemented centralized validation)
        try:
            # If you have centralized DOI validation, test it here
            # from chemlit_extractor.utils import validate_and_normalize_doi
            # normalized_doi = validate_and_normalize_doi(doi)
            # debug_steps.append(f"✅ Step 2: DOI validation passed, normalized to '{normalized_doi}'")
            debug_steps.append(
                "✅ Step 2: DOI validation skipped (not implemented yet)"
            )
        except Exception as e:
            debug_steps.append(f"❌ Step 2 FAILED: DOI validation error: {str(e)}")
            return HTMLResponse(
                content=f"""
            <div id="article-form" class="bg-red-50 border border-red-200 rounded-xl p-8">
                <h3>Debug Steps:</h3>
                <ul>{"".join([f"<li>{step}</li>" for step in debug_steps])}</ul>
            </div>
            """,
                status_code=400,
            )

        # Step 3: Check if article already exists
        try:
            existing_article = ArticleCRUD.get_by_doi(db, doi)
            if existing_article:
                debug_steps.append(
                    f"❌ Step 3: Article with DOI '{doi}' already exists!"
                )
                return HTMLResponse(
                    content=f"""
                <div id="article-form" class="bg-yellow-50 border border-yellow-200 rounded-xl p-8">
                    <h3>Debug Steps:</h3>
                    <ul>{"".join([f"<li>{step}</li>" for step in debug_steps])}</ul>
                    <p><strong>Issue found:</strong> This article is already in your database.</p>
                </div>
                """,
                    status_code=400,
                )
            else:
                debug_steps.append(
                    "✅ Step 3: Article does not exist yet, good to proceed"
                )
        except Exception as e:
            debug_steps.append(f"❌ Step 3 FAILED: Database check error: {str(e)}")
            return HTMLResponse(
                content=f"""
            <div id="article-form" class="bg-red-50 border border-red-200 rounded-xl p-8">
                <h3>Debug Steps:</h3>
                <ul>{"".join([f"<li>{step}</li>" for step in debug_steps])}</ul>
            </div>
            """,
                status_code=500,
            )

        # Step 4: Test CrossRef connection
        try:
            service = CrossRefService()
            debug_steps.append("✅ Step 4: CrossRef service created")
        except Exception as e:
            debug_steps.append(
                f"❌ Step 4 FAILED: CrossRef service creation error: {str(e)}"
            )
            return HTMLResponse(
                content=f"""
            <div id="article-form" class="bg-red-50 border border-red-200 rounded-xl p-8">
                <h3>Debug Steps:</h3>
                <ul>{"".join([f"<li>{step}</li>" for step in debug_steps])}</ul>
            </div>
            """,
                status_code=500,
            )

        # Step 5: Test CrossRef fetch
        try:
            result = service.fetch_and_convert_article(doi)
            if not result:
                debug_steps.append(f"❌ Step 5: DOI '{doi}' not found in CrossRef")
                return HTMLResponse(
                    content=f"""
                <div id="article-form" class="bg-red-50 border border-red-200 rounded-xl p-8">
                    <h3>Debug Steps:</h3>
                    <ul>{"".join([f"<li>{step}</li>" for step in debug_steps])}</ul>
                    <p><strong>Issue found:</strong> Article not found in CrossRef database.</p>
                </div>
                """,
                    status_code=404,
                )
            else:
                article_data, authors_data = result
                debug_steps.append(
                    f"✅ Step 5: CrossRef fetch successful, got article: '{article_data.title[:50]}...'"
                )
        except Exception as e:
            debug_steps.append(f"❌ Step 5 FAILED: CrossRef fetch error: {str(e)}")
            service.close()
            return HTMLResponse(
                content=f"""
            <div id="article-form" class="bg-red-50 border border-red-200 rounded-xl p-8">
                <h3>Debug Steps:</h3>
                <ul>{"".join([f"<li>{step}</li>" for step in debug_steps])}</ul>
            </div>
            """,
                status_code=502,
            )

        # Step 6: Test URL conversion (HttpUrl issue we had before)
        try:
            if hasattr(article_data, "url") and article_data.url is not None:
                article_data.url = str(article_data.url)
                debug_steps.append("✅ Step 6: URL conversion successful")
            else:
                debug_steps.append("✅ Step 6: No URL to convert")
        except Exception as e:
            debug_steps.append(f"❌ Step 6 FAILED: URL conversion error: {str(e)}")
            service.close()
            return HTMLResponse(
                content=f"""
            <div id="article-form" class="bg-red-50 border border-red-200 rounded-xl p-8">
                <h3>Debug Steps:</h3>
                <ul>{"".join([f"<li>{step}</li>" for step in debug_steps])}</ul>
            </div>
            """,
                status_code=500,
            )

        # Step 7: Test database creation
        try:
            article = ArticleCRUD.create(db, article_data, authors_data)
            debug_steps.append(
                f"✅ Step 7: Article created successfully! ID: {article.doi}"
            )
        except ValueError as e:
            debug_steps.append(
                f"❌ Step 7 FAILED: Article creation validation error: {str(e)}"
            )
            service.close()
            return HTMLResponse(
                content=f"""
            <div id="article-form" class="bg-red-50 border border-red-200 rounded-xl p-8">
                <h3>Debug Steps:</h3>
                <ul>{"".join([f"<li>{step}</li>" for step in debug_steps])}</ul>
            </div>
            """,
                status_code=400,
            )
        except Exception as e:
            debug_steps.append(
                f"❌ Step 7 FAILED: Article creation database error: {str(e)}"
            )
            service.close()
            return HTMLResponse(
                content=f"""
            <div id="article-form" class="bg-red-50 border border-red-200 rounded-xl p-8">
                <h3>Debug Steps:</h3>
                <ul>{"".join([f"<li>{step}</li>" for step in debug_steps])}</ul>
            </div>
            """,
                status_code=500,
            )

        service.close()
        debug_steps.append("✅ ALL STEPS PASSED! Article registration should work.")

        return HTMLResponse(
            content=f"""
        <div id="article-form" class="bg-green-50 border border-green-200 rounded-xl p-8">
            <h3>🎉 Debug Success!</h3>
            <ul>{"".join([f"<li>{step}</li>" for step in debug_steps])}</ul>
            <p><strong>Article registered:</strong> {article.title}</p>
            <p><strong>Authors:</strong> {len(article.authors)} author(s)</p>
        </div>
        """,
            status_code=201,
        )

    except Exception as e:
        debug_steps.append(f"❌ UNEXPECTED ERROR: {str(e)}")
        return HTMLResponse(
            content=f"""
        <div id="article-form" class="bg-red-50 border border-red-200 rounded-xl p-8">
            <h3>Debug Steps:</h3>
            <ul>{"".join([f"<li>{step}</li>" for step in debug_steps])}</ul>
        </div>
        """,
            status_code=500,
        )
