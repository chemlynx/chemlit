"""CrossRef API client for fetching article metadata."""

import time
from datetime import datetime, timedelta
from typing import Any

import httpx
from pydantic import ValidationError

from chemlit_extractor.core.config import settings
from chemlit_extractor.models.schemas import (
    ArticleCreate,
    AuthorCreate,
    CrossRefResponse,
)


class RateLimiter:
    """Simple rate limiter for API requests."""

    def __init__(self, max_requests: int, time_window: timedelta) -> None:
        """
        Initialize rate limiter.

        Args:
            max_requests: Maximum number of requests allowed in time window.
            time_window: Time window for rate limiting.
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests: list[datetime] = []

    def can_make_request(self) -> bool:
        """
        Check if a request can be made without exceeding rate limit.

        Returns:
            True if request can be made, False otherwise.
        """
        now = datetime.now()
        cutoff = now - self.time_window

        # Remove old requests outside the time window
        self.requests = [req_time for req_time in self.requests if req_time > cutoff]

        return len(self.requests) < self.max_requests

    def record_request(self) -> None:
        """Record that a request was made."""
        self.requests.append(datetime.now())

    def wait_time(self) -> float:
        """
        Get the time to wait before next request can be made.

        Returns:
            Time to wait in seconds, 0 if no wait needed.
        """
        if self.can_make_request():
            return 0.0

        if not self.requests:
            return 0.0

        oldest_request = min(self.requests)
        wait_until = oldest_request + self.time_window
        now = datetime.now()

        if wait_until <= now:
            return 0.0

        return (wait_until - now).total_seconds()


class CrossRefClient:
    """Client for interacting with CrossRef API."""

    def __init__(
        self, rate_limit: int | None = None, user_agent: str | None = None
    ) -> None:
        """
        Initialize CrossRef client with rate limiting.

        Args:
            rate_limit: Maximum requests per minute (default from settings).
            user_agent: User agent string (default from settings).
        """
        self.base_url = "https://api.crossref.org"
        self.user_agent = user_agent or settings.crossref_user_agent
        self.rate_limiter = RateLimiter(
            max_requests=rate_limit or settings.crossref_rate_limit,
            time_window=timedelta(minutes=1),
        )

        # Configure HTTP client
        self.client = httpx.Client(
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    def __enter__(self) -> "CrossRefClient":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.client.close()

    def _wait_for_rate_limit(self) -> None:
        """Wait if necessary to respect rate limits."""
        wait_time = self.rate_limiter.wait_time()
        if wait_time > 0:
            time.sleep(wait_time)

    def get_article_by_doi(self, doi: str) -> CrossRefResponse | None:
        """
        Fetch article metadata from CrossRef API by DOI.

        Args:
            doi: Digital Object Identifier for the article.

        Returns:
            CrossRef response data or None if not found/error.

        Raises:
            httpx.HTTPError: If there's an HTTP error.
            ValueError: If DOI format is invalid.
        """
        # Validate and clean DOI
        clean_doi = self._clean_doi(doi)
        if not clean_doi:
            raise ValueError(f"Invalid DOI format: {doi}")

        # Check rate limit
        self._wait_for_rate_limit()

        # Make API request
        url = f"{self.base_url}/works/{clean_doi}"

        try:
            self.rate_limiter.record_request()
            response = self.client.get(url)
            response.raise_for_status()

            data = response.json()
            work_data = data.get("message", {})

            # Parse and validate response
            return CrossRefResponse.model_validate(work_data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise httpx.HTTPError(f"HTTP {e.response.status_code}: {e.response.text}")
        except (httpx.HTTPError, ValidationError) as e:
            raise httpx.HTTPError(f"Failed to fetch article data: {e}") from e

    def search_articles(
        self, query: str, limit: int = 20, offset: int = 0
    ) -> list[CrossRefResponse]:
        """
        Search for articles using CrossRef API.

        Args:
            query: Search query string.
            limit: Maximum number of results to return.
            offset: Number of results to skip.

        Returns:
            List of CrossRef response data.

        Raises:
            httpx.HTTPError: If there's an HTTP error.
        """
        # Check rate limit
        self._wait_for_rate_limit()

        # Prepare search parameters
        params = {
            "query": query,
            "rows": min(limit, 1000),  # CrossRef API limit
            "offset": offset,
        }

        url = f"{self.base_url}/works"

        try:
            self.rate_limiter.record_request()
            response = self.client.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            works = data.get("message", {}).get("items", [])

            # Parse and validate responses
            articles = []
            for work in works:
                try:
                    article = CrossRefResponse.model_validate(work)
                    articles.append(article)
                except ValidationError:
                    # Skip invalid entries
                    continue

            return articles

        except httpx.HTTPError as e:
            raise httpx.HTTPError(f"Failed to search articles: {e}") from e

    @staticmethod
    def _clean_doi(doi: str) -> str | None:
        """
        Clean and validate DOI format.

        Args:
            doi: Raw DOI string.

        Returns:
            Cleaned DOI or None if invalid.
        """
        if not doi:
            return None

        # Remove common prefixes and clean
        doi = doi.strip().lower()

        # Remove URL prefixes
        prefixes_to_remove = [
            "https://doi.org/",
            "http://doi.org/",
            "https://dx.doi.org/",
            "http://dx.doi.org/",
            "doi:",
        ]

        for prefix in prefixes_to_remove:
            if doi.startswith(prefix):
                doi = doi[len(prefix) :]
                break

        # Validate DOI format (must start with 10.)
        if not doi.startswith("10."):
            return None

        return doi

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()


class CrossRefService:
    """Service layer for CrossRef operations with database integration."""

    def __init__(self, client: CrossRefClient | None = None) -> None:
        """
        Initialize CrossRef service.

        Args:
            client: CrossRef client instance (creates new one if None).
        """
        self.client = client or CrossRefClient()

    def fetch_and_convert_article(
        self, doi: str
    ) -> tuple[ArticleCreate, list[AuthorCreate]] | None:
        """
        Fetch article from CrossRef and convert to our schema format.

        Args:
            doi: DOI to fetch.

        Returns:
            Tuple of (ArticleCreate, list of AuthorCreate) or None if not found.

        Raises:
            httpx.HTTPError: If there's an API error.
            ValueError: If DOI format is invalid.
        """
        crossref_data = self.client.get_article_by_doi(doi)
        if not crossref_data:
            return None

        # Convert CrossRef data to our schemas
        article_data = self._convert_crossref_to_article(crossref_data)
        authors_data = self._convert_crossref_to_authors(crossref_data)

        return article_data, authors_data

    def _convert_crossref_to_article(
        self, crossref_data: CrossRefResponse
    ) -> ArticleCreate:
        """
        Convert CrossRef response to ArticleCreate schema.

        Args:
            crossref_data: CrossRef API response.

        Returns:
            ArticleCreate instance.
        """
        # Extract title (CrossRef returns list, we want first one)
        title = "Unknown Title"
        if crossref_data.title and len(crossref_data.title) > 0:
            title = crossref_data.title[0]

        # Extract journal name
        journal = None
        if crossref_data.container_title and len(crossref_data.container_title) > 0:
            journal = crossref_data.container_title[0]

        # Extract publication year
        year = None
        if crossref_data.published_print:
            date_parts = crossref_data.published_print.get("date-parts", [])
            if date_parts and len(date_parts) > 0 and len(date_parts[0]) > 0:
                year = date_parts[0][0]
        elif crossref_data.published_online:
            date_parts = crossref_data.published_online.get("date-parts", [])
            if date_parts and len(date_parts) > 0 and len(date_parts[0]) > 0:
                year = date_parts[0][0]

        return ArticleCreate(
            doi=crossref_data.DOI.lower(),
            title=title,
            journal=journal,
            year=year,
            volume=crossref_data.volume,
            issue=crossref_data.issue,
            pages=crossref_data.page,
            abstract=crossref_data.abstract,
            url=crossref_data.URL,
            publisher=crossref_data.publisher,
        )

    def _convert_crossref_to_authors(
        self, crossref_data: CrossRefResponse
    ) -> list[AuthorCreate]:
        """
        Convert CrossRef authors to AuthorCreate schemas.

        Args:
            crossref_data: CrossRef API response.

        Returns:
            List of AuthorCreate instances.
        """
        authors = []

        if not crossref_data.author:
            return authors

        for author_data in crossref_data.author:
            # Extract names with defaults
            first_name = author_data.given or "Unknown"
            last_name = author_data.family or "Unknown"

            # Clean up ORCID
            orcid = None
            if author_data.ORCID:
                orcid = author_data.ORCID.replace("http://orcid.org/", "").replace(
                    "https://orcid.org/", ""
                )

            authors.append(
                AuthorCreate(
                    first_name=first_name,
                    last_name=last_name,
                    orcid=orcid,
                )
            )

        return authors

    def close(self) -> None:
        """Close the underlying client."""
        self.client.close()


# Global client factory function
def get_crossref_client() -> CrossRefClient:
    """
    Get CrossRef client instance.

    Returns:
        CrossRef client that should be used with context manager.

    Example:
        ```python
        with get_crossref_client() as client:
            article = client.get_article_by_doi("10.1000/example")
        ```
    """
    return CrossRefClient()


def get_crossref_service() -> CrossRefService:
    """
    Get CrossRef service instance.

    Returns:
        CrossRef service for database integration.

    Example:
        ```python
        service = get_crossref_service()
        try:
            article_data, authors_data = service.fetch_and_convert_article("10.1000/example")
        finally:
            service.close()
        ```
    """
    return CrossRefService()
