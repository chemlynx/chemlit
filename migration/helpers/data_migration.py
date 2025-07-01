"""Data migration helpers for existing database records."""

from sqlalchemy.orm import Session
from chemlit_extractor.database import get_db_session, ArticleCRUD
from chemlit_extractor.services.article_service import ArticleService

logger = logging.getLogger(__name__)


class DataMigrationHelper:
    """Helper for migrating existing data to work with new service architecture."""

    @staticmethod
    def validate_existing_articles(limit: int = 100) -> Dict[str, Any]:
        """
        Validate existing articles work with new service architecture.

        Returns:
            Dictionary with validation results and any issues found.
        """
        issues = []
        validated_count = 0

        with get_db_session() as db:
            articles = ArticleCRUD.get_multi(db, skip=0, limit=limit)

            for article in articles:
                try:
                    # Test that ArticleService can retrieve the article
                    with ArticleService(db_session=db) as service:
                        retrieved = service.get_article(article.doi)
                        if not retrieved:
                            issues.append(f"Could not retrieve article: {article.doi}")
                        else:
                            validated_count += 1

                except Exception as e:
                    issues.append(f"Error validating {article.doi}: {str(e)}")

        return {
            "validated_count": validated_count,
            "total_articles": len(articles),
            "issues": issues,
            "success_rate": validated_count / len(articles) if articles else 1.0,
        }

    @staticmethod
    def check_file_structure_compatibility() -> Dict[str, Any]:
        """
        Check that existing file storage structure is compatible.

        Returns:
            Compatibility report.
        """
        from chemlit_extractor.core.config import settings
        from pathlib import Path

        issues = []
        articles_with_files = 0

        articles_path = settings.articles_path
        if not articles_path.exists():
            return {"compatible": True, "message": "No existing files to check"}

        for article_dir in articles_path.iterdir():
            if article_dir.is_dir():
                articles_with_files += 1

                # Check expected subdirectories
                expected_subdirs = ["pdf", "html", "supplementary", "images"]
                for subdir in expected_subdirs:
                    subdir_path = article_dir / subdir
                    if subdir_path.exists() and not subdir_path.is_dir():
                        issues.append(
                            f"Expected directory but found file: {subdir_path}"
                        )

        return {
            "compatible": len(issues) == 0,
            "articles_with_files": articles_with_files,
            "issues": issues,
        }
