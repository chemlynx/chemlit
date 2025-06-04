"""SQLAlchemy database models."""

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Mapped, mapped_column, relationship

Base = declarative_base()

# Association table for many-to-many relationship between articles and authors
article_authors = Table(
    "article_authors",
    Base.metadata,
    Column("article_doi", String(255), ForeignKey("articles.doi"), primary_key=True),
    Column("author_id", Integer, ForeignKey("authors.id"), primary_key=True),
    Column("author_order", Integer, nullable=False, default=0),
    Column("created_at", DateTime, default=func.now()),
)


class Author(Base):
    """Author database model."""

    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    orcid: Mapped[str | None] = mapped_column(String(50), nullable=True, unique=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )

    # Relationships
    articles: Mapped[list["Article"]] = relationship(
        "Article", secondary=article_authors, back_populates="authors"
    )

    def __repr__(self) -> str:
        """String representation of Author."""
        return f"<Author(id={self.id}, name='{self.first_name} {self.last_name}')>"


class Article(Base):
    """Article database model."""

    __tablename__ = "articles"

    doi: Mapped[str] = mapped_column(String(255), primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    journal: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    volume: Mapped[str | None] = mapped_column(String(50), nullable=True)
    issue: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pages: Mapped[str | None] = mapped_column(String(50), nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )

    # Relationships
    authors: Mapped[list[Author]] = relationship(
        Author, secondary=article_authors, back_populates="articles"
    )
    compounds: Mapped[list["Compound"]] = relationship(
        "Compound", back_populates="article", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """String representation of Article."""
        return f"<Article(doi='{self.doi}', title='{self.title[:50]}...')>"


class Compound(Base):
    """Compound database model."""

    __tablename__ = "compounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    article_doi: Mapped[str] = mapped_column(
        String(255), ForeignKey("articles.doi"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    original_structure: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_structure: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )

    # Relationships
    article: Mapped[Article] = relationship("Article", back_populates="compounds")
    properties: Mapped[list["CompoundProperty"]] = relationship(
        "CompoundProperty", back_populates="compound", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """String representation of Compound."""
        return f"<Compound(id={self.id}, name='{self.name}', article='{self.article_doi}')>"


class CompoundProperty(Base):
    """Compound property database model."""

    __tablename__ = "compound_properties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    compound_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("compounds.id"), nullable=False, index=True
    )
    property_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    value: Mapped[str] = mapped_column(String(1000), nullable=False)
    units: Mapped[str | None] = mapped_column(String(50), nullable=True)
    measurement_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )

    # Relationships
    compound: Mapped[Compound] = relationship("Compound", back_populates="properties")

    def __repr__(self) -> str:
        """String representation of CompoundProperty."""
        return (
            f"<CompoundProperty(id={self.id}, "
            f"property='{self.property_name}', "
            f"value='{self.value}')>"
        )
