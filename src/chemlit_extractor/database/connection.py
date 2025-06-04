"""Database connection and session management."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from chemlit_extractor.core.config import settings
from chemlit_extractor.database.models import Base

# Create database engine
engine = create_engine(
    settings.database_url,
    echo=settings.debug,  # Show SQL queries in debug mode
    pool_pre_ping=True,  # Verify connections before use
    pool_recycle=300,  # Recycle connections every 5 minutes
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables() -> None:
    """Create all database tables."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session]:
    """
    Get database session for dependency injection.

    Yields:
        Database session that is automatically closed after use.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session() -> Session:
    """
    Get a database session for direct use.

    Returns:
        Database session that must be manually closed.

    Note:
        Remember to close the session when done:
        ```python
        db = get_db_session()
        try:
            # Use db here
            pass
        finally:
            db.close()
        ```
    """
    return SessionLocal()
