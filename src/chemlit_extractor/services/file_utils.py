"""File management utilities."""

import re
from pathlib import Path
from typing import Literal

from chemlit_extractor.core.config import settings

FileType = Literal["pdf", "html", "supplementary", "images"]


def sanitize_doi_for_filesystem(doi: str) -> str:
    """
    Convert DOI to filesystem-safe directory name.

    Args:
        doi: DOI string (e.g., "10.1000/example.doi")

    Returns:
        Sanitized string safe for filesystem use.

    Examples:
        "10.1000/example.doi" -> "10.1000_example.doi"
        "10.1021/ja.2023.12345" -> "10.1021_ja.2023.12345"
    """
    # Remove common DOI prefixes if present
    clean_doi = doi.lower().strip()
    prefixes_to_remove = [
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
        "doi:",
    ]

    for prefix in prefixes_to_remove:
        if clean_doi.startswith(prefix):
            clean_doi = clean_doi[len(prefix) :]
            break

    # Replace filesystem-unsafe characters
    # Keep alphanumeric, dots, hyphens, underscores
    # Replace forward slashes with underscores
    sanitized = re.sub(r"[/\\]", "_", clean_doi)
    sanitized = re.sub(r'[<>:"|?*]', "_", sanitized)

    # Remove any double underscores and trailing/leading underscores
    sanitized = re.sub(r"_+", "_", sanitized)
    sanitized = sanitized.strip("_")

    # Ensure it's not too long for filesystem
    if len(sanitized) > 200:
        sanitized = sanitized[:200].rstrip("_")

    return sanitized


def get_article_directory(doi: str) -> Path:
    """
    Get the directory path for an article's files.

    Args:
        doi: Article DOI.

    Returns:
        Path to article directory.
    """
    sanitized_doi = sanitize_doi_for_filesystem(doi)
    return settings.articles_path / sanitized_doi


def get_file_type_directory(doi: str, file_type: FileType) -> Path:
    """
    Get the directory path for a specific file type within an article.

    Args:
        doi: Article DOI.
        file_type: Type of files (pdf, html, supplementary, images).

    Returns:
        Path to file type directory.
    """
    article_dir = get_article_directory(doi)
    return article_dir / file_type


def create_article_directories(doi: str) -> dict[str, Path]:
    """
    Create all necessary directories for an article.

    Args:
        doi: Article DOI.

    Returns:
        Dictionary mapping file types to their directory paths.
    """
    article_dir = get_article_directory(doi)

    directories = {
        "article": article_dir,
        "pdf": article_dir / "pdf",
        "html": article_dir / "html",
        "supplementary": article_dir / "supplementary",
        "images": article_dir / "images",
    }

    # Create all directories
    for directory in directories.values():
        directory.mkdir(parents=True, exist_ok=True)

    return directories


def get_safe_filename(original_filename: str, max_length: int = 100) -> str:
    """
    Make a filename safe for filesystem use.

    Args:
        original_filename: Original filename.
        max_length: Maximum allowed filename length.

    Returns:
        Safe filename.
    """
    # Remove path components if present
    filename = Path(original_filename).name

    # Replace unsafe characters
    safe_filename = re.sub(r'[<>:"|?*\\]', "_", filename)

    # Remove multiple underscores and spaces
    safe_filename = re.sub(r"[_\s]+", "_", safe_filename)

    # Trim to max length while preserving extension
    if len(safe_filename) > max_length:
        stem = Path(safe_filename).stem
        suffix = Path(safe_filename).suffix

        # Keep extension, trim stem
        max_stem_length = max_length - len(suffix)
        if max_stem_length > 0:
            safe_filename = stem[:max_stem_length] + suffix
        else:
            safe_filename = safe_filename[:max_length]

    return safe_filename.strip("_")


def is_allowed_file_type(filename: str, file_type: FileType) -> bool:
    """
    Check if a file type is allowed for the given category.

    Args:
        filename: Name of the file.
        file_type: Expected file type category.

    Returns:
        True if file type is allowed.
    """
    file_extension = Path(filename).suffix.lower()

    allowed_extensions = {
        "pdf": {".pdf"},
        "html": {".html", ".htm", ".xml"},
        "supplementary": {
            ".pdf",
            ".doc",
            ".docx",
            ".txt",
            ".csv",
            ".xlsx",
            ".xls",
            ".zip",
            ".tar",
            ".gz",
            ".rar",
            ".7z",
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".tiff",
            ".bmp",
            ".svg",
        },
        "images": {
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".tiff",
            ".tif",
            ".bmp",
            ".svg",
            ".webp",
        },
    }

    return file_extension in allowed_extensions.get(file_type, set())


def get_file_size_mb(file_path: Path) -> float:
    """
    Get file size in megabytes.

    Args:
        file_path: Path to the file.

    Returns:
        File size in MB.
    """
    if not file_path.exists():
        return 0.0

    size_bytes = file_path.stat().st_size
    return size_bytes / (1024 * 1024)


def validate_file_size(file_path: Path, max_size_mb: int | None = None) -> bool:
    """
    Validate that file size is within limits.

    Args:
        file_path: Path to the file.
        max_size_mb: Maximum allowed size in MB (defaults to settings).

    Returns:
        True if file size is acceptable.
    """
    if max_size_mb is None:
        max_size_mb = settings.max_file_size_mb

    file_size_mb = get_file_size_mb(file_path)
    return file_size_mb <= max_size_mb
