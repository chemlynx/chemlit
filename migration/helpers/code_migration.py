"""Code migration helpers for converting existing patterns to ArticleService."""

from typing import Any, Dict, Optional
import logging

from chemlit_extractor.services.article_service import (
    ArticleService,
    FileUrls,
    RegistrationStatus,
    get_article_service_context,
)
from chemlit_extractor.models.schemas import ArticleCreate

logger = logging.getLogger(__name__)


class CodeMigrationHelper:
    """Helper class for migrating existing code patterns to ArticleService."""

    @staticmethod
    def migrate_crossref_fetch_pattern(doi: str) -> Dict[str, Any]:
        """
        Migrate the old CrossRef fetch pattern.

        OLD PATTERN:
        ```python
        service = CrossRefService()
        try:
            result = service.fetch_and_convert_article(doi)
            if result:
                article_data, authors_data = result
                article = ArticleCRUD.create(db, article_data, authors_data)
                return {"success": True, "article": article}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            service.close()
        ```

        NEW PATTERN:
        ```python
        result = CodeMigrationHelper.migrate_crossref_fetch_pattern(doi)
        ```
        """
        with get_article_service_context() as service:
            result = service.register_article(
                doi=doi,
                fetch_metadata=True,
                download_files=False,
            )

            return {
                "success": result.status == RegistrationStatus.SUCCESS,
                "article": result.article,
                "message": result.message,
                "error": (
                    result.error_details
                    if result.status == RegistrationStatus.ERROR
                    else None
                ),
            }

    @staticmethod
    def migrate_file_download_pattern(
        doi: str,
        pdf_url: Optional[str] = None,
        html_url: Optional[str] = None,
        supplementary_urls: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        """
        Migrate the old file download pattern.

        OLD PATTERN:
        ```python
        background_tasks.add_task(
            _download_files_for_article,
            doi, pdf_url, html_url, supplementary_urls
        )
        ```

        NEW PATTERN:
        ```python
        result = CodeMigrationHelper.migrate_file_download_pattern(
            doi, pdf_url, html_url, supplementary_urls
        )
        ```
        """
        file_urls = None
        if pdf_url or html_url or supplementary_urls:
            file_urls = FileUrls(
                pdf_url=pdf_url,
                html_url=html_url,
                supplementary_urls=supplementary_urls or [],
            )

        with get_article_service_context() as service:
            result = service.register_article(
                doi=doi,
                fetch_metadata=True,
                download_files=bool(file_urls),
                file_urls=file_urls,
            )

            download_info = {
                "triggered": (
                    result.download_status.attempted
                    if result.download_status
                    else False
                ),
                "successful": (
                    result.download_status.successful_downloads
                    if result.download_status
                    else 0
                ),
                "failed": (
                    result.download_status.failed_downloads
                    if result.download_status
                    else 0
                ),
            }

            return {
                "article_status": result.status,
                "download_status": download_info,
                "message": result.message,
            }

    @staticmethod
    def migrate_direct_creation_pattern(article_data: ArticleCreate) -> Dict[str, Any]:
        """
        Migrate direct article creation pattern.

        OLD PATTERN:
        ```python
        try:
            existing = ArticleCRUD.get_by_doi(db, article_data.doi)
            if existing:
                raise HTTPException(400, "Already exists")
            article = ArticleCRUD.create(db, article_data)
            return article
        except ValueError as e:
            raise HTTPException(400, str(e))
        ```

        NEW PATTERN:
        ```python
        result = CodeMigrationHelper.migrate_direct_creation_pattern(article_data)
        ```
        """
        with get_article_service_context() as service:
            result = service.register_article(
                doi=article_data.doi,
                fetch_metadata=False,
                article_data=article_data,
            )

            return {
                "success": result.status == RegistrationStatus.SUCCESS,
                "article": result.article,
                "already_exists": result.status == RegistrationStatus.ALREADY_EXISTS,
                "error_message": (
                    result.message
                    if result.status == RegistrationStatus.ERROR
                    else None
                ),
            }
