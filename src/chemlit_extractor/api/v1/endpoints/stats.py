"""API endpoints for database statistics."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from chemlit_extractor.database import get_database_stats, get_db
from chemlit_extractor.models.schemas import DatabaseStats

router = APIRouter()


@router.get("/", response_model=DatabaseStats)
def get_stats(db: Session = Depends(get_db)) -> DatabaseStats:
    """
    Get database statistics.

    Returns counts of articles, compounds, properties, and authors
    currently stored in the database.

    Returns:
        Database statistics including total counts.
    """
    return get_database_stats(db)


@router.get("/summary")
def get_stats_summary(db: Session = Depends(get_db)) -> dict[str, str | int]:
    """
    Get a human-readable summary of database statistics.

    Returns:
        Dictionary with formatted statistics and summary message.
    """
    stats = get_database_stats(db)

    # Calculate some derived stats
    avg_compounds_per_article = 0.0
    if stats.total_articles > 0:
        avg_compounds_per_article = stats.total_compounds / stats.total_articles

    avg_properties_per_compound = 0.0
    if stats.total_compounds > 0:
        avg_properties_per_compound = stats.total_properties / stats.total_compounds

    return {
        "total_articles": stats.total_articles,
        "total_compounds": stats.total_compounds,
        "total_properties": stats.total_properties,
        "total_authors": stats.total_authors,
        "avg_compounds_per_article": round(avg_compounds_per_article, 2),
        "avg_properties_per_compound": round(avg_properties_per_compound, 2),
        "summary": (
            f"Database contains {stats.total_articles} articles with "
            f"{stats.total_compounds} compounds and {stats.total_properties} properties, "
            f"authored by {stats.total_authors} unique authors."
        ),
    }
