"""Validation helpers for ensuring migration success."""

import httpx
from typing import List, Dict, Any
from chemlit_extractor.services.article_service import get_article_service_context


class MigrationValidator:
    """Validates that migration was successful."""

    @staticmethod
    def test_api_compatibility(
        base_url: str = "http://localhost:8000",
    ) -> Dict[str, Any]:
        """
        Test that all API endpoints still work after migration.

        Args:
            base_url: Base URL of the API.

        Returns:
            Test results for each endpoint.
        """
        test_results = {}

        # Test endpoints
        endpoints = [
            ("GET", "/api/v1/stats"),
            ("GET", "/api/v1/articles"),
            ("GET", "/docs"),
            ("GET", "/health"),
        ]

        for method, endpoint in endpoints:
            try:
                url = f"{base_url}{endpoint}"
                response = httpx.request(method, url, timeout=10)

                test_results[endpoint] = {
                    "status_code": response.status_code,
                    "success": response.status_code < 400,
                    "response_time": response.elapsed.total_seconds(),
                }

            except Exception as e:
                test_results[endpoint] = {
                    "success": False,
                    "error": str(e),
                }

        success_count = sum(
            1 for result in test_results.values() if result.get("success")
        )

        return {
            "total_endpoints": len(endpoints),
            "successful_endpoints": success_count,
            "success_rate": success_count / len(endpoints),
            "results": test_results,
        }

    @staticmethod
    def test_service_functionality(
        test_doi: str = "10.1039/d5ob00519a",
    ) -> Dict[str, Any]:
        """
        Test core ArticleService functionality.

        Args:
            test_doi: DOI to use for testing.

        Returns:
            Test results.
        """
        test_results = {}

        try:
            with get_article_service_context() as service:
                # Test article lookup
                existing = service.get_article(test_doi)
                test_results["get_article"] = {
                    "success": True,
                    "found": existing is not None,
                }

                # Test article existence check
                exists = service.article_exists(test_doi)
                test_results["article_exists"] = {"success": True, "exists": exists}

                # Test registration (should handle existing article gracefully)
                result = service.register_article(
                    doi=test_doi,
                    fetch_metadata=True,
                    download_files=False,
                )
                test_results["register_article"] = {
                    "success": True,
                    "status": result.status,
                    "message": result.message,
                }

        except Exception as e:
            test_results["error"] = {"success": False, "error": str(e)}

        return test_results
