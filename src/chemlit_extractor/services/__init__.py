"""Services package initialization."""

from chemlit_extractor.services.crossref import (
    CrossRefClient,
    CrossRefService,
    RateLimiter,
    get_crossref_client,
    get_crossref_service,
)
from chemlit_extractor.services.file_download import (
    DownloadResult,
    FileDownloadService,
    download_article_files,
    download_file,
)
from chemlit_extractor.services.file_management import (
    ArticleFileInfo,
    FileManagementService,
    get_file_management_service,
)
from chemlit_extractor.services.file_utils import (
    FileType,
    create_article_directories,
    get_article_directory,
    get_file_type_directory,
    get_safe_filename,
    sanitize_doi_for_filesystem,
)

__all__ = [
    "ArticleFileInfo",
    "CrossRefClient",
    "CrossRefService",
    "DownloadResult",
    "FileDownloadService",
    "FileManagementService",
    "FileType",
    "RateLimiter",
    "create_article_directories",
    "download_article_files",
    "download_file",
    "get_article_directory",
    "get_crossref_client",
    "get_crossref_service",
    "get_file_management_service",
    "get_file_type_directory",
    "get_safe_filename",
    "sanitize_doi_for_filesystem",
]
