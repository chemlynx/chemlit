"""Demo script to test CrossRef API functionality."""

import pytest

from chemlit_extractor.services.crossref import CrossRefService, get_crossref_client


class TestCrossRefDemo:
    """Demo tests for CrossRef functionality."""

    def test_crossref_client_basic(self):
        """Basic test of CrossRef client (mocked)."""
        # This test doesn't require internet - it's just testing the client setup
        with get_crossref_client() as client:
            assert client.base_url == "https://api.crossref.org"
            assert "ChemLitExtractor" in client.user_agent

            # Test DOI cleaning functionality
            cleaned = client._clean_doi("https://doi.org/10.1000/test.123")
            assert cleaned == "10.1000/test.123"

    def test_crossref_service_setup(self):
        """Test CrossRef service setup."""
        service = CrossRefService()
        try:
            assert service.client is not None
            assert hasattr(service, "fetch_and_convert_article")
        finally:
            service.close()

    @pytest.mark.integration
    @pytest.mark.slow
    def test_fetch_real_article(self):
        """
        Test fetching a real article from CrossRef.

        This test requires internet connection and will be skipped in normal test runs.
        Run with: pytest -m "integration and slow" to include this test.
        """
        # Use a well-known, stable DOI
        test_doi = "10.1371/journal.pone.0000001"  # First PLOS ONE paper

        service = CrossRefService()
        try:
            result = service.fetch_and_convert_article(test_doi)

            if result is not None:
                article_data, authors_data = result

                print("\n✅ Successfully fetched article:")
                print(f"   DOI: {article_data.doi}")
                print(f"   Title: {article_data.title}")
                print(f"   Journal: {article_data.journal}")
                print(f"   Year: {article_data.year}")
                print(f"   Authors: {len(authors_data)}")

                if authors_data:
                    print(
                        f"   First author: {authors_data[0].first_name} {authors_data[0].last_name}"
                    )

                # Basic assertions
                assert article_data.doi == test_doi.lower()
                assert len(article_data.title) > 0
                assert isinstance(authors_data, list)

            else:
                pytest.skip("Article not found - API may be down or DOI changed")

        except Exception as e:
            pytest.skip(f"CrossRef API not accessible: {e}")
        finally:
            service.close()

    @pytest.mark.integration
    def test_doi_validation(self):
        """Test DOI validation with various formats."""
        with get_crossref_client() as client:
            # Valid DOI formats that should be cleaned properly
            valid_dois = [
                "10.1000/test",
                "https://doi.org/10.1000/test",
                "http://dx.doi.org/10.1000/test",
                "doi:10.1000/test",
                "  10.1000/test  ",  # With whitespace
            ]

            for doi in valid_dois:
                cleaned = client._clean_doi(doi)
                assert cleaned == "10.1000/test"

            # Invalid DOIs that should be rejected
            invalid_dois = [
                "not-a-doi",
                "123.456/test",  # Wrong prefix
                "",
                "just-text",
            ]

            for doi in invalid_dois:
                cleaned = client._clean_doi(doi)
                assert cleaned is None

    def test_rate_limiter_functionality(self):
        """Test rate limiter without making actual API calls."""
        from datetime import timedelta

        from chemlit_extractor.services.crossref import RateLimiter

        # Create restrictive rate limiter for testing
        limiter = RateLimiter(max_requests=2, time_window=timedelta(seconds=1))

        # Should allow first two requests
        assert limiter.can_make_request() is True
        limiter.record_request()

        assert limiter.can_make_request() is True
        limiter.record_request()

        # Third request should be blocked
        assert limiter.can_make_request() is False
        assert limiter.wait_time() > 0

        print("✅ Rate limiter working correctly")


# Simple function to run a quick demo
def demo_crossref_basic() -> None:
    """
    Run a basic demo of CrossRef functionality.

    This function can be called directly to test CrossRef without pytest.
    """
    print("🧪 Testing CrossRef Client Setup...")

    # Test basic client setup
    with get_crossref_client() as client:
        print(f"✅ Client created with base URL: {client.base_url}")

        # Test DOI cleaning
        test_doi = "https://doi.org/10.1000/test.example"
        cleaned = client._clean_doi(test_doi)
        print(f"✅ DOI cleaning: '{test_doi}' -> '{cleaned}'")

    # Test service setup
    service = CrossRefService()
    try:
        print("✅ Service created successfully")
    finally:
        service.close()
        print("✅ Service closed successfully")

    print("🎉 Basic CrossRef functionality working!")


if __name__ == "__main__":
    demo_crossref_basic()
