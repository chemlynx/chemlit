"""Simplified CrossRef service."""

import re

import httpx
from pydantic import ValidationError

from chemlit_extractor.core.config import settings
from chemlit_extractor.models.schemas import (
    ArticleCreate,
    AuthorCreate,
    CrossRefResponse,
)

# Import our simplified utilities (these would be in services/utils.py)
from .utils import enhance_article_with_journal, extract_year_from_crossref


class CrossRefService:
    """Simplified CrossRef service for fetching article metadata."""

    BASE_URL = "https://api.crossref.org/works"

    def __init__(self):
        """Initialize with HTTP client."""
        self.client = httpx.Client(
            headers={
                "User-Agent": settings.crossref_user_agent,
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        """Close HTTP client."""
        self.client.close()

    def fetch_and_convert_article(
        self, doi: str
    ) -> tuple[ArticleCreate, list[AuthorCreate]] | None:
        """
        Fetch article from CrossRef and convert to our schemas.

        Args:
            doi: DOI to fetch

        Returns:
            Tuple of (ArticleCreate, list of AuthorCreate) or None
        """
        # Clean DOI
        clean_doi = self._clean_doi(doi)
        if not clean_doi:
            return None

        # Fetch from CrossRef
        try:
            response = self.client.get(f"{self.BASE_URL}/{clean_doi}")
            response.raise_for_status()

            data = response.json()
            crossref_data = CrossRefResponse.model_validate(data.get("message", {}))

        except (httpx.HTTPError, ValidationError):
            return None

        # Convert to our schemas
        article = self._create_article(crossref_data, clean_doi)
        authors = self._create_authors(crossref_data)

        return article, authors

    def _clean_doi(self, doi: str) -> str | None:
        """Clean and validate DOI."""
        if not doi:
            return None

        # Remove common prefixes
        doi = doi.strip().lower()
        for prefix in ["https://doi.org/", "http://doi.org/", "doi:"]:
            if doi.startswith(prefix):
                doi = doi[len(prefix) :]

        # Basic validation
        if not doi.startswith("10."):
            return None

        return doi

    def _create_article(self, data: CrossRefResponse, doi: str) -> ArticleCreate:
        """Convert CrossRef data to ArticleCreate."""
        # Extract basic fields
        title = data.title[0] if data.title else "Unknown Title"
        journal = data.container_title[0] if data.container_title else None

        # Extract year using our utility
        year = extract_year_from_crossref(data)

        # Clean up abstract (remove JATS markup)
        abstract = self._clean_abstract(data.abstract) if data.abstract else None

        article = ArticleCreate(
            doi=doi,
            title=title,
            journal=journal,
            year=year,
            volume=data.volume,
            issue=data.issue,
            pages=data.page,
            abstract=abstract,
            url=data.URL,
            publisher=data.publisher,
        )

        # Enhance with journal mapping if needed
        enhance_article_with_journal(article, doi)

        return article

    def _create_authors(self, data: CrossRefResponse) -> list[AuthorCreate]:
        """Convert CrossRef authors to AuthorCreate list."""
        if not data.author:
            return []

        authors = []
        for author_data in data.author:
            # Clean up ORCID
            orcid = None
            if author_data.ORCID:
                orcid = author_data.ORCID.replace("http://orcid.org/", "")
                orcid = orcid.replace("https://orcid.org/", "")

            authors.append(
                AuthorCreate(
                    first_name=author_data.given or "Unknown",
                    last_name=author_data.family or "Unknown",
                    orcid=orcid,
                )
            )

        return authors

    def _clean_abstract(self, abstract: str) -> str:
        """Remove JATS markup from abstract."""
        if not abstract:
            return abstract

        # Remove common JATS tags
        abstract = re.sub(r"</?jats:[^>]+>", "", abstract)
        abstract = re.sub(r"</?[^>]+>", "", abstract)  # Remove any remaining tags

        return abstract.strip()
