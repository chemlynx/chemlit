"""Database package initialization."""

from chemlit_extractor.database.connection import (
    SessionLocal,
    create_tables,
    engine,
    get_db,
    get_db_session,
)
from chemlit_extractor.database.crud import (
    ArticleCRUD,
    AuthorCRUD,
    CompoundCRUD,
    CompoundPropertyCRUD,
    get_database_stats,
)
from chemlit_extractor.database.models import (
    Article,
    Author,
    Base,
    Compound,
    CompoundProperty,
    article_authors,
)

__all__ = [
    "Article",
    "ArticleCRUD",
    "Author",
    "AuthorCRUD",
    "Base",
    "Compound",
    "CompoundCRUD",
    "CompoundProperty",
    "CompoundPropertyCRUD",
    "article_authors",
    "create_tables",
    "engine",
    "get_database_stats",
    "get_db",
    "get_db_session",
    "SessionLocal",
]
