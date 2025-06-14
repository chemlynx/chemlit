# tests/integration/test_crossref_publishers.py
"""
Integration tests for CrossRef publisher variations.

These tests use real CrossRef responses to identify parsing issues.
Run with: pytest tests/integration/test_crossref_publishers.py -v
"""

import pytest

from chemlit_extractor.models.crossref import CrossRefWork
from chemlit_extractor.services.crossref import CrossRefService


class TestCrossRefPublisherParsing:
    """Test real CrossRef responses from different publishers."""

    def test_rsc_response_parsing(self):
        """Test RSC response with JATS markup in abstract."""
        rsc_data = {
            "DOI": "10.1039/d5ob00519a",
            "title": [
                "Triflic acid catalyzed intermolecular hydroamination of alkenes"
            ],
            "container-title": ["Organic & Biomolecular Chemistry"],
            "volume": "23",
            "issue": "22",
            "published-online": {"date-parts": [[2025]]},  # Year only
            "abstract": "<jats:p>We used Fmoc-NH<jats:sub>2</jats:sub> as the amine source.</jats:p>",
            "author": [{"given": "Test", "family": "Author", "sequence": "first"}],
        }

        service = CrossRefService()
        work = CrossRefWork(**rsc_data)
        article, authors = service._convert_crossref_to_schemas(work)

        assert article.doi == "10.1039/d5ob00519a"
        assert article.year == 2025

        # This will likely fail if JATS cleaning not implemented:
        if article.abstract:
            assert (
                "<jats:p>" not in article.abstract
            ), "JATS paragraph tags should be cleaned"
            assert (
                "<jats:sub>" not in article.abstract
            ), "JATS subscript tags should be cleaned"

    def test_beilstein_response_missing_issue(self):
        """Test Beilstein response with missing issue field."""
        beilstein_data = {
            "DOI": "10.3762/bjoc.21.83",
            "title": ["Pd-Catalyzed asymmetric allylic amination"],
            "container-title": ["Beilstein Journal of Organic Chemistry"],
            "volume": "21",
            # Note: No "issue" field
            "published-online": {"date-parts": [[2025, 5, 23]]},
            "abstract": "<jats:p>Test with <jats:italic>italic</jats:italic> text.</jats:p>",
            "author": [{"given": "Test", "family": "Author", "sequence": "first"}],
        }

        service = CrossRefService()
        work = CrossRefWork(**beilstein_data)
        article, authors = service._convert_crossref_to_schemas(work)

        assert article.doi == "10.3762/bjoc.21.83"
        assert article.year == 2025
        assert article.volume == "21"
        assert article.issue is None  # Should handle missing issue gracefully

        # Check JATS cleaning
        if article.abstract:
            assert (
                "<jats:italic>" not in article.abstract
            ), "JATS italic tags should be cleaned"

    def test_acs_response_missing_abstract(self):
        """Test ACS response with missing abstract field."""
        acs_data = {
            "DOI": "10.1021/acs.joc.5c00313",
            "title": ["The Synthesis of a Naloxone-Related Oxidative Drug Product"],
            "container-title": ["The Journal of Organic Chemistry"],
            "volume": "90",
            "issue": "16",
            "published-online": {"date-parts": [[2025, 4, 14]]},
            # Note: No "abstract" field
            "author": [{"given": "Test", "family": "Author", "sequence": "first"}],
        }

        service = CrossRefService()
        work = CrossRefWork(**acs_data)
        article, authors = service._convert_crossref_to_schemas(work)

        assert article.doi == "10.1021/acs.joc.5c00313"
        assert article.year == 2025
        assert article.volume == "90"
        assert article.issue == "16"

        # This will likely fail if missing abstract not handled:
        assert (
            article.abstract is None
        ), "Missing abstract should be None, not cause error"

    @pytest.mark.parametrize(
        "date_parts,expected_year",
        [
            ([[2025]], 2025),  # RSC: year only
            ([[2025, 5]], 2025),  # Year and month
            ([[2025, 5, 23]], 2025),  # Full date
            ([[2024, 12, 31]], 2024),  # Different year
        ],
    )
    def test_date_parsing_variations(self, date_parts, expected_year):
        """Test different date format parsing."""
        test_data = {
            "DOI": "10.1000/test",
            "title": ["Test Article"],
            "published-online": {"date-parts": date_parts},
            "author": [{"given": "Test", "family": "Author", "sequence": "first"}],
        }

        service = CrossRefService()
        work = CrossRefWork(**test_data)
        article, authors = service._convert_crossref_to_schemas(work)

        assert article.year == expected_year


# Simple integration marker
pytestmark = pytest.mark.integration
