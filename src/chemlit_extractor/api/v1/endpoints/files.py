"""API endpoints for file management operations."""

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from chemlit_extractor.database import ArticleCRUD, get_db
from chemlit_extractor.services.file_management import FileManagementService
from chemlit_extractor.services.file_utils import FileType

router = APIRouter()


# Pydantic models for file operations
class FileDownloadRequest(BaseModel):
    """Request model for downloading files."""

    pdf_url: str | None = Field(default=None, description="URL to PDF file")
    html_url: str | None = Field(default=None, description="URL to HTML file")
    supplementary_urls: list[str] = Field(
        default_factory=list, description="URLs to supplementary files"
    )


class FileDownloadResponse(BaseModel):
    """Response model for file download operations."""

    doi: str
    requested_downloads: int
    successful_downloads: int
    failed_downloads: int
    results: dict[str, dict[str, Any]]
    message: str


class FileListResponse(BaseModel):
    """Response model for listing files."""

    doi: str
    sanitized_doi: str
    has_files: bool
    total_size_mb: float
    file_counts: dict[str, int]
    total_files: int
    last_updated: str | None
    files: list[dict[str, Any]]


# FIXED: More specific routes first, then general ones
@router.get("/{doi:path}/files/{file_type}")
def list_files_by_type(
    doi: str,
    file_type: FileType,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    List files of a specific type for an article.

    Args:
        doi: Article DOI.
        file_type: Type of files to list (pdf, html, supplementary, images).

    Returns:
        List of files of the specified type.

    Raises:
        404: If article not found.
    """
    # Verify article exists
    article = ArticleCRUD.get_by_doi(db, doi)
    if not article:
        raise HTTPException(
            status_code=404, detail=f"Article with DOI '{doi}' not found"
        )

    with FileManagementService() as file_service:
        file_info = file_service.get_article_files(doi)

        return {
            "doi": doi,
            "file_type": file_type,
            "files": file_info.files[file_type],
            "count": len(file_info.files[file_type]),
        }


@router.get("/{doi:path}/files/{file_type}/{filename}")
def serve_file(
    doi: str,
    file_type: FileType,
    filename: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    """
    Serve a specific file for download.

    Args:
        doi: Article DOI.
        file_type: Type of file.
        filename: Name of the file.

    Returns:
        File download response.

    Raises:
        404: If article or file not found.
    """
    # Verify article exists
    article = ArticleCRUD.get_by_doi(db, doi)
    if not article:
        raise HTTPException(
            status_code=404, detail=f"Article with DOI '{doi}' not found"
        )

    # Get file path
    from chemlit_extractor.services.file_utils import get_file_type_directory

    file_dir = get_file_type_directory(doi, file_type)
    file_path = file_dir / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found")

    return FileResponse(
        path=file_path, filename=filename, media_type="application/octet-stream"
    )


@router.post("/{doi:path}/download")
def download_article_files(
    doi: str,
    download_request: FileDownloadRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> FileDownloadResponse:
    """
    Download files for an article.

    This endpoint downloads files in the background and returns immediately.
    Use the list endpoint to check download progress.

    Args:
        doi: Article DOI.
        download_request: URLs of files to download.
        background_tasks: FastAPI background tasks.

    Returns:
        Download operation summary.

    Raises:
        404: If article not found.
        400: If no download URLs provided.
    """
    # Verify article exists
    article = ArticleCRUD.get_by_doi(db, doi)
    if not article:
        raise HTTPException(
            status_code=404, detail=f"Article with DOI '{doi}' not found"
        )

    # Check if any URLs provided
    urls_provided = bool(
        download_request.pdf_url
        or download_request.html_url
        or download_request.supplementary_urls
    )

    if not urls_provided:
        raise HTTPException(
            status_code=400, detail="At least one download URL must be provided"
        )

    # Count requested downloads
    requested_count = 0
    if download_request.pdf_url:
        requested_count += 1
    if download_request.html_url:
        requested_count += 1
    requested_count += len(download_request.supplementary_urls)

    # Add download task to background
    background_tasks.add_task(
        _download_files_background,
        doi,
        download_request.pdf_url,
        download_request.html_url,
        download_request.supplementary_urls,
    )

    return FileDownloadResponse(
        doi=doi,
        requested_downloads=requested_count,
        successful_downloads=0,  # Will be updated by background task
        failed_downloads=0,
        results={},
        message=f"Download started for {requested_count} files. Check file list for progress.",
    )


@router.post("/{doi:path}/download/sync")
def download_article_files_sync(
    doi: str,
    download_request: FileDownloadRequest,
    db: Session = Depends(get_db),
) -> FileDownloadResponse:
    """
    Download files for an article synchronously.

    This endpoint downloads files immediately and waits for completion.
    Use for small files or when you need immediate results.

    Args:
        doi: Article DOI.
        download_request: URLs of files to download.

    Returns:
        Download operation results.

    Raises:
        404: If article not found.
        400: If no download URLs provided.
    """
    # Verify article exists
    article = ArticleCRUD.get_by_doi(db, doi)
    if not article:
        raise HTTPException(
            status_code=404, detail=f"Article with DOI '{doi}' not found"
        )

    # Check if any URLs provided
    urls_provided = bool(
        download_request.pdf_url
        or download_request.html_url
        or download_request.supplementary_urls
    )

    if not urls_provided:
        raise HTTPException(
            status_code=400, detail="At least one download URL must be provided"
        )

    # Perform downloads
    with FileManagementService() as file_service:
        results = file_service.download_from_urls(
            doi=doi,
            pdf_url=download_request.pdf_url,
            html_url=download_request.html_url,
            supplementary_urls=download_request.supplementary_urls,
        )

    # Process results
    successful = sum(1 for result in results.values() if result.success)
    failed = len(results) - successful

    # Convert results to serializable format
    serializable_results = {}
    for url, result in results.items():
        serializable_results[url] = {
            "success": result.success,
            "file_path": str(result.file_path) if result.file_path else None,
            "error": result.error,
            "file_size_mb": result.file_size_mb,
            "content_type": result.content_type,
        }

    return FileDownloadResponse(
        doi=doi,
        requested_downloads=len(results),
        successful_downloads=successful,
        failed_downloads=failed,
        results=serializable_results,
        message=f"Download completed: {successful} successful, {failed} failed",
    )


@router.get("/{doi:path}/stats")
def get_file_stats(
    doi: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Get file statistics for an article.

    Args:
        doi: Article DOI.

    Returns:
        File statistics and metadata.

    Raises:
        404: If article not found.
    """
    # Verify article exists
    article = ArticleCRUD.get_by_doi(db, doi)
    if not article:
        raise HTTPException(
            status_code=404, detail=f"Article with DOI '{doi}' not found"
        )

    with FileManagementService() as file_service:
        return file_service.get_file_stats(doi)


@router.delete("/{doi:path}/files/{file_type}", status_code=204)
def delete_files_by_type(
    doi: str,
    file_type: FileType,
    db: Session = Depends(get_db),
) -> None:
    """
    Delete all files of a specific type for an article.

    Args:
        doi: Article DOI.
        file_type: Type of files to delete.

    Raises:
        404: If article not found.
    """
    # Verify article exists
    article = ArticleCRUD.get_by_doi(db, doi)
    if not article:
        raise HTTPException(
            status_code=404, detail=f"Article with DOI '{doi}' not found"
        )

    with FileManagementService() as file_service:
        success = file_service.delete_file_type(doi, file_type)

        if not success:
            raise HTTPException(
                status_code=500, detail=f"Failed to delete {file_type} files"
            )
    # Don't return anything - FastAPI will automatically return 204


# FIXED: Put the general route LAST to avoid conflicts
@router.get("/{doi:path}")
def list_article_files(
    doi: str,
    db: Session = Depends(get_db),
) -> FileListResponse:
    """
    List all files associated with an article.

    Args:
        doi: Article DOI.

    Returns:
        Information about all files for the article.

    Raises:
        404: If article not found.
    """
    # Verify article exists
    article = ArticleCRUD.get_by_doi(db, doi)
    if not article:
        raise HTTPException(
            status_code=404, detail=f"Article with DOI '{doi}' not found"
        )

    with FileManagementService() as file_service:
        file_info = file_service.get_article_files(doi)
        stats = file_service.get_file_stats(doi)

        return FileListResponse(
            doi=doi,
            sanitized_doi=file_info.sanitized_doi,
            has_files=file_info.has_files(),
            total_size_mb=file_info.total_size_mb,
            file_counts=file_info.get_file_count(),
            total_files=sum(file_info.get_file_count().values()),
            last_updated=stats["last_updated"],
            files=file_info.get_all_files(),
        )


@router.delete("/{doi:path}", status_code=204)
def delete_article_files(
    doi: str,
    db: Session = Depends(get_db),
) -> None:
    """
    Delete all files for an article.

    Args:
        doi: Article DOI.

    Raises:
        404: If article not found.
    """
    # Verify article exists
    article = ArticleCRUD.get_by_doi(db, doi)
    if not article:
        raise HTTPException(
            status_code=404, detail=f"Article with DOI '{doi}' not found"
        )

    with FileManagementService() as file_service:
        success = file_service.delete_article_files(doi)

        if not success:
            raise HTTPException(
                status_code=500, detail="Failed to delete article files"
            )
    # Don't return anything - FastAPI will automatically return 204


# Background task function
def _download_files_background(
    doi: str, pdf_url: str | None, html_url: str | None, supplementary_urls: list[str]
) -> None:
    """
    Background task for downloading files.

    Args:
        doi: Article DOI.
        pdf_url: Optional PDF URL.
        html_url: Optional HTML URL.
        supplementary_urls: List of supplementary file URLs.
    """
    try:
        with FileManagementService() as file_service:
            file_service.download_from_urls(
                doi=doi,
                pdf_url=pdf_url,
                html_url=html_url,
                supplementary_urls=supplementary_urls,
            )
    except Exception as e:
        # Log error but don't raise (background task)
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Background download failed for {doi}: {e}")


@router.get("/{doi:path}/stats/html")
def get_file_stats_html(
    doi: str,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Get file statistics as HTML for HTMX updates."""
    try:
        # Verify article exists
        article = ArticleCRUD.get_by_doi(db, doi)
        if not article:
            return HTMLResponse(
                content=f"<div class=\"error\">Article with DOI '{doi}' not found.</div>",
                status_code=404,
            )

        with FileManagementService() as file_service:
            stats = file_service.get_file_stats(doi)

            if stats["has_files"]:
                file_list = ""
                for file_type, count in stats["file_counts"].items():
                    if count > 0:
                        file_list += f"<li><strong>{file_type.title()}:</strong> {count} file(s)</li>"

                return HTMLResponse(
                    content=f"""
                <div class="download-status">
                    <h3>File Status for {doi}</h3>
                    <p><strong>Total files:</strong> {stats['total_files']}</p>
                    <p><strong>Total size:</strong> {stats['total_size_mb']} MB</p>
                    <p><strong>Last updated:</strong> {stats['last_updated'] or 'Never'}</p>
                    <ul>{file_list}</ul>
                </div>
                """
                )
            else:
                return HTMLResponse(
                    content=f"""
                <div class="download-status">
                    <h3>File Status for {doi}</h3>
                    <p>No files have been downloaded yet.</p>
                    <p><em>If downloads were started, they may still be in progress.</em></p>
                    <button class="btn" 
                            hx-get="/api/v1/files/{doi}/stats/html" 
                            hx-target="#file-status" hx-swap="innerHTML">
                        Refresh Status
                    </button>
                </div>
                """
                )

    except Exception as e:
        return HTMLResponse(
            content=f'<div class="error">Error checking file status: {str(e)}</div>',
            status_code=500,
        ) @ router.get("/{doi:path}/stats/html")


def get_file_stats_html(
    doi: str,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Get file statistics as HTML for HTMX updates."""
    try:
        # Verify article exists
        article = ArticleCRUD.get_by_doi(db, doi)
        if not article:
            return HTMLResponse(
                content=f'<div class="bg-red-50 border border-red-200 rounded-lg p-4"><p class="text-red-800">Article with DOI \'{doi}\' not found.</p></div>',
                status_code=404,
            )

        with FileManagementService() as file_service:
            stats = file_service.get_file_stats(doi)

            if stats["has_files"]:
                file_list = ""
                for file_type, count in stats["file_counts"].items():
                    if count > 0:
                        file_list += f"<li><strong>{file_type.title()}:</strong> {count} file(s)</li>"

                return HTMLResponse(
                    content=f"""
                <div class="bg-green-50 border border-green-200 rounded-lg p-6">
                    <h3 class="text-lg font-medium text-green-800 mb-4">File Status for {doi}</h3>
                    <div class="grid grid-cols-2 gap-4 text-sm">
                        <div>
                            <p class="font-medium text-gray-700">Total files:</p>
                            <p class="text-gray-900">{stats['total_files']}</p>
                        </div>
                        <div>
                            <p class="font-medium text-gray-700">Total size:</p>
                            <p class="text-gray-900">{stats['total_size_mb']} MB</p>
                        </div>
                        <div>
                            <p class="font-medium text-gray-700">Last updated:</p>
                            <p class="text-gray-900">{stats['last_updated'] or 'Never'}</p>
                        </div>
                        <div>
                            <p class="font-medium text-gray-700">File breakdown:</p>
                            <ul class="text-gray-900 text-sm">{file_list}</ul>
                        </div>
                    </div>
                </div>
                """
                )
            else:
                return HTMLResponse(
                    content=f"""
                <div class="bg-yellow-50 border border-yellow-200 rounded-lg p-6">
                    <h3 class="text-lg font-medium text-yellow-800 mb-2">File Status for {doi}</h3>
                    <p class="text-yellow-700">No files have been downloaded yet.</p>
                    <p class="text-yellow-600 text-sm mt-1"><em>If downloads were started, they may still be in progress.</em></p>
                    <button class="mt-3 inline-flex items-center px-3 py-2 border border-yellow-300 text-sm font-medium rounded-md text-yellow-800 bg-yellow-100 hover:bg-yellow-200 transition-colors" 
                            hx-get="/api/v1/files/{doi}/stats/html" 
                            hx-target="#file-status"
                            hx-swap="innerHTML">
                        Refresh Status
                    </button>
                </div>
                """
                )

    except Exception as e:
        return HTMLResponse(
            content=f'<div class="bg-red-50 border border-red-200 rounded-lg p-4"><p class="text-red-800">Error checking file status: {str(e)}</p></div>',
            status_code=500,
        )
