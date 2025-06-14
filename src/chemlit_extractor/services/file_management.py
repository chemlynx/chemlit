"""File management service for organizing and managing article files."""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from chemlit_extractor.services.file_download import DownloadResult, FileDownloadService
from chemlit_extractor.services.file_utils import (
    FileType,
    create_article_directories,
    get_article_directory,
    get_file_size_mb,
    get_file_type_directory,
    sanitize_doi_for_filesystem,
)


class ArticleFileInfo:
    """Information about files associated with an article."""

    def __init__(self, doi: str):
        self.doi = doi
        self.sanitized_doi = sanitize_doi_for_filesystem(doi)
        self.article_directory = get_article_directory(doi)
        self.files: dict[FileType, list[dict[str, Any]]] = {
            "pdf": [],
            "html": [],
            "supplementary": [],
            "images": [],
        }
        self.total_size_mb = 0.0
        self.last_updated: datetime | None = None

        # Scan for existing files
        self._scan_files()

    def _scan_files(self) -> None:
        """Scan article directory for existing files."""
        if not self.article_directory.exists():
            return

        for file_type in self.files.keys():
            type_dir = get_file_type_directory(self.doi, file_type)
            if type_dir.exists():
                for file_path in type_dir.iterdir():
                    if file_path.is_file():
                        file_info = {
                            "filename": file_path.name,
                            "path": file_path,
                            "size_mb": get_file_size_mb(file_path),
                            "modified": datetime.fromtimestamp(
                                file_path.stat().st_mtime
                            ),
                        }
                        self.files[file_type].append(file_info)
                        self.total_size_mb += file_info["size_mb"]

                        # Track most recent modification
                        if (
                            self.last_updated is None
                            or file_info["modified"] > self.last_updated
                        ):
                            self.last_updated = file_info["modified"]

    def get_file_count(self) -> dict[str, int]:
        """Get count of files by type."""
        return {file_type: len(files) for file_type, files in self.files.items()}

    def has_files(self) -> bool:
        """Check if article has any files."""
        return any(len(files) > 0 for files in self.files.values())

    def get_all_files(self) -> list[dict[str, Any]]:
        """Get all files as a flat list."""
        all_files = []
        for file_type, files in self.files.items():
            for file_info in files:
                file_info["type"] = file_type
                all_files.append(file_info)
        return sorted(all_files, key=lambda x: x["modified"], reverse=True)


class FileManagementService:
    """Service for managing article files and directories."""

    def __init__(self):
        """Initialize file management service."""
        self.download_service = FileDownloadService()

    def get_article_files(self, doi: str) -> ArticleFileInfo:
        """
        Get information about files for an article.

        Args:
            doi: Article DOI.

        Returns:
            ArticleFileInfo with file details.
        """
        return ArticleFileInfo(doi)

    def create_article_structure(self, doi: str) -> dict[str, Path]:
        """
        Create directory structure for an article.

        Args:
            doi: Article DOI.

        Returns:
            Dictionary mapping directory types to paths.
        """
        return create_article_directories(doi)

    def download_files(
        self, doi: str, file_downloads: list[dict[str, Any]]
    ) -> dict[str, DownloadResult]:
        """
        Download files for an article.

        Args:
            doi: Article DOI.
            file_downloads: List of download specifications.

        Returns:
            Dictionary mapping URLs to download results.
        """
        return self.download_service.download_multiple_files(file_downloads, doi)

    def download_from_urls(
        self,
        doi: str,
        pdf_url: str | None = None,
        html_url: str | None = None,
        supplementary_urls: list[str] | None = None,
    ) -> dict[str, DownloadResult]:
        """
        Download common article files from URLs.

        Args:
            doi: Article DOI.
            pdf_url: Optional PDF URL.
            html_url: Optional HTML URL.
            supplementary_urls: Optional list of supplementary file URLs.

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

        if supplementary_urls:
            for i, url in enumerate(supplementary_urls):
                downloads.append(
                    {
                        "url": url,
                        "file_type": "supplementary",
                        "filename": f"supplementary_{i+1}",
                    }
                )

        if not downloads:
            return {}

        return self.download_service.download_multiple_files(downloads, doi)

    def delete_article_files(self, doi: str) -> bool:
        """
        Delete all files for an article.

        Args:
            doi: Article DOI.

        Returns:
            True if deletion was successful.
        """
        try:
            article_dir = get_article_directory(doi)
            if article_dir.exists():
                shutil.rmtree(article_dir)
                return True
            return False
        except Exception:
            return False

    def delete_file_type(self, doi: str, file_type: FileType) -> bool:
        """
        Delete all files of a specific type for an article.

        Args:
            doi: Article DOI.
            file_type: Type of files to delete.

        Returns:
            True if deletion was successful.
        """
        try:
            type_dir = get_file_type_directory(doi, file_type)
            if type_dir.exists():
                shutil.rmtree(type_dir)
                # Recreate empty directory
                type_dir.mkdir(parents=True, exist_ok=True)
                return True
            return False
        except Exception:
            return False

    def move_file(
        self,
        doi: str,
        source_path: Path,
        target_file_type: FileType,
        new_filename: str | None = None,
    ) -> Path | None:
        """
        Move a file to the appropriate article directory.

        Args:
            doi: Article DOI.
            source_path: Current file path.
            target_file_type: Target file type directory.
            new_filename: Optional new filename.

        Returns:
            New file path if successful, None otherwise.
        """
        try:
            if not source_path.exists():
                return None

            # Create directories if needed
            create_article_directories(doi)

            # Determine target filename
            filename = new_filename or source_path.name
            from chemlit_extractor.services.file_utils import get_safe_filename

            safe_filename = get_safe_filename(filename)

            # Get target path
            target_dir = get_file_type_directory(doi, target_file_type)
            target_path = target_dir / safe_filename

            # Move file
            shutil.move(str(source_path), str(target_path))
            return target_path

        except Exception:
            return None

    def get_file_stats(self, doi: str) -> dict[str, Any]:
        """
        Get statistics about files for an article.

        Args:
            doi: Article DOI.

        Returns:
            Dictionary with file statistics.
        """
        file_info = self.get_article_files(doi)
        file_counts = file_info.get_file_count()

        return {
            "doi": doi,
            "sanitized_doi": file_info.sanitized_doi,
            "has_files": file_info.has_files(),
            "total_size_mb": round(file_info.total_size_mb, 2),
            "file_counts": file_counts,
            "total_files": sum(file_counts.values()),
            "last_updated": (
                file_info.last_updated.isoformat() if file_info.last_updated else None
            ),
            "directory_exists": file_info.article_directory.exists(),
        }

    def cleanup_empty_directories(self, doi: str) -> None:
        """
        Remove empty directories for an article.

        Args:
            doi: Article DOI.
        """
        try:
            article_dir = get_article_directory(doi)
            if not article_dir.exists():
                return

            # Remove empty subdirectories
            for subdir in article_dir.iterdir():
                if subdir.is_dir() and not any(subdir.iterdir()):
                    subdir.rmdir()

            # Remove article directory if empty
            if not any(article_dir.iterdir()):
                article_dir.rmdir()

        except Exception:
            pass  # Ignore errors in cleanup

    def close(self) -> None:
        """Close the download service."""
        self.download_service.close()

    def __enter__(self) -> "FileManagementService":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()


# Convenience function
def get_file_management_service() -> FileManagementService:
    """
    Get file management service instance.

    Returns:
        FileManagementService instance.
    """
    return FileManagementService()
