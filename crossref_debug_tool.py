#!/usr/bin/env python3
"""
Debug tool for CrossRef article registration issues.

Use this to debug why year/journal aren't showing up in your register page.
"""

import sys
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

try:
    from chemlit_extractor.services.crossref import CrossRefService
except ImportError as e:
    print(f"❌ Cannot import CrossRef service: {e}")
    sys.exit(1)


def debug_crossref_article(doi: str):
    """Debug CrossRef article fetching for registration page."""
    print(f"🔍 Debugging CrossRef fetch for DOI: {doi}")
    print("=" * 60)

    # Test your existing service
    service = CrossRefService()

    try:
        # This is what your register page calls
        result = service.fetch_and_convert_article(doi)

        if result is None:
            print("❌ Service returned None - article not found")
            return

        article_data, authors_data = result

        print("📄 ARTICLE DATA:")
        print(f"  DOI: {article_data.doi}")
        print(f"  Title: {article_data.title}")
        print(f"  Journal: {article_data.journal} ← CHECK THIS")
        print(f"  Year: {article_data.year} ← CHECK THIS")
        print(f"  Volume: {article_data.volume}")
        print(f"  Issue: {article_data.issue}")
        print(f"  Pages: {article_data.pages}")
        print(
            f"  Abstract: {article_data.abstract[:100] if article_data.abstract else None}..."
        )

        print("\n👥 AUTHORS DATA:")
        for i, author in enumerate(authors_data):
            print(f"  {i+1}. {author.first_name} {author.last_name}")
            if author.orcid:
                print(f"     ORCID: {author.orcid}")

        # Identify issues
        issues = []
        if not article_data.year:
            issues.append("❌ Missing year")
        if not article_data.journal:
            issues.append("❌ Missing journal name")

        if issues:
            print("\n🔧 ISSUES FOUND:")
            for issue in issues:
                print(f"  {issue}")
        else:
            print("\n✅ All data looks good!")

        # Now test with raw CrossRef data to see what's available
        print("\n🔍 RAW CROSSREF DATA ANALYSIS:")
        print("-" * 40)

        # Get raw data (you might need to modify this based on your service structure)
        try:
            raw_data = service.client.get_article_by_doi(doi)
            if raw_data:
                debug_raw_crossref_data(raw_data, doi)
            else:
                print("No raw data available")
        except Exception as e:
            print(f"Could not get raw data: {e}")

    except Exception as e:
        print(f"❌ Error: {e}")

    finally:
        service.close()


def debug_raw_crossref_data(raw_data, doi: str):
    """Debug the raw CrossRef data to see what's available."""

    # Check year extraction
    print("📅 DATE FIELDS:")
    date_fields = ["published_online", "published_print", "issued", "created"]

    for field in date_fields:
        if hasattr(raw_data, field):
            date_value = getattr(raw_data, field)
            if date_value:
                print(f"  {field}: {date_value}")
                if isinstance(date_value, dict) and "date-parts" in date_value:
                    date_parts = date_value["date-parts"]
                    if date_parts and len(date_parts) > 0:
                        print(f"    → First date: {date_parts[0]}")
                        if len(date_parts[0]) > 0:
                            print(f"    → Year: {date_parts[0][0]}")

    # Check journal fields
    print("\n📰 JOURNAL FIELDS:")
    journal_fields = ["container_title", "short_container_title", "publisher"]

    for field in journal_fields:
        if hasattr(raw_data, field):
            value = getattr(raw_data, field)
            print(f"  {field}: {value}")

    # Test journal mapping
    print("\n🗺️  JOURNAL MAPPING TEST:")
    from journal_mapping_system import JournalMapper

    mapper = JournalMapper()
    journal_info = mapper.get_journal_info(doi)

    if journal_info:
        print("  ✅ Mapping found:")
        print(f"    Short: {journal_info.short_name}")
        print(f"    Full: {journal_info.full_name}")
        print(f"    Publisher: {journal_info.publisher}")
    else:
        print("  ❌ No journal mapping found for DOI pattern")
        print(f"      You might want to add: {doi[:12]}...")


def test_multiple_dois():
    """Test multiple DOIs to see patterns."""
    test_dois = [
        "10.1039/d5ob00519a",  # RSC
        "10.1021/acs.joc.5c00313",  # ACS
        "10.3762/bjoc.21.83",  # Beilstein
    ]

    for doi in test_dois:
        print(f"\n{'='*60}")
        debug_crossref_article(doi)
        print(f"{'='*60}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Debug specific DOI
        debug_crossref_article(sys.argv[1])
    else:
        # Test with known DOIs
        print("🧪 Testing multiple DOIs...")
        test_multiple_dois()

        print("\n💡 USAGE:")
        print(f"  python {sys.argv[0]} <DOI>   # Debug specific DOI")
        print(f"  python {sys.argv[0]}         # Test known DOIs")
