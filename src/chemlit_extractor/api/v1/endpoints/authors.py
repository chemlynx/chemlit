"""API endpoints for author operations."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from chemlit_extractor.database import AuthorCRUD, get_db
from chemlit_extractor.models.schemas import Author, AuthorCreate, AuthorUpdate

router = APIRouter()


@router.get("/", response_model=list[Author])
def get_authors(
    skip: int = Query(0, ge=0, description="Number of authors to skip"),
    limit: int = Query(
        100, ge=1, le=1000, description="Maximum number of authors to return"
    ),
    db: Session = Depends(get_db),
) -> list[Author]:
    """
    Get authors with pagination.

    Authors are ordered by last name, then first name.

    Args:
        skip: Number of authors to skip.
        limit: Maximum number of authors to return.

    Returns:
        List of authors.
    """
    return AuthorCRUD.get_multi(db, skip=skip, limit=limit)


@router.get("/{author_id}", response_model=Author)
def get_author(
    author_id: int,
    db: Session = Depends(get_db),
) -> Author:
    """
    Get a specific author by ID.

    Args:
        author_id: ID of the author to retrieve.

    Returns:
        Author details.

    Raises:
        404: If author with the given ID is not found.
    """
    author = AuthorCRUD.get_by_id(db, author_id)
    if not author:
        raise HTTPException(
            status_code=404, detail=f"Author with ID {author_id} not found"
        )
    return author


@router.post("/", response_model=Author, status_code=201)
def create_author(
    author: AuthorCreate,
    db: Session = Depends(get_db),
) -> Author:
    """
    Create a new author.

    Note: This endpoint creates a new author directly.
    Authors are usually created automatically when adding articles from CrossRef.

    Args:
        author: Author data to create.

    Returns:
        Created author with assigned ID and timestamps.
    """
    return AuthorCRUD.create(db, author)


@router.put("/{author_id}", response_model=Author)
def update_author(
    author_id: int,
    author_update: AuthorUpdate,
    db: Session = Depends(get_db),
) -> Author:
    """
    Update an existing author.

    Args:
        author_id: ID of the author to update.
        author_update: Updated author data.

    Returns:
        Updated author.

    Raises:
        404: If author with the given ID is not found.
    """
    updated_author = AuthorCRUD.update(db, author_id, author_update)
    if not updated_author:
        raise HTTPException(
            status_code=404, detail=f"Author with ID {author_id} not found"
        )
    return updated_author


@router.delete("/{author_id}", status_code=204)
def delete_author(
    author_id: int,
    db: Session = Depends(get_db),
) -> None:
    """
    Delete an author.

    Warning: This will remove the author from all articles.
    Use with caution as this may affect data integrity.

    Args:
        author_id: ID of the author to delete.

    Raises:
        404: If author with the given ID is not found.
    """
    success = AuthorCRUD.delete(db, author_id)
    if not success:
        raise HTTPException(
            status_code=404, detail=f"Author with ID {author_id} not found"
        )
