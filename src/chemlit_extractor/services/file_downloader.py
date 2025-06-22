"""Simple file downloader service with auto-discovery."""

import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from chemlit_extractor.core.config import settings
from chemlit_extractor.services.file_utils import (
    get_article_directory,
    get_safe_filename,
)

logger = logging.getLogger(__name__)


class FileDownloader:
    """Simple file downloader with automatic discovery capabilities."""

    # Common publisher patterns for file discovery
    PUBLISHER_PATTERNS = {
        "royal society of chemistry": {
            "pdf": lambda doi, url: f"https://pubs.rsc.org/en/content/articlepdf/{doi.split('/')[-1]}",
            "html": lambda doi, url: url,  # Usually the article URL is the HTML version
        },
        "american chemical society": {
            "pdf": lambda doi, url: url.replace("/abs/", "/pdf/") if url else None,
            "html": lambda doi, url: url.replace("/pdf/", "/abs/") if url else None,
        },
        "elsevier": {
            "pdf": lambda doi, url: f"https://api.elsevier.com/content/article/doi/{doi}?httpAccept=application/pdf",
            "html": lambda doi, url: url,
        },
        "wiley": {
            "pdf": lambda doi, url: url.replace("/abs/", "/pdf/") if url else None,
            "html": lambda doi, url: url.replace("/pdf/", "/abs/") if url else None,
        },
        "springer": {
            "pdf": lambda doi, url: url.replace(".html", ".pdf") if url else None,
            "html": lambda doi, url: url,
        },
    }

    def __init__(self):
        self.client = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "ChemLitExtractor/1.0 (Academic Research Tool)",
                "Accept": "application/pdf,text/html,*/*",
            },
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        """Close HTTP client."""
        self.client.close()

    def auto_discover_and_download(
        self,
        doi: str,
        publisher: str | None = None,
        url: str | None = None,
    ) -> dict[str, Any]:
        """
        Try to automatically discover and download files.

        Args:
            doi: Article DOI
            publisher: Publisher name from CrossRef
            url: Article URL from CrossRef

        Returns:
            Dict with results for each file type
        """
        results = {}

        # Try publisher-specific patterns
        if publisher:
            publisher_lower = publisher.lower()
            for pub_key, patterns in self.PUBLISHER_PATTERNS.items():
                if pub_key in publisher_lower:
                    # Try PDF
                    if "pdf" in patterns:
                        pdf_url = patterns["pdf"](doi, url)
                        if pdf_url:
                            results["pdf"] = self._try_download(doi, pdf_url, "pdf")

                    # Try HTML
                    if "html" in patterns:
                        html_url = patterns["html"](doi, url)
                        if (
                            html_url and html_url != url
                        ):  # Don't re-download the same URL
                            results["html"] = self._try_download(doi, html_url, "html")

                    break

        # If no publisher patterns matched, try generic approaches
        if not results and url:
            # Try common URL modifications
            results.update(self._try_generic_patterns(doi, url))

        # Try DOI.org as last resort
        if not results.get("pdf"):
            doi_url = f"https://doi.org/{doi}"
            results["pdf"] = self._try_download(
                doi, doi_url, "pdf", follow_meta_refresh=True
            )

        return results

    def download_from_urls(
        self,
        doi: str,
        pdf_url: str | None = None,
        html_url: str | None = None,
        supplementary_urls: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Download files from provided URLs.

        Args:
            doi: Article DOI
            pdf_url: Direct PDF URL
            html_url: Direct HTML URL
            supplementary_urls: List of supplementary file URLs

        Returns:
            Dict with download results
        """
        results = {}

        if pdf_url:
            results["pdf"] = self._download_file(doi, pdf_url, "pdf", "article.pdf")

        if html_url:
            results["html"] = self._download_file(doi, html_url, "html", "article.html")

        if supplementary_urls:
            supp_results = []
            for i, url in enumerate(supplementary_urls):
                result = self._download_file(
                    doi, url, "supplementary", f"supplementary_{i+1}"
                )
                supp_results.append(result)
            results["supplementary"] = {
                "success": any(r["success"] for r in supp_results),
                "files": supp_results,
                "count": len([r for r in supp_results if r["success"]]),
            }

        return results

    def _try_download(
        self,
        doi: str,
        url: str,
        file_type: str,
        follow_meta_refresh: bool = False,
    ) -> dict[str, Any]:
        """Try to download a file, return result dict."""
        try:
            response = self.client.head(url, follow_redirects=True)

            # Check if it's the right content type
            content_type = response.headers.get("content-type", "").lower()
            if file_type == "pdf" and "pdf" not in content_type:
                return {"success": False, "error": "Not a PDF"}
            elif file_type == "html" and "html" not in content_type:
                return {"success": False, "error": "Not HTML"}

            # If HEAD looks good, do the actual download
            return self._download_file(doi, url, file_type)

        except Exception as e:
            logger.debug(f"Failed to download {url}: {e}")
            return {"success": False, "error": str(e)}

    def _download_file(
        self,
        doi: str,
        url: str,
        file_type: str,
        filename: str | None = None,
    ) -> dict[str, Any]:
        """Download a file and save it."""
        try:
            # Create directory
            article_dir = get_article_directory(doi)
            type_dir = article_dir / file_type
            type_dir.mkdir(parents=True, exist_ok=True)

            # Download
            response = self.client.get(url)
            response.raise_for_status()

            # Determine filename
            if not filename:
                filename = self._get_filename_from_url(url)
            safe_filename = get_safe_filename(filename)

            # Add extension if missing
            if file_type == "pdf" and not safe_filename.endswith(".pdf"):
                safe_filename += ".pdf"
            elif file_type == "html" and not safe_filename.endswith((".html", ".htm")):
                safe_filename += ".html"

            # Save file
            file_path = type_dir / safe_filename
            file_path.write_bytes(response.content)

            file_size_mb = len(response.content) / (1024 * 1024)

            logger.info(f"Downloaded {safe_filename} ({file_size_mb:.2f} MB) for {doi}")

            return {
                "success": True,
                "filename": safe_filename,
                "size_mb": round(file_size_mb, 2),
                "path": str(file_path.relative_to(settings.data_root_path)),
            }

        except Exception as e:
            logger.error(f"Error downloading {url} for {doi}: {e}")
            return {
                "success": False,
                "error": str(e),
                "url": url,
            }

    def _try_generic_patterns(self, doi: str, url: str) -> dict[str, Any]:
        """Try generic URL patterns when publisher-specific ones don't work."""
        results = {}

        # Common PDF URL patterns
        pdf_patterns = [
            lambda u: u.replace("/abs/", "/pdf/"),
            lambda u: u.replace("/abstract/", "/pdf/"),
            lambda u: u.replace("/full/", "/pdf/"),
            lambda u: u.replace(".html", ".pdf"),
            lambda u: u.replace("/html/", "/pdf/"),
            lambda u: u + ".pdf" if not u.endswith(".pdf") else u,
        ]

        for pattern in pdf_patterns:
            try:
                pdf_url = pattern(url)
                if pdf_url != url:  # Only try if URL actually changed
                    result = self._try_download(doi, pdf_url, "pdf")
                    if result.get("success"):
                        results["pdf"] = result
                        break
            except Exception:
                continue

        return results

    def _get_filename_from_url(self, url: str) -> str:
        """Extract filename from URL."""
        parsed = urlparse(url)
        path = Path(parsed.path)

        if path.name and "." in path.name:
            return path.name

        # Generate based on domain
        domain = parsed.netloc.replace("www.", "").replace(".", "_")
        return f"download_{domain}"
