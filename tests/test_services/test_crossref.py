"""Test CrossRef API client."""

import time
from datetime import timedelta
from unittest.mock import Mock, patch

import httpx
import pytest

from chemlit_extractor.models.schemas import CrossRefResponse
from chemlit_extractor.services.crossref import (
    CrossRefClient,
    CrossRefService,
    RateLimiter,
)


class TestRateLimiter:
    """Test rate limiter functionality."""

    def test_initial_state(self):
        """Test rate limiter initial state."""
        limiter = RateLimiter(max_requests=5, time_window=timedelta(minutes=1))

        assert limiter.can_make_request() is True
        assert limiter.wait_time() == 0.0

    def test_record_request(self):
        """Test recording requests."""
        limiter = RateLimiter(max_requests=2, time_window=timedelta(minutes=1))

        # Should be able to make first request
        assert limiter.can_make_request() is True
        limiter.record_request()

        # Should be able to make second request
        assert limiter.can_make_request() is True
        limiter.record_request()

        # Should not be able to make third request
        assert limiter.can_make_request() is False

    def test_time_window_expiry(self):
        """Test that old requests expire."""
        limiter = RateLimiter(max_requests=1, time_window=timedelta(milliseconds=100))

        # Make a request
        limiter.record_request()
        assert limiter.can_make_request() is False

        # Wait for time window to expire
        time.sleep(0.15)  # 150ms > 100ms window

        # Should be able to make request again
        assert limiter.can_make_request() is True

    def test_wait_time_calculation(self):
        """Test wait time calculation."""
        limiter = RateLimiter(max_requests=1, time_window=timedelta(seconds=1))

        # Make a request
        limiter.record_request()

        # Should need to wait
        wait_time = limiter.wait_time()
        assert 0 < wait_time <= 1.0


class TestCrossRefClient:
    """Test CrossRef client functionality."""

    @pytest.fixture
    def mock_httpx_client(self):
        """Mock httpx client."""
        with patch("chemlit_extractor.services.crossref.httpx.Client") as mock_client:
            yield mock_client

    @pytest.fixture
    def sample_crossref_response(self):
        """Sample CrossRef API response."""
        return {
            "message": {
                "DOI": "10.1000/test",
                "title": ["Test Article Title"],
                "author": [
                    {
                        "given": "John",
                        "family": "Doe",
                        "ORCID": "http://orcid.org/0000-0000-0000-0001",
                    }
                ],
                "published-print": {"date-parts": [[2023, 6, 15]]},
                "container-title": ["Test Journal"],
                "publisher": "Test Publisher",
                "volume": "42",
                "issue": "3",
                "page": "123-130",
                "abstract": "This is a test abstract.",
                "URL": "https://example.com/article",
            }
        }

    def test_clean_doi_valid(self):
        """Test DOI cleaning with valid DOIs."""
        test_cases = [
            ("10.1000/test", "10.1000/test"),
            ("10.1000/TEST", "10.1000/test"),  # Lowercase conversion
            ("https://doi.org/10.1000/test", "10.1000/test"),
            ("http://dx.doi.org/10.1000/test", "10.1000/test"),
            ("doi:10.1000/test", "10.1000/test"),
            ("  10.1000/test  ", "10.1000/test"),  # Whitespace removal
        ]

        for input_doi, expected in test_cases:
            result = CrossRefClient._clean_doi(input_doi)
            assert result == expected, f"Failed for input: {input_doi}"

    def test_clean_doi_invalid(self):
        """Test DOI cleaning with invalid DOIs."""
        invalid_dois = [
            "",
            "invalid-doi",
            "not.a.doi",
            "123.456/test",  # Doesn't start with 10.
            None,
        ]

        for invalid_doi in invalid_dois:
            result = CrossRefClient._clean_doi(invalid_doi)
            assert result is None, f"Should have rejected: {invalid_doi}"

    def test_init_with_defaults(self):
        """Test client initialization with default values."""
        client = CrossRefClient()

        assert client.base_url == "https://api.crossref.org"
        assert "ChemLitExtractor" in client.user_agent
        assert client.rate_limiter.max_requests == 10

    def test_init_with_custom_values(self):
        """Test client initialization with custom values."""
        custom_user_agent = "TestAgent/1.0"
        client = CrossRefClient(rate_limit=5, user_agent=custom_user_agent)

        assert client.user_agent == custom_user_agent
        assert client.rate_limiter.max_requests == 5

    def test_context_manager(self, mock_httpx_client):
        """Test client as context manager."""
        mock_instance = Mock()
        mock_httpx_client.return_value = mock_instance

        with CrossRefClient() as client:
            assert client is not None

        mock_instance.close.assert_called_once()

    @patch("time.sleep")
    def test_rate_limiting(self, mock_sleep, mock_httpx_client):
        """Test that rate limiting works."""
        # Setup mock
        mock_instance = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"DOI": "10.1000/test", "title": ["Test"]}
        }
        mock_instance.get.return_value = mock_response
        mock_httpx_client.return_value = mock_instance

        # Create client with very restrictive rate limit
        client = CrossRefClient(rate_limit=1)

        # Make first request (should work)
        result1 = client.get_article_by_doi("10.1000/test1")
        assert result1 is not None

        # Make second request (should trigger rate limiting)
        client.get_article_by_doi("10.1000/test2")

        # Should have called sleep due to rate limiting
        mock_sleep.assert_called()

        client.close()

    def test_get_article_success(self, mock_httpx_client, sample_crossref_response):
        """Test successful article retrieval."""
        # Setup mock
        mock_instance = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_crossref_response
        mock_instance.get.return_value = mock_response
        mock_httpx_client.return_value = mock_instance

        client = CrossRefClient()
        result = client.get_article_by_doi("10.1000/test")

        assert result is not None
        assert isinstance(result, CrossRefResponse)
        assert result.DOI == "10.1000/test"
        assert result.title == ["Test Article Title"]

        client.close()

    def test_get_article_not_found(self, mock_httpx_client):
        """Test article not found (404)."""
        # Setup mock for 404
        mock_instance = Mock()
        mock_response = Mock()
        mock_response.status_code = 404
        mock_instance.get.return_value = mock_response
        mock_instance.get.return_value.raise_for_status.side_effect = (
            httpx.HTTPStatusError("404", request=Mock(), response=mock_response)
        )
        mock_httpx_client.return_value = mock_instance

        client = CrossRefClient()
        result = client.get_article_by_doi("10.1000/nonexistent")

        assert result is None
        client.close()

    def test_get_article_invalid_doi(self, mock_httpx_client):
        """Test error with invalid DOI."""
        mock_httpx_client.return_value = Mock()

        client = CrossRefClient()

        with pytest.raises(ValueError, match="Invalid DOI format"):
            client.get_article_by_doi("invalid-doi")

        client.close()

    def test_get_article_http_error(self, mock_httpx_client):
        """Test HTTP error handling."""
        # Setup mock for 500 error
        mock_instance = Mock()
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_instance.get.return_value = mock_response
        mock_instance.get.return_value.raise_for_status.side_effect = (
            httpx.HTTPStatusError("500", request=Mock(), response=mock_response)
        )
        mock_httpx_client.return_value = mock_instance

        client = CrossRefClient()

        with pytest.raises(httpx.HTTPError, match="HTTP 500"):
            client.get_article_by_doi("10.1000/test")

        client.close()

    def test_search_articles_success(self, mock_httpx_client, sample_crossref_response):
        """Test successful article search."""
        # Setup mock
        mock_instance = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"items": [sample_crossref_response["message"]]}
        }
        mock_instance.get.return_value = mock_response
        mock_httpx_client.return_value = mock_instance

        client = CrossRefClient()
        results = client.search_articles("test query", limit=10)

        assert len(results) == 1
        assert isinstance(results[0], CrossRefResponse)
        assert results[0].DOI == "10.1000/test"

        # Verify correct parameters were passed
        mock_instance.get.assert_called_once()
        call_args = mock_instance.get.call_args
        assert call_args[1]["params"]["query"] == "test query"
        assert call_args[1]["params"]["rows"] == 10

        client.close()

    def test_search_articles_empty_results(self, mock_httpx_client):
        """Test search with no results."""
        # Setup mock
        mock_instance = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"items": []}}
        mock_instance.get.return_value = mock_response
        mock_httpx_client.return_value = mock_instance

        client = CrossRefClient()
        results = client.search_articles("nonexistent query")

        assert results == []
        client.close()


class TestCrossRefService:
    """Test CrossRef service functionality."""

    @pytest.fixture
    def mock_client(self):
        """Mock CrossRef client."""
        return Mock(spec=CrossRefClient)

    @pytest.fixture
    def sample_crossref_data(self):
        """Sample CrossRef response object."""
        return CrossRefResponse(
            DOI="10.1000/test",
            title=["Test Article Title"],
            author=[
                {
                    "given": "John",
                    "family": "Doe",
                    "ORCID": "http://orcid.org/0000-0000-0000-0001",
                },
                {"given": "Jane", "family": "Smith", "ORCID": None},
            ],
            published_print={"date-parts": [[2023, 6, 15]]},
            container_title=["Test Journal"],
            publisher="Test Publisher",
            volume="42",
            issue="3",
            page="123-130",
            abstract="This is a test abstract.",
            URL="https://example.com/article",
        )

    def test_fetch_and_convert_success(self, mock_client, sample_crossref_data):
        """Test successful fetch and conversion."""
        mock_client.get_article_by_doi.return_value = sample_crossref_data

        service = CrossRefService(client=mock_client)
        result = service.fetch_and_convert_article("10.1000/test")

        assert result is not None
        article_data, authors_data = result

        # Check article data
        assert article_data.doi == "10.1000/test"
        assert article_data.title == "Test Article Title"
        assert article_data.journal == "Test Journal"
        assert article_data.year == 2023
        assert article_data.volume == "42"

        # Check authors data
        assert len(authors_data) == 2
        assert authors_data[0].first_name == "John"
        assert authors_data[0].last_name == "Doe"
        assert authors_data[0].orcid == "0000-0000-0000-0001"  # Should strip URL
        assert authors_data[1].first_name == "Jane"
        assert authors_data[1].orcid is None

    def test_fetch_and_convert_not_found(self, mock_client):
        """Test fetch when article not found."""
        mock_client.get_article_by_doi.return_value = None

        service = CrossRefService(client=mock_client)
        result = service.fetch_and_convert_article("10.1000/nonexistent")

        assert result is None

    def test_convert_minimal_crossref_data(self, mock_client):
        """Test conversion with minimal CrossRef data."""
        minimal_data = CrossRefResponse(
            DOI="10.1000/minimal",
            title=None,  # Missing title
            author=None,  # No authors
            published_print=None,  # No publication date
            container_title=None,  # No journal
        )

        mock_client.get_article_by_doi.return_value = minimal_data

        service = CrossRefService(client=mock_client)
        result = service.fetch_and_convert_article("10.1000/minimal")

        assert result is not None
        article_data, authors_data = result

        # Should handle missing data gracefully
        assert article_data.doi == "10.1000/minimal"
        assert article_data.title == "Unknown Title"
        assert article_data.journal is None
        assert article_data.year is None
        assert len(authors_data) == 0

    def test_convert_year_from_online_date(self, mock_client):
        """Test year extraction from online publication date."""
        data_with_online_date = CrossRefResponse(
            DOI="10.1000/online",
            title=["Online Article"],
            published_online={"date-parts": [[2022, 12, 1]]},  # Only online date
            published_print=None,  # No print date
        )

        mock_client.get_article_by_doi.return_value = data_with_online_date

        service = CrossRefService(client=mock_client)
        result = service.fetch_and_convert_article("10.1000/online")

        assert result is not None
        article_data, _ = result
        assert article_data.year == 2022  # Should extract from online date

    def test_service_close(self, mock_client):
        """Test service close method."""
        service = CrossRefService(client=mock_client)
        service.close()

        mock_client.close.assert_called_once()


@pytest.mark.integration
class TestCrossRefIntegration:
    """Integration tests with real CrossRef API."""

    @pytest.mark.slow
    def test_real_api_call(self):
        """Test actual API call to CrossRef (requires internet)."""
        # Use a well-known DOI that should always exist
        test_doi = "10.1038/nature12373"  # Famous Nature paper

        with CrossRefClient(rate_limit=5) as client:
            try:
                result = client.get_article_by_doi(test_doi)

                assert result is not None
                assert isinstance(result, CrossRefResponse)
                assert result.DOI.endswith("nature12373")
                assert result.title is not None
                assert len(result.title) > 0

                print(f"✅ Successfully fetched: {result.title[0][:50]}...")

            except httpx.HTTPError as e:
                pytest.skip(f"CrossRef API not accessible: {e}")

    @pytest.mark.slow
    def test_real_service_integration(self):
        """Test service with real API call."""
        test_doi = "10.1038/nature12373"

        service = CrossRefService()
        try:
            result = service.fetch_and_convert_article(test_doi)

            if result is not None:
                article_data, authors_data = result

                assert article_data.doi == test_doi.lower()
                assert len(article_data.title) > 0
                assert isinstance(authors_data, list)

                print(
                    f"✅ Service integration successful: {len(authors_data)} authors found"
                )
            else:
                pytest.skip("Article not found - API may be down or DOI changed")

        except httpx.HTTPError as e:
            pytest.skip(f"CrossRef API not accessible: {e}")
        finally:
            service.close()

    @pytest.mark.slow
    def test_real_search_functionality(self):
        """Test search with real API."""
        with CrossRefClient(rate_limit=5) as client:
            try:
                results = client.search_articles("machine learning", limit=5)

                assert isinstance(results, list)
                assert len(results) <= 5

                if len(results) > 0:
                    # Check first result has expected structure
                    first_result = results[0]
                    assert isinstance(first_result, CrossRefResponse)
                    assert first_result.DOI is not None

                print(f"✅ Search returned {len(results)} results")

            except httpx.HTTPError as e:
                pytest.skip(f"CrossRef API not accessible: {e}")

    def test_rate_limiting_real(self):
        """Test rate limiting with multiple real requests."""
        # Use a very restrictive rate limit for testing
        with CrossRefClient(rate_limit=2) as client:
            try:
                start_time = time.time()

                # Make 3 requests - should trigger rate limiting
                for i in range(3):
                    client.get_article_by_doi(f"10.1038/nature{12370 + i}")

                end_time = time.time()
                elapsed = end_time - start_time

                # Should take at least some time due to rate limiting
                # (but don't make it too strict to avoid flaky tests)
                assert elapsed > 0.5  # Should take at least 500ms

                print(f"✅ Rate limiting test completed in {elapsed:.2f}s")

            except httpx.HTTPError as e:
                pytest.skip(f"CrossRef API not accessible: {e}")


class TestCrossRefFactoryFunctions:
    """Test factory functions for CrossRef components."""

    def test_get_crossref_client(self):
        """Test CrossRef client factory function."""
        from chemlit_extractor.services.crossref import get_crossref_client

        client = get_crossref_client()
        assert isinstance(client, CrossRefClient)
        assert client.base_url == "https://api.crossref.org"
        client.close()

    def test_get_crossref_service(self):
        """Test CrossRef service factory function."""
        from chemlit_extractor.services.crossref import get_crossref_service

        service = get_crossref_service()
        assert isinstance(service, CrossRefService)
        assert isinstance(service.client, CrossRefClient)
        service.close()


class TestCrossRefErrorHandling:
    """Test error handling in CrossRef components."""

    def test_invalid_json_response(self, mock_httpx_client):
        """Test handling of invalid JSON response."""
        mock_instance = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_instance.get.return_value = mock_response
        mock_httpx_client.return_value = mock_instance

        client = CrossRefClient()

        with pytest.raises(httpx.HTTPError, match="Failed to fetch article data"):
            client.get_article_by_doi("10.1000/test")

        client.close()

    def test_network_timeout(self, mock_httpx_client):
        """Test handling of network timeout."""
        mock_instance = Mock()
        mock_instance.get.side_effect = httpx.TimeoutException("Request timeout")
        mock_httpx_client.return_value = mock_instance

        client = CrossRefClient()

        with pytest.raises(httpx.HTTPError, match="Failed to fetch article data"):
            client.get_article_by_doi("10.1000/test")

        client.close()

    def test_malformed_crossref_data(self, mock_client):
        """Test handling of malformed CrossRef data in service."""
        # Create data that will fail Pydantic validation
        malformed_data = CrossRefResponse(
            DOI="10.1000/test",
            title=["Test"],
            author=[
                {
                    "given": "",  # Empty name should still work
                    "family": "",
                    "ORCID": "invalid-orcid-format",
                }
            ],
        )

        mock_client.get_article_by_doi.return_value = malformed_data

        service = CrossRefService(client=mock_client)
        result = service.fetch_and_convert_article("10.1000/test")

        # Should handle gracefully
        assert result is not None
        article_data, authors_data = result

        # Should use "Unknown" for empty names
        assert authors_data[0].first_name == "Unknown"
        assert authors_data[0].last_name == "Unknown"
