"""File download service for fetching article files."""

import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from chemlit_extractor.core.config import settings
from chemlit_extractor.services.file_utils import (
    FileType,
    create_article_directories,
    get_file_type_directory,
    get_safe_filename,
    is_allowed_file_type,
    validate_file_size,
)

logger = logging.getLogger(__name__)


class DownloadResult:
    """Result of a file download operation."""

    def __init__(
        self,
        success: bool,
        file_path: Path | None = None,
        error: str | None = None,
        file_size_mb: float = 0.0,
        content_type: str | None = None,
    ):
        self.success = success
        self.file_path = file_path
        self.error = error
        self.file_size_mb = file_size_mb
        self.content_type = content_type

    def __repr__(self) -> str:
        if self.success:
            return f"DownloadResult(success=True, file_path={self.file_path}, size={self.file_size_mb:.2f}MB)"
        else:
            return f"DownloadResult(success=False, error='{self.error}')"


class FileDownloadService:
    """Service for downloading files from URLs."""

    def __init__(self, timeout: int = 60, max_size_mb: int | None = None):
        """
        Initialize download service.

        Args:
            timeout: Request timeout in seconds.
            max_size_mb: Maximum file size in MB (defaults to settings).
        """
        self.timeout = timeout
        self.max_size_mb = max_size_mb or settings.max_file_size_mb

        # Configure HTTP client
        self.client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": "ChemLitExtractor/0.1.0 (Academic Research Tool)"},
            follow_redirects=True,
        )

    def __enter__(self) -> "FileDownloadService":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.client.close()

    def download_file(
        self, url: str, doi: str, file_type: FileType, filename: str | None = None
    ) -> DownloadResult:
        """
        Download a file from URL to the appropriate article directory.

        Args:
            url: URL to download from.
            doi: Article DOI for directory organization.
            file_type: Type of file (pdf, html, supplementary, images).
            filename: Optional custom filename (will be sanitized).

        Returns:
            DownloadResult with success status and file path.
        """
        try:
            # Validate URL
            parsed_url = urlparse(url)
            if parsed_url.scheme not in ("http", "https"):
                return DownloadResult(
                    success=False, error="URL must use HTTP or HTTPS protocol"
                )

            # Create article directories
            create_article_directories(doi)

            # Determine filename
            if filename is None:
                filename = self._extract_filename_from_url(url)

            safe_filename = get_safe_filename(filename)

            # Validate file type
            if not is_allowed_file_type(safe_filename, file_type):
                return DownloadResult(
                    success=False,
                    error=f"File type not allowed for category '{file_type}': {safe_filename}",
                )

            # Get target directory and file path
            target_dir = get_file_type_directory(doi, file_type)
            target_path = target_dir / safe_filename

            # Download file
            logger.info(f"Downloading {url} to {target_path}")

            with self.client.stream("GET", url) as response:
                response.raise_for_status()

                # Check content type
                content_type = response.headers.get("content-type", "")

                # Stream download to file

                with open(target_path, "wb") as file:
                    for chunk in response.iter_bytes(chunk_size=8192):
                        file.write(chunk)
                        total_size += len(chunk)

                        # Check size limit during download
                        if total_size > self.max_size_mb * 1024 * 1024:
                            file.close()
                            target_path.unlink()  # Delete partial file
                            return DownloadResult(
                                success=False,
                                error=f"File too large (>{self.max_size_mb}MB)",
                            )

            # Final validation
            if not validate_file_size(target_path, self.max_size_mb):
                target_path.unlink()
                return DownloadResult(
                    success=False,
                    error=f"Downloaded file exceeds size limit ({self.max_size_mb}MB)",
                )

            from chemlit_extractor.services.file_utils import get_file_size_mb

            file_size_mb = get_file_size_mb(target_path)

            logger.info(
                f"Successfully downloaded {safe_filename} ({file_size_mb:.2f}MB)"
            )

            return DownloadResult(
                success=True,
                file_path=target_path,
                file_size_mb=file_size_mb,
                content_type=content_type,
            )

        except httpx.HTTPError as e:
            logger.error(f"HTTP error downloading {url}: {e}")
            return DownloadResult(success=False, error=f"HTTP error: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error downloading {url}: {e}")
            return DownloadResult(success=False, error=f"Download failed: {str(e)}")

    def download_multiple_files(
        self, downloads: list[dict[str, Any]], doi: str
    ) -> dict[str, DownloadResult]:
        """
        Download multiple files for an article.

        Args:
            downloads: List of download specs with keys: url, file_type, filename (optional).
            doi: Article DOI.

        Returns:
            Dictionary mapping URLs to DownloadResult objects.
        """
        results = {}

        for download_spec in downloads:
            url = download_spec["url"]
            file_type = download_spec["file_type"]
            filename = download_spec.get("filename")

            result = self.download_file(url, doi, file_type, filename)
            results[url] = result

            if not result.success:
                logger.warning(f"Failed to download {url}: {result.error}")

        return results

    def _extract_filename_from_url(self, url: str) -> str:
        """
        Extract filename from URL.

        Args:
            url: URL to extract filename from.

        Returns:
            Extracted filename or generated name.
        """
        parsed = urlparse(url)
        path = Path(parsed.path)

        # Try to get filename from URL path
        if path.name and "." in path.name:
            return path.name

        # Generate filename based on URL
        domain = parsed.netloc.replace("www.", "")
        return f"download_{domain}.html"

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()


# Convenience functions
def download_file(
    url: str, doi: str, file_type: FileType, filename: str | None = None
) -> DownloadResult:
    """
    Download a single file (convenience function).

    Args:
        url: URL to download from.
        doi: Article DOI.
        file_type: Type of file.
        filename: Optional custom filename.

    Returns:
        DownloadResult.
    """
    with FileDownloadService() as service:
        return service.download_file(url, doi, file_type, filename)


def download_article_files(
    doi: str, pdf_url: str | None = None, html_url: str | None = None
) -> dict[str, DownloadResult]:
    """
    Download common article files (PDF and HTML).

    Args:
        doi: Article DOI.
        pdf_url: Optional PDF URL.
        html_url: Optional HTML URL.

    Returns:
        Dictionary of download results.
    """
    downloads = []

    if pdf_url:
        downloads.append(
            {"url": pdf_url, "file_type": "pdf", "filename": "article.pdf"}
        )

    if html_url:
        downloads.append(
            {"url": html_url, "file_type": "html", "filename": "article.html"}
        )

    if not downloads:
        return {}

    with FileDownloadService() as service:
        return service.download_multiple_files(downloads, doi)
