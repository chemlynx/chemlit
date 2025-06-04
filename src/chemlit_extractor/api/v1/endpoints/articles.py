"""API endpoints for article operations."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from chemlit_extractor.database import ArticleCRUD, CompoundCRUD, get_db
from chemlit_extractor.models.schemas import (
    Article,
    ArticleCreate,
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
