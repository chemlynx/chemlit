# tests/integration/test_publisher_variations.py
"""
Integration test for CrossRef publisher variations.

Tests your existing CrossRef service against real publisher responses
to identify what breaks with different data formats.
"""

from unittest.mock import Mock

import pytest

from chemlit_extractor.models.schemas import CrossRefResponse
from chemlit_extractor.services.crossref import CrossRefService


class TestPublisherVariations:
    """Test CrossRef service against real publisher data variations."""

    def test_rsc_publisher_response(self):
        """Test RSC response with JATS markup and year-only date."""
        # Real RSC response structure
        rsc_data = CrossRefResponse(
            DOI="10.1039/d5ob00519a",
            title=[
                "Triflic acid catalyzed intermolecular hydroamination of alkenes with Fmoc-NH<sub>2</sub> as the amine source"
            ],
            container_title=["Organic & Biomolecular Chemistry"],
            publisher="Royal Society of Chemistry (RSC)",
            volume="23",
            issue="22",
            page="5352-5358",
            published_online={"date-parts": [[2025]]},  # Year only!
            abstract="<jats:p>We used Fmoc-NH<jats:sub>2</jats:sub> as the amine source for the Brønsted acid-catalysed hydroamination of alkenes, and the mechanism was investigated using NMR and VNTA techniques.</jats:p>",
            author=[
                {"given": "Aswathi C.", "family": "S."},
                {
                    "given": "Chinraj",
                    "family": "Sivarajan",
                    "ORCID": "https://orcid.org/0000-0002-0496-0645",
                },
                {
                    "given": "Raja",
                    "family": "Mitra",
                    "ORCID": "https://orcid.org/0000-0002-3317-3800",
                },
            ],
        )

        # Mock the client to return our test data
        mock_client = Mock()
        mock_client.get_article_by_doi.return_value = rsc_data

        # Test your existing service
        service = CrossRefService(client=mock_client)
        result = service.fetch_and_convert_article("10.1039/d5ob00519a")

        assert result is not None
        article_data, authors_data = result

        # Basic assertions
        assert article_data.doi == "10.1039/d5ob00519a"
        assert "Triflic acid" in article_data.title
        assert article_data.year == 2025  # Should extract from year-only date

        # Check JATS markup handling - this will likely FAIL if not implemented:
        print(f"RSC Abstract: {article_data.abstract}")
        if article_data.abstract:
            # These assertions will show what currently breaks:
            jats_tags_present = any(
                tag in article_data.abstract
                for tag in ["<jats:p>", "<jats:sub>", "</jats:p>"]
            )
            if jats_tags_present:
                print("⚠️  RSC: JATS markup not cleaned from abstract")

        # Check authors
        assert len(authors_data) == 3
        assert authors_data[0].first_name == "Aswathi C."

    def test_beilstein_publisher_response(self):
        """Test Beilstein response with missing issue field and JATS markup."""
        beilstein_data = CrossRefResponse(
            DOI="10.3762/bjoc.21.83",
            title=[
                "Pd-Catalyzed asymmetric allylic amination with isatin using a P,olefin-type chiral ligand"
            ],
            container_title=["Beilstein Journal of Organic Chemistry"],
            publisher="Beilstein Institut",
            volume="21",
            # Note: No "issue" field for Beilstein!
            page="1018-1023",
            published_online={"date-parts": [[2025, 5, 23]]},  # Full date
            abstract="<jats:p>In this study, we implemented the P,olefin-type chiral ligand (a<jats:italic>R</jats:italic>)-(-)-<jats:bold>6</jats:bold>, which contains a cyclohexyl group.</jats:p>",
            author=[
                {"given": "Natsume", "family": "Akimoto"},
                {"given": "Kaho", "family": "Takaya"},
                {
                    "given": "Yoshio",
                    "family": "Kasashima",
                    "ORCID": "https://orcid.org/0000-0002-6224-4495",
                },
            ],
        )

        mock_client = Mock()
        mock_client.get_article_by_doi.return_value = beilstein_data

        service = CrossRefService(client=mock_client)
        result = service.fetch_and_convert_article("10.3762/bjoc.21.83")

        assert result is not None
        article_data, authors_data = result

        assert article_data.doi == "10.3762/bjoc.21.83"
        assert article_data.year == 2025
        assert article_data.volume == "21"
        # This should be None since Beilstein doesn't provide issue:
        print(f"Beilstein issue field: {article_data.issue}")

        # Check JATS markup handling
        print(f"Beilstein Abstract: {article_data.abstract}")
        if article_data.abstract:
            jats_tags_present = any(
                tag in article_data.abstract for tag in ["<jats:italic>", "<jats:bold>"]
            )
            if jats_tags_present:
                print("⚠️  Beilstein: JATS markup not cleaned from abstract")

    def test_acs_publisher_response(self):
        """Test ACS response with missing abstract field."""
        acs_data = CrossRefResponse(
            DOI="10.1021/acs.joc.5c00313",
            title=[
                "The Synthesis of a Naloxone-Related Oxidative Drug Product Degradant"
            ],
            container_title=["The Journal of Organic Chemistry"],
            publisher="American Chemical Society (ACS)",
            volume="90",
            issue="16",
            page="5632-5641",
            published_online={"date-parts": [[2025, 4, 14]]},
            published_print={"date-parts": [[2025, 4, 25]]},
            # Note: No "abstract" field for ACS!
            abstract=None,  # Explicitly None
            author=[
                {"given": "Marie-Angélique F. S.", "family": "Deschamps"},
                {
                    "given": "John S.",
                    "family": "Carey",
                    "ORCID": "https://orcid.org/0000-0002-3654-0063",
                },
                {
                    "given": "Joseph P. A.",
                    "family": "Harrity",
                    "ORCID": "https://orcid.org/0000-0001-5038-5699",
                },
            ],
        )

        mock_client = Mock()
        mock_client.get_article_by_doi.return_value = acs_data

        service = CrossRefService(client=mock_client)
        result = service.fetch_and_convert_article("10.1021/acs.joc.5c00313")

        assert result is not None
        article_data, authors_data = result

        assert article_data.doi == "10.1021/acs.joc.5c00313"
        assert article_data.year == 2025
        assert article_data.volume == "90"
        assert article_data.issue == "16"

        # Critical test: Missing abstract should be handled gracefully
        print(f"ACS Abstract: {article_data.abstract}")
        # This should be None or empty, not cause an error

    @pytest.mark.integration
    def test_current_service_issues_summary(self):
        """Quick test to identify all current issues at once."""
        print("\n" + "=" * 50)
        print("PUBLISHER VARIATION TEST SUMMARY")
        print("=" * 50)

        issues_found = []

        # Test each publisher case
        test_cases = [
            ("RSC", "10.1039/d5ob00519a"),
            ("Beilstein", "10.3762/bjoc.21.83"),
            ("ACS", "10.1021/acs.joc.5c00313"),
        ]

        for publisher, doi in test_cases:
            try:
                if publisher == "RSC":
                    self.test_rsc_publisher_response()
                elif publisher == "Beilstein":
                    self.test_beilstein_publisher_response()
                elif publisher == "ACS":
                    self.test_acs_publisher_response()

                print(f"✅ {publisher}: Basic parsing works")

            except Exception as e:
                issues_found.append(f"❌ {publisher}: {str(e)}")
                print(f"❌ {publisher}: {str(e)}")

        if issues_found:
            print("\n🔧 ISSUES TO FIX:")
            for issue in issues_found:
                print(f"  {issue}")
        else:
            print("\n🎉 All publishers parse correctly!")

        print("\n💡 NEXT STEPS:")
        print("  1. Add JATS markup cleaning function")
        print("  2. Handle missing 'abstract' field gracefully")
        print("  3. Handle missing 'issue' field gracefully")
        print("  4. Test with real API calls")


# Simple standalone test function
def test_publisher_variations_standalone():
    """
    Simple function to test publisher variations without pytest.

    Run this directly to see what breaks:
    python -c "from tests.integration.test_publisher_variations import test_publisher_variations_standalone; test_publisher_variations_standalone()"
    """
    print("🧪 Testing Publisher Variations...")

    test_instance = TestPublisherVariations()

    publishers = ["RSC", "Beilstein", "ACS"]
    methods = [
        test_instance.test_rsc_publisher_response,
        test_instance.test_beilstein_publisher_response,
        test_instance.test_acs_publisher_response,
    ]

    for publisher, test_method in zip(publishers, methods, strict=False):
        try:
            test_method()
            print(f"✅ {publisher}: OK")
        except Exception as e:
            print(f"❌ {publisher}: {e}")

    print("\nDone! Check output above to see what needs fixing.")


if __name__ == "__main__":
    test_publisher_variations_standalone()
