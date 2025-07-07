"""Pydantic schemas for data validation and serialization."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


class ExtractionMethod(str, Enum):
    """Methods for compound structure extraction."""

    DECIMER = "decimer"
    NAME_TO_STRUCTURE = "name_to_structure"
    MANUAL = "manual"


# Base Models
class BaseSchema(BaseModel):
    """Base schema with common configuration."""

    model_config = {
        "from_attributes": True,
        "validate_assignment": True,
        "str_strip_whitespace": True,
    }


# Author Models
class AuthorBase(BaseSchema):
    """Base author schema."""

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    orcid: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=255)


class AuthorCreate(AuthorBase):
    """Schema for creating authors."""

    pass


class AuthorUpdate(BaseSchema):
    """Schema for updating authors."""

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    orcid: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=255)


class Author(AuthorBase):
    """Complete author schema."""

    id: int
    created_at: datetime
    updated_at: datetime


# Article Models
class ArticleBase(BaseSchema):
    """Base article schema."""

    title: str = Field(..., min_length=1, max_length=1000)
    journal: str | None = Field(default=None, max_length=255)
    year: int | None = Field(default=None, ge=1900, le=2030)
    volume: str | None = Field(default=None, max_length=50)
    issue: str | None = Field(default=None, max_length=50)
    pages: str | None = Field(default=None, max_length=50)
    abstract: str | None = Field(default=None, max_length=10000)
    url: str | None = Field(default=None, max_length=500)
    publisher: str | None = Field(default=None, max_length=255)


class ArticleCreate(ArticleBase):
    """Schema for creating articles."""

    doi: str = Field(..., min_length=5, max_length=255)

    @field_validator("doi")
    @classmethod
    def validate_doi(cls, v: str) -> str:
        """Validate and normalize DOI format."""
        doi = v.strip().lower()
        print(f"{doi=}")
        if not doi.startswith("10."):
            raise ValueError("DOI must start with '10.'")
        return doi

    @model_validator(mode="before")
    @classmethod
    def convert_url_to_string(cls, values):
        """Convert HttpUrl to string for database compatibility."""
        if isinstance(values, dict) and "url" in values:
            url = values["url"]
            if hasattr(url, "__str__"):  # HttpUrl object
                values["url"] = str(url)
        return values


class ArticleUpdate(BaseSchema):
    """Schema for updating articles."""

    title: str | None = Field(default=None, min_length=1, max_length=1000)
    journal: str | None = Field(default=None, max_length=255)
    # journalabb: str | None = Field(default=None, max_length=155)
    year: int | None = Field(default=None, ge=1900, le=2030)
    volume: str | None = Field(default=None, max_length=50)
    issue: str | None = Field(default=None, max_length=50)
    pages: str | None = Field(default=None, max_length=50)
    abstract: str | None = Field(default=None, max_length=10000)
    url: HttpUrl | None = Field(default=None)
    publisher: str | None = Field(default=None, max_length=255)


class Article(ArticleBase):
    """Complete article schema."""

    doi: str
    created_at: datetime
    updated_at: datetime
    authors: list[Author] = Field(default_factory=list)


# Compound Models
class CompoundBase(BaseSchema):
    """Base compound schema."""

    name: str = Field(..., min_length=1, max_length=500)
    original_structure: str | None = Field(default=None, max_length=10000)
    final_structure: str | None = Field(default=None, max_length=10000)
    extraction_method: ExtractionMethod | None = Field(default=None)
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    notes: str | None = Field(default=None, max_length=2000)


class CompoundCreate(CompoundBase):
    """Schema for creating compounds."""

    article_doi: str = Field(..., min_length=1, max_length=255)


class CompoundUpdate(BaseSchema):
    """Schema for updating compounds."""

    name: str | None = Field(default=None, min_length=1, max_length=500)
    original_structure: str | None = Field(default=None, max_length=10000)
    final_structure: str | None = Field(default=None, max_length=10000)
    extraction_method: ExtractionMethod | None = Field(default=None)
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    notes: str | None = Field(default=None, max_length=2000)


class Compound(CompoundBase):
    """Complete compound schema."""

    id: int
    article_doi: str
    created_at: datetime
    updated_at: datetime


# Compound Property Models
class CompoundPropertyBase(BaseSchema):
    """Base compound property schema."""

    property_name: str = Field(..., min_length=1, max_length=255)
    value: str = Field(..., min_length=1, max_length=1000)
    units: str | None = Field(default=None, max_length=50)
    measurement_type: str | None = Field(default=None, max_length=100)
    conditions: str | None = Field(default=None, max_length=1000)
    source_text: str | None = Field(default=None, max_length=2000)


class CompoundPropertyCreate(CompoundPropertyBase):
    """Schema for creating compound properties."""

    compound_id: int = Field(..., gt=0)


class CompoundPropertyUpdate(BaseSchema):
    """Schema for updating compound properties."""

    property_name: str | None = Field(default=None, min_length=1, max_length=255)
    value: str | None = Field(default=None, min_length=1, max_length=1000)
    units: str | None = Field(default=None, max_length=50)
    measurement_type: str | None = Field(default=None, max_length=100)
    conditions: str | None = Field(default=None, max_length=1000)
    source_text: str | None = Field(default=None, max_length=2000)


class CompoundProperty(CompoundPropertyBase):
    """Complete compound property schema."""

    id: int
    compound_id: int
    created_at: datetime
    updated_at: datetime


# Search and Response Models
class ArticleSearchQuery(BaseSchema):
    """Schema for article search queries."""

    doi: str | None = Field(default=None, min_length=5, max_length=255)
    author: str | None = Field(default=None, min_length=1, max_length=200)
    year: int | None = Field(default=None, ge=1800, le=2030)
    journal: str | None = Field(default=None, min_length=1, max_length=255)
    title: str | None = Field(default=None, min_length=1, max_length=500)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ArticleSearchResponse(BaseSchema):
    """Schema for article search responses."""

    articles: list[Article]
    total_count: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)


class DatabaseStats(BaseSchema):
    """Schema for database statistics."""

    total_articles: int = Field(..., ge=0)
    total_compounds: int = Field(..., ge=0)
    total_properties: int = Field(..., ge=0)
    total_authors: int = Field(..., ge=0)


# CrossRef API Models
class CrossRefAuthor(BaseSchema):
    """CrossRef author data."""

    given: str | None = Field(default=None)
    family: str | None = Field(default=None)
    ORCID: str | None = Field(default=None)


class CrossRefResponse(BaseSchema):
    """CrossRef API response data."""

    DOI: str
    title: list[str] | None = Field(default=None)
    author: list[CrossRefAuthor] | None = Field(default=None)
    published_print: dict[str, Any] | None = Field(default=None)
    published_online: dict[str, Any] | None = Field(default=None)
    container_title: list[str] | None = Field(default=None)
    short_container_title: list[str] | None = Field(default=None)
    publisher: str | None = Field(default=None)
    volume: str | None = Field(default=None)
    issue: str | None = Field(default=None)
    page: str | None = Field(default=None)
    abstract: str | None = Field(default=None)
    URL: str | None = Field(default=None)
    published: dict[str, Any] | None = None


class ArticleCreateWithFiles(BaseSchema):
    """Schema for creating articles with optional file downloads."""

    doi: str = Field(
        ..., min_length=5, max_length=255, description="DOI to fetch from CrossRef"
    )
    pdf_url: str | None = Field(default=None, description="URL to PDF file")
    html_url: str | None = Field(default=None, description="URL to HTML file")
    supplementary_urls: list[str] = Field(
        default_factory=list, description="URLs to supplementary files"
    )
    download_files: bool = Field(
        default=True, description="Whether to trigger file downloads"
    )

    @field_validator("doi")
    @classmethod
    def validate_doi(cls, v: str) -> str:
        """Validate and normalize DOI format."""
        doi = v.strip().lower()
        if not doi.startswith("10."):
            raise ValueError("DOI must start with '10.'")
        return doi


class ArticleCreateResponse(BaseSchema):
    """Response for article creation with file download status."""

    article: Article
    download_triggered: bool = Field(default=False)
    download_count: int = Field(default=0, ge=0)
    download_message: str | None = Field(default=None)


class ArticleRegistrationData(BaseSchema):
    """
    Complete data for registering an article with authors.
    This represents the atomic unit of article creation.
    """

    doi: str = Field(..., min_length=5, max_length=255)
    title: str = Field(..., min_length=1, max_length=1000)
    journal: str | None = Field(default=None, max_length=255)
    year: int | None = Field(default=None, ge=1900, le=2030)
    volume: str | None = Field(default=None, max_length=50)
    issue: str | None = Field(default=None, max_length=50)
    pages: str | None = Field(default=None, max_length=50)
    abstract: str | None = Field(default=None, max_length=10000)
    url: str | None = Field(default=None, max_length=500)
    publisher: str | None = Field(default=None, max_length=255)
    authors: list[AuthorCreate] = Field(
        ..., min_items=1
    )  # Required, must have at least one!

    @field_validator("doi")
    @classmethod
    def validate_doi(cls, v: str) -> str:
        """Validate and normalize DOI format."""
        doi = v.strip().lower()
        if not doi.startswith("10."):
            raise ValueError("DOI must start with '10.'")
        return doi

    @field_validator("authors")
    @classmethod
    def validate_authors(cls, v: list[AuthorCreate]) -> list[AuthorCreate]:
        """Ensure we have at least one valid author."""
        if not v:
            raise ValueError("Articles must have at least one author")

        # Filter out any completely empty authors
        valid_authors = [
            author
            for author in v
            if author.first_name.strip() or author.last_name.strip()
        ]

        if not valid_authors:
            raise ValueError("Articles must have at least one author with a name")

        return valid_authors
