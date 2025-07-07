from fastapi import APIRouter, Depends, HTTPException, Query, Response, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy.orm import Session
import logging
import json

from chemlit_extractor.database import CompoundCRUD, get_db
from chemlit_extractor.models.schemas import (
    Article,
    ArticleCreate,
    ArticleSearchQuery,
    ArticleSearchResponse,
    AuthorCreate,
    ArticleRegistrationData,
)
from chemlit_extractor.services.article_service import (
    ArticleRegistrationResult,
    ArticleService,
    FileUrls,
    get_article_service_dependency,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class ArticleCreateRequest(BaseModel):
    """Unified request for article creation - focused on registration_data format."""

    # New unified format (primary)
    registration_data: ArticleRegistrationData | None = Field(
        None, description="Complete article data including authors"
    )

    # Simple DOI format (for CrossRef lookup)
    doi: str | None = Field(None, description="DOI to fetch from CrossRef")

    # Common options
    download_files: bool = Field(
        default=False, description="Download files after registration"
    )
    file_urls: FileUrls | None = Field(default=None, description="Optional file URLs")

    @model_validator(mode="after")
    def validate_request(self):
        """Ensure we have valid data."""
        if not self.registration_data and not self.doi:
            raise ValueError("Either 'registration_data' or 'doi' must be provided")
        return self


@router.post("/", response_model=ArticleRegistrationResult)
async def create_article(
    request: Request,
    response: Response,
    article_service: ArticleService = Depends(get_article_service_dependency),
) -> ArticleRegistrationResult:
    """
    Register an article as an atomic unit with its authors.
    Expects registration_data format from HTMX form.
    """
    try:
        # Get the raw body for debugging
        body = await request.body()
        content_type = request.headers.get("content-type", "")

        logger.info(f"Content-Type: {content_type}")
        logger.info(f"Raw body (first 200 chars): {body.decode()[:200]}...")

        # Parse JSON data
        if "application/json" in content_type:
            try:
                data = json.loads(body.decode())
                logger.info(f"Successfully parsed JSON data")
                logger.info(f"Data keys: {list(data.keys())}")

                # Log the registration_data structure
                if "registration_data" in data:
                    reg_data = data["registration_data"]
                    logger.info(f"Registration data keys: {list(reg_data.keys())}")
                    logger.info(f"Authors count: {len(reg_data.get('authors', []))}")

            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error: {e}")
                raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")
        else:
            logger.error(f"Expected JSON content type, got: {content_type}")
            raise HTTPException(
                status_code=400, detail=f"Expected application/json, got {content_type}"
            )

        # Create and validate request
        try:
            article_request = ArticleCreateRequest(**data)
            logger.info(f"Successfully created ArticleCreateRequest")
        except ValidationError as e:
            logger.error(f"Validation error: {e.errors()}")
            raise HTTPException(
                status_code=422,
                detail={"message": "Validation failed", "errors": e.errors()},
            )

        # Process the registration
        if article_request.doi and not article_request.registration_data:
            # Simple DOI lookup
            logger.info(f"Processing DOI lookup: {article_request.doi}")
            result = article_service.register_article_from_doi(
                doi=article_request.doi,
                download_files=article_request.download_files,
                file_urls=article_request.file_urls,
            )
        else:
            # Direct registration with provided data
            logger.info(f"Processing direct registration")
            result = article_service.register_article_with_data(
                registration_data=article_request.registration_data,
                download_files=article_request.download_files,
                file_urls=article_request.file_urls,
            )

        # Set appropriate status code
        if result.status == "already_exists":
            response.status_code = 200
        elif result.status == "success":
            response.status_code = 201
        else:
            if "not found" in result.message.lower():
                raise HTTPException(status_code=404, detail=result.message)
            elif "invalid" in result.message.lower():
                raise HTTPException(status_code=400, detail=result.message)
            else:
                raise HTTPException(status_code=500, detail=result.message)

        logger.info(f"Registration successful: {result.status}")
        return result

    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.error(f"Unexpected error in create_article: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
    """Search articles - keeping the existing search logic."""
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
