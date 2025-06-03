"""Database package initialization."""

from chemlit_extractor.database.connection import (
    create_tables,
    get_db,
    get_db_session,
    engine,
    SessionLocal,
)
from chemlit_extractor.database.models import (
    Article,
    Author,
    Base,
    Compound,
    CompoundProperty,
    article_authors,
)
from chemlit_extractor.database.crud import (
    ArticleCRUD,
    AuthorCRUD,
    CompoundCRUD,
    CompoundPropertyCRUD,
    get_database_stats,
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
