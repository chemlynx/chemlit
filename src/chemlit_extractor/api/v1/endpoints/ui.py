"""FastAPI endpoints for the ChemLit Extractor UI."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from chemlit_extractor.database import ArticleCRUD, AuthorCRUD, CompoundCRUD, get_db
from chemlit_extractor.models.schemas import ArticleCreate
from chemlit_extractor.services.crossref import CrossRefService

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Initialize CrossRef service
crossref_service = CrossRefService()


@router.get("/", response_class=HTMLResponse)
async def homepage(request: Request):
    """Render the homepage."""
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/search", response_class=HTMLResponse)
async def search_page(request: Request):
    """Render the search page."""
    return templates.TemplateResponse("search.html", {"request": request})


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Render the article registration page."""
    return templates.TemplateResponse("register.html", {"request": request})


@router.get("/stats/html", response_class=HTMLResponse)
async def get_stats_html(request: Request, db: Session = Depends(get_db)):
    """Get database statistics as HTML for HTMX."""
    try:
        # Get counts from database using existing methods
        article_count = ArticleCRUD.count(db)
        author_count = AuthorCRUD.count(db)
        compound_count = CompoundCRUD.count(db)

        stats_html = f"""
        <div class="bg-white rounded-xl shadow-sm p-6 border border-gray-200">
            <div class="flex items-center">
                <div class="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center">
                    <span class="text-blue-600 text-xl">📄</span>
                </div>
                <div class="ml-4">
                    <p class="text-sm font-medium text-gray-600">Total Articles</p>
                    <p class="text-2xl font-bold text-gray-900">{article_count:,}</p>
                </div>
            </div>
        </div>
        
        <div class="bg-white rounded-xl shadow-sm p-6 border border-gray-200">
            <div class="flex items-center">
                <div class="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center">
                    <span class="text-green-600 text-xl">🧪</span>
                </div>
                <div class="ml-4">
                    <p class="text-sm font-medium text-gray-600">Total Compounds</p>
                    <p class="text-2xl font-bold text-gray-900">{compound_count:,}</p>
                </div>
            </div>
        </div>
        
        <div class="bg-white rounded-xl shadow-sm p-6 border border-gray-200">
            <div class="flex items-center">
                <div class="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center">
                    <span class="text-purple-600 text-xl">👥</span>
                </div>
                <div class="ml-4">
                    <p class="text-sm font-medium text-gray-600">Total Authors</p>
                    <p class="text-2xl font-bold text-gray-900">{author_count:,}</p>
                </div>
            </div>
        </div>
        """

        return HTMLResponse(content=stats_html)

    except Exception as e:
        error_html = f"""
        <div class="col-span-3 bg-red-50 border border-red-200 rounded-lg p-4">
            <p class="text-red-600">Error loading statistics: {str(e)}</p>
        </div>
        """
        return HTMLResponse(content=error_html)


@router.post("/search", response_class=HTMLResponse)
async def search_articles(
    request: Request,
    db: Session = Depends(get_db),
    doi: str = Form(None),
    author: str = Form(None),
    year: int = Form(None),
    journal: str = Form(None),
):
    """Search articles and return HTML results."""
    try:
        results = []

        if doi:
            # Search by DOI
            article = ArticleCRUD.get_by_doi(db, doi.strip())
            if article:
                results = [article]
        else:
            # Use existing search with ArticleSearchQuery
            from chemlit_extractor.models.schemas import ArticleSearchQuery

            search_query = ArticleSearchQuery(
                author=author.strip() if author else None,
                year=year,
                journal=journal.strip() if journal else None,
                limit=20,  # Limit results for UI
            )

            results, total_count = ArticleCRUD.search(db, search_query)

        # Render results (rest of the method stays the same)
        if not results:
            results_html = """
            <div class="bg-yellow-50 border border-yellow-200 rounded-lg p-6 text-center">
                <div class="w-12 h-12 bg-yellow-100 rounded-lg flex items-center justify-center mx-auto mb-4">
                    <span class="text-yellow-600 text-xl">🔍</span>
                </div>
                <h3 class="text-lg font-medium text-yellow-800 mb-2">No Results Found</h3>
                <p class="text-yellow-600">No articles match your search criteria. Try different terms or check for typos.</p>
            </div>
            """
        else:
            results_list = []
            for article in results:
                authors_names = [
                    f"{a.first_name} {a.last_name}" for a in article.authors[:3]
                ]
                authors_display = ", ".join(authors_names)
                if len(article.authors) > 3:
                    authors_display += f" and {len(article.authors) - 3} more"

                result_html = f"""
                <div class="bg-white border border-gray-200 rounded-lg p-6 hover:shadow-md transition-shadow">
                    <div class="flex justify-between items-start">
                        <div class="flex-1">
                            <h3 class="text-lg font-semibold text-gray-900 mb-2">
                                <a href="/articles/{article.doi}" class="hover:text-blue-600 transition-colors">
                                    {article.title}
                                </a>
                            </h3>
                            <p class="text-gray-600 mb-2">{authors_display}</p>
                            <div class="flex items-center space-x-4 text-sm text-gray-500">
                                <span>{article.journal or 'Unknown Journal'}</span>
                                <span>•</span>
                                <span>{article.year or 'Unknown Year'}</span>
                                <span>•</span>
                                <span class="font-mono text-xs bg-gray-100 px-2 py-1 rounded">{article.doi}</span>
                            </div>
                        </div>
                        <div class="flex items-center space-x-2 ml-4">
                            <span class="bg-blue-100 text-blue-800 text-xs font-medium px-2.5 py-0.5 rounded">
                                {len(article.compounds)} compounds
                            </span>
                        </div>
                    </div>
                </div>
                """
                results_list.append(result_html)

            results_html = f"""
            <div class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
                <div class="p-6 border-b border-gray-200">
                    <h3 class="text-lg font-semibold text-gray-900">
                        Search Results ({len(results)} found)
                    </h3>
                </div>
                <div class="divide-y divide-gray-200">
                    {"".join(results_list)}
                </div>
            </div>
            """

        return HTMLResponse(content=results_html)

    except Exception as e:
        error_html = f"""
        <div class="bg-red-50 border border-red-200 rounded-lg p-6">
            <h3 class="text-lg font-medium text-red-800 mb-2">Search Error</h3>
            <p class="text-red-600">An error occurred while searching: {str(e)}</p>
        </div>
        """
        return HTMLResponse(content=error_html)


@router.post("/register/fetch-doi", response_class=HTMLResponse)
async def fetch_doi_data(
    request: Request,
    doi: str = Form(...),
    db: Session = Depends(get_db),
):
    """Fetch article data from CrossRef by DOI and return editable form."""
    try:
        # Check if article already exists
        existing_article = ArticleCRUD.get_by_doi(db, doi.strip())
        if existing_article:
            error_html = f"""
            <div class="bg-yellow-50 border border-yellow-200 rounded-lg p-6">
                <h3 class="text-lg font-medium text-yellow-800 mb-2">Article Already Exists</h3>
                <p class="text-yellow-600 mb-4">This article is already in your database.</p>
                <a href="/articles/{doi}" class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700">
                    View Article
                </a>
            </div>
            """
            return HTMLResponse(content=error_html)

        # Fetch from CrossRef
        result = crossref_service.fetch_and_convert_article(doi.strip())
        if not result:
            error_html = """
            <div class="bg-red-50 border border-red-200 rounded-lg p-6">
                <h3 class="text-lg font-medium text-red-800 mb-2">Article Not Found</h3>
                <p class="text-red-600">Could not find article data for this DOI. Please check the DOI and try again.</p>
            </div>
            """
            return HTMLResponse(content=error_html)

        article_data, authors_data = result

        # Render the editable form
        return templates.TemplateResponse(
            "article_form.html",
            {
                "request": request,
                "article": article_data,
                "authors": authors_data,
            },
        )

    except Exception as e:
        error_html = f"""
        <div class="bg-red-50 border border-red-200 rounded-lg p-6">
            <h3 class="text-lg font-medium text-red-800 mb-2">Fetch Error</h3>
            <p class="text-red-600">An error occurred while fetching article data: {str(e)}</p>
        </div>
        """
        return HTMLResponse(content=error_html)


@router.post("/register/save", response_class=HTMLResponse)
async def save_article(
    request: Request,
    db: Session = Depends(get_db),
    # Article fields
    doi: str = Form(...),
    title: str = Form(...),
    journal: str = Form(None),
    year: int = Form(None),
    volume: str = Form(None),
    issue: str = Form(None),
    pages: str = Form(None),
    abstract: str = Form(None),
):
    """Save the edited article data to the database."""
    try:
        # Create article
        article_data = ArticleCreate(
            doi=doi.strip(),
            title=title.strip(),
            journal=journal.strip() if journal else None,
            year=year,
            volume=volume.strip() if volume else None,
            issue=issue.strip() if issue else None,
            pages=pages.strip() if pages else None,
            abstract=abstract.strip() if abstract else None,
        )

        # Save article
        article = ArticleCRUD.create(db, article_data)

        # Parse and save authors (this is a simplified version)
        # In a real implementation, you'd parse the form data for authors

        success_html = f"""
        <div class="bg-green-50 border border-green-200 rounded-lg p-6">
            <div class="flex items-center">
                <div class="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center">
                    <span class="text-green-600 text-xl">✅</span>
                </div>
                <div class="ml-4">
                    <h3 class="text-lg font-medium text-green-800 mb-2">Article Registered Successfully!</h3>
                    <p class="text-green-600 mb-4">The article has been added to your database.</p>
                    <div class="flex space-x-4">
                        <a href="/articles/{doi}" class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-green-600 hover:bg-green-700">
                            View Article
                        </a>
                        <a href="/register" class="inline-flex items-center px-4 py-2 border border-green-300 text-sm font-medium rounded-md text-green-700 bg-white hover:bg-green-50">
                            Add Another
                        </a>
                    </div>
                </div>
            </div>
        </div>
        """

        return HTMLResponse(content=success_html)

    except Exception as e:
        error_html = f"""
        <div class="bg-red-50 border border-red-200 rounded-lg p-6">
            <h3 class="text-lg font-medium text-red-800 mb-2">Save Error</h3>
            <p class="text-red-600">An error occurred while saving the article: {str(e)}</p>
        </div>
        """
        return HTMLResponse(content=error_html)


async def save_article_with_background_downloads(
    request: Request,
    doi: str = Form(...),
    title: str = Form(...),
    journal: str = Form(None),
    year: int = Form(None),
    # ... other form fields
    db: Session = Depends(get_db),
    # ... same parameters as above
):
    """
    Version with background downloads (non-blocking).

    Use this if you want the user to see immediate success
    while downloads happen in the background.
    """
    try:
        # Save article (your existing code)
        article = articles_crud.create_article_with_authors(
            db=db, article=article_data, authors=authors_data
        )

        # 🎯 NEW: Schedule background downloads
        task_id = await trigger_background_downloads(
            doi=article.doi, crossref_data=None
        )

        logger.info(f"Scheduled background downloads for {article.doi}: {task_id}")

        # Return immediate success
        return HTMLResponse(
            content=f"""
            <div class="bg-green-50 border border-green-200 rounded-lg p-6">
                <div class="flex">
                    <div class="flex-shrink-0">
                        <span class="text-green-400 text-2xl">✅</span>
                    </div>
                    <div class="ml-3">
                        <h3 class="text-lg font-medium text-green-800">Article Registered Successfully!</h3>
                        <p class="mt-2 text-sm text-green-700">
                            <strong>DOI:</strong> {article.doi}<br>
                            <strong>Title:</strong> {article.title}<br>
                            <strong>Authors:</strong> {len(authors_data)} author(s) added
                        </p>
                        <div class="mt-3 text-sm text-green-600">
                            <strong>File Downloads:</strong> Starting in background...
                        </div>
                        <div class="mt-4">
                            <a href="/search" class="text-green-600 hover:text-green-500 font-medium">
                                View in search results →
                            </a>
                        </div>
                    </div>
                </div>
            </div>
            """
        )

    except Exception:
        # Same error handling as above
        pass
