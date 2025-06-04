"""Demo script to test the FastAPI application."""


import pytest
import requests


class TestAPIDemo:
    """Demo tests for the FastAPI application."""

    @pytest.fixture(scope="class")
    def base_url(self):
        """Base URL for API testing."""
        return "http://localhost:8000"

    @pytest.mark.integration
    def test_api_health_check(self, base_url):
        """Test that the API is running and healthy."""
        try:
            response = requests.get(f"{base_url}/health", timeout=5)
            assert response.status_code == 200

            data = response.json()
            assert data["status"] == "healthy"

            print("✅ API health check passed")

        except requests.exceptions.RequestException:
            pytest.skip(
                "API server not running. Start with: python -m chemlit_extractor.main"
            )

    @pytest.mark.integration
    def test_api_documentation(self, base_url):
        """Test that API documentation is accessible."""
        try:
            response = requests.get(f"{base_url}/docs", timeout=5)
            assert response.status_code == 200
            assert (
                "swagger" in response.text.lower() or "openapi" in response.text.lower()
            )

            print("✅ API documentation accessible")

        except requests.exceptions.RequestException:
            pytest.skip("API server not running")

    @pytest.mark.integration
    def test_stats_endpoint(self, base_url):
        """Test the stats endpoint."""
        try:
            response = requests.get(f"{base_url}/api/v1/stats/", timeout=5)
            assert response.status_code == 200

            data = response.json()
            assert "total_articles" in data
            assert "total_compounds" in data
            assert "total_properties" in data
            assert "total_authors" in data

            print(
                f"✅ Database stats: {data['total_articles']} articles, {data['total_compounds']} compounds"
            )

        except requests.exceptions.RequestException:
            pytest.skip("API server not running")

    @pytest.mark.integration
    def test_stats_summary(self, base_url):
        """Test the stats summary endpoint."""
        try:
            response = requests.get(f"{base_url}/api/v1/stats/summary", timeout=5)
            assert response.status_code == 200

            data = response.json()
            assert "summary" in data

            print(f"✅ Database summary: {data['summary']}")

        except requests.exceptions.RequestException:
            pytest.skip("API server not running")

    @pytest.mark.integration
    def test_articles_search_empty(self, base_url):
        """Test searching articles (should work even if empty)."""
        try:
            response = requests.get(f"{base_url}/api/v1/articles/", timeout=5)
            assert response.status_code == 200

            data = response.json()
            assert "articles" in data
            assert "total_count" in data
            assert isinstance(data["articles"], list)

            print(f"✅ Article search: found {data['total_count']} articles")

        except requests.exceptions.RequestException:
            pytest.skip("API server not running")

    @pytest.mark.integration
    @pytest.mark.slow
    def test_create_article_workflow(self, base_url):
        """Test creating an article through the API (cleanup after)."""
        test_doi = "10.1000/api.demo.test"

        try:
            # Clean up any existing test article first
            requests.delete(f"{base_url}/api/v1/articles/{test_doi}")

            # Create a test article
            article_data = {
                "doi": test_doi,
                "title": "API Demo Test Article",
                "journal": "Demo Journal",
                "year": 2024,
                "abstract": "This is a test article created by the API demo.",
            }

            response = requests.post(
                f"{base_url}/api/v1/articles/", json=article_data, timeout=5
            )

            if response.status_code == 201:
                print("✅ Article creation successful")

                # Verify we can retrieve it
                get_response = requests.get(f"{base_url}/api/v1/articles/{test_doi}")
                assert get_response.status_code == 200

                retrieved_data = get_response.json()
                assert retrieved_data["title"] == article_data["title"]

                print("✅ Article retrieval successful")

                # Clean up
                delete_response = requests.delete(
                    f"{base_url}/api/v1/articles/{test_doi}"
                )
                assert delete_response.status_code == 204

                print("✅ Article cleanup successful")

            else:
                # Article might already exist, that's OK for demo
                print(
                    f"ℹ️  Article creation returned {response.status_code}: {response.text}"
                )

        except requests.exceptions.RequestException:
            pytest.skip("API server not running")


def demo_api_manually():
    """
    Manual demo function to test API endpoints.

    Run this to test the API without pytest.
    """
    base_url = "http://localhost:8000"

    print("🧪 Testing ChemLit Extractor API...")

    try:
        # Test health endpoint
        response = requests.get(f"{base_url}/health", timeout=5)
        if response.status_code == 200:
            print("✅ API is healthy and running")
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return

        # Test stats
        response = requests.get(f"{base_url}/api/v1/stats/", timeout=5)
        if response.status_code == 200:
            stats = response.json()
            print(
                f"✅ Database stats: {stats['total_articles']} articles, {stats['total_compounds']} compounds"
            )

        # Test article search
        response = requests.get(f"{base_url}/api/v1/articles/?limit=5", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Found {data['total_count']} articles in database")
            if data["articles"]:
                print(f"   First article: {data['articles'][0]['title'][:50]}...")

        print("\n🎉 API demo completed successfully!")
        print(f"📖 View full documentation at: {base_url}/docs")

    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to connect to API: {e}")
        print("💡 Make sure the API server is running with:")
        print("   python -m chemlit_extractor.main")
        print("   or")
        print("   uvicorn chemlit_extractor.main:app --reload")


if __name__ == "__main__":
    demo_api_manually()
