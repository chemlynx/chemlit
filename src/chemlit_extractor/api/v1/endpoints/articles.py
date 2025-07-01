from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from chemlit_extractor.database import CompoundCRUD, get_db
from chemlit_extractor.models.schemas import (
    Article,
    ArticleSearchQuery,
    ArticleSearchResponse,
)
from chemlit_extractor.services.article_service import (
    ArticleRegistrationResult,
    ArticleService,
    FileUrls,
    get_article_service_dependency,
)

router = APIRouter()


# Simplified request model
class ArticleCreateRequest(BaseModel):
    """Simplified request for article creation."""

    doi: str = Field(..., description="Article DOI")
    fetch_from_crossref: bool = Field(default=True, description="Fetch from CrossRef")
    download_files: bool = Field(default=False, description="Download files")
    file_urls: FileUrls | None = Field(default=None, description="File URLs")


@router.post("/", response_model=ArticleRegistrationResult, status_code=201)
def create_article(
    request: ArticleCreateRequest,
    article_service: ArticleService = Depends(get_article_service_dependency),
) -> ArticleRegistrationResult:
    """
    Create an article - MUCH SIMPLER than before!

    All the complexity is now handled by ArticleService:
    - DOI validation and cleaning
    - Duplicate checking
    - CrossRef fetching
    - Transaction management
    - File downloads
    - Error handling
    """
    result = article_service.register_article(
        doi=request.doi,
        fetch_metadata=request.fetch_from_crossref,
        download_files=request.download_files,
        file_urls=request.file_urls,
    )

    # Simple status code mapping
    if result.status == "error":
        if "not found" in result.message.lower():
            raise HTTPException(status_code=404, detail=result.message)
        elif "invalid doi" in result.message.lower():
            raise HTTPException(status_code=400, detail=result.message)
        else:
            raise HTTPException(status_code=500, detail=result.message)

    return result


@router.get("/{doi:path}", response_model=Article)
def get_article(
    doi: str,
    article_service: ArticleService = Depends(get_article_service_dependency),
) -> Article:
    """Get article by DOI - simplified."""
    article = article_service.get_article(doi)
    if not article:
        raise HTTPException(
            status_code=404, detail=f"Article with DOI '{doi}' not found"
        )
    return article


@router.get("/", response_model=ArticleSearchResponse)
def search_articles(
    doi: str | None = Query(None, description="DOI to search for"),
    title: str | None = Query(None, description="Title keywords"),
    author: str | None = Query(None, description="Author name"),
    journal: str | None = Query(None, description="Journal name"),
    year: int | None = Query(None, description="Publication year"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    offset: int = Query(0, ge=0, description="Results to skip"),
    db: Session = Depends(get_db),
) -> ArticleSearchResponse:
    """
    Search articles - keeping the existing search logic.

    Note: Search functionality could also be moved to ArticleService
    in a future refactor for consistency.
    """
    from chemlit_extractor.database import ArticleCRUD

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
