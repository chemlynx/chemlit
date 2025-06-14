#!/usr/bin/env python3
"""
Simple test runner for CrossRef publisher variations.

Run this to see exactly what breaks with your current CrossRef service.
Usage: python test_publisher_variations_simple.py
"""

import sys
from pathlib import Path
from unittest.mock import Mock

# Add src to path
project_root = Path(__file__).parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

try:
    from chemlit_extractor.models.schemas import CrossRefResponse
    from chemlit_extractor.services.crossref import CrossRefService
except ImportError as e:
    print(f"❌ Cannot import modules: {e}")
    print("Make sure you're running this from the project root directory")
    sys.exit(1)


def test_rsc_response():
    """Test RSC response with JATS markup."""
    print("📊 Testing RSC Publisher...")

    # Real RSC response data
    rsc_data = CrossRefResponse(
        DOI="10.1039/d5ob00519a",
        title=[
            "Triflic acid catalyzed intermolecular hydroamination of alkenes with Fmoc-NH<sub>2</sub> as the amine source"
        ],
        container_title=["Organic & Biomolecular Chemistry"],
        volume="23",
        issue="22",
        published_online={"date-parts": [[2025]]},  # Year only format
        abstract="<jats:p>We used Fmoc-NH<jats:sub>2</jats:sub> as the amine source for the Brønsted acid-catalysed hydroamination of alkenes.</jats:p>",
        author=[
            {"given": "Aswathi C.", "family": "S."},
            {
                "given": "Chinraj",
                "family": "Sivarajan",
                "ORCID": "https://orcid.org/0000-0002-0496-0645",
            },
        ],
    )

    # Test with your existing service
    mock_client = Mock()
    mock_client.get_article_by_doi.return_value = rsc_data

    service = CrossRefService(client=mock_client)
    result = service.fetch_and_convert_article("10.1039/d5ob00519a")

    if result is None:
        print("❌ Service returned None")
        return False

    article_data, authors_data = result

    # Check basic parsing
    assert article_data.doi == "10.1039/d5ob00519a"
    assert article_data.year == 2025
    print(f"  ✅ Basic parsing: DOI={article_data.doi}, Year={article_data.year}")

    # Check JATS markup handling
    if article_data.abstract:
        has_jats_tags = any(
            tag in article_data.abstract
            for tag in ["<jats:p>", "<jats:sub>", "</jats:p>"]
        )
        if has_jats_tags:
            print("  ⚠️  JATS markup still present in abstract")
            print(f"      Abstract: {article_data.abstract[:100]}...")
            return False
        else:
            print("  ✅ JATS markup cleaned successfully")

    print("  ✅ RSC parsing successful")
    return True


def test_beilstein_response():
    """Test Beilstein response with missing issue field."""
    print("📊 Testing Beilstein Publisher...")

    beilstein_data = CrossRefResponse(
        DOI="10.3762/bjoc.21.83",
        title=["Pd-Catalyzed asymmetric allylic amination with isatin"],
        container_title=["Beilstein Journal of Organic Chemistry"],
        volume="21",
        # No issue field!
        published_online={"date-parts": [[2025, 5, 23]]},  # Full date
        abstract="<jats:p>We implemented the P,olefin-type chiral ligand (a<jats:italic>R</jats:italic>)-(-)-<jats:bold>6</jats:bold>.</jats:p>",
        author=[{"given": "Natsume", "family": "Akimoto"}],
    )

    mock_client = Mock()
    mock_client.get_article_by_doi.return_value = beilstein_data

    service = CrossRefService(client=mock_client)
    result = service.fetch_and_convert_article("10.3762/bjoc.21.83")

    if result is None:
        print("❌ Service returned None")
        return False

    article_data, authors_data = result

    print(f"  ✅ Basic parsing: Year={article_data.year}, Volume={article_data.volume}")
    print(f"  📋 Issue field: {article_data.issue} (should be None)")

    # Check JATS markup
    if article_data.abstract:
        has_jats_tags = any(
            tag in article_data.abstract for tag in ["<jats:italic>", "<jats:bold>"]
        )
        if has_jats_tags:
            print("  ⚠️  JATS markup still present in abstract")
            return False

    print("  ✅ Beilstein parsing successful")
    return True


def test_acs_response():
    """Test ACS response with missing abstract."""
    print("📊 Testing ACS Publisher...")

    acs_data = CrossRefResponse(
        DOI="10.1021/acs.joc.5c00313",
        title=["The Synthesis of a Naloxone-Related Oxidative Drug Product Degradant"],
        container_title=["The Journal of Organic Chemistry"],
        volume="90",
        issue="16",
        published_online={"date-parts": [[2025, 4, 14]]},
        abstract=None,  # ACS doesn't provide abstracts!
        author=[{"given": "John S.", "family": "Carey"}],
    )

    mock_client = Mock()
    mock_client.get_article_by_doi.return_value = acs_data

    service = CrossRefService(client=mock_client)
    result = service.fetch_and_convert_article("10.1021/acs.joc.5c00313")

    if result is None:
        print("❌ Service returned None")
        return False

    article_data, authors_data = result

    print(f"  ✅ Basic parsing: Year={article_data.year}, Volume={article_data.volume}")
    print(f"  📋 Abstract field: {article_data.abstract} (should be None)")

    print("  ✅ ACS parsing successful")
    return True


def main():
    """Run all publisher variation tests."""
    print("🧪 CrossRef Publisher Variation Test")
    print("=" * 50)

    results = {}

    # Test each publisher
    test_cases = [
        ("RSC", test_rsc_response),
        ("Beilstein", test_beilstein_response),
        ("ACS", test_acs_response),
    ]

    for publisher, test_func in test_cases:
        try:
            success = test_func()
            results[publisher] = "PASS" if success else "ISSUES"
        except Exception as e:
            print(f"❌ {publisher} FAILED: {e}")
            results[publisher] = "FAILED"

    # Summary
    print("\n📋 SUMMARY")
    print("=" * 50)

    total_issues = 0
    for publisher, status in results.items():
        if status == "PASS":
            print(f"✅ {publisher}: All checks passed")
        elif status == "ISSUES":
            print(f"⚠️  {publisher}: Has issues that need fixing")
            total_issues += 1
        else:
            print(f"❌ {publisher}: Failed to parse")
            total_issues += 1

    if total_issues == 0:
        print("\n🎉 All publisher variations handled correctly!")
    else:
        print(f"\n🔧 {total_issues} publisher(s) have issues")
        print("\nLikely fixes needed:")
        print("  1. Add JATS XML markup cleaning to your CrossRef service")
        print("  2. Handle missing 'abstract' field gracefully")
        print("  3. Handle missing 'issue' field gracefully")

        print("\nNext steps:")
        print("  1. Run this test to see current issues")
        print("  2. Fix the issues in your CrossRef service")
        print("  3. Run the test again to verify fixes")
        print("  4. Add pytest integration tests")


if __name__ == "__main__":
    main()
