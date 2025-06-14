#!/usr/bin/env python3
"""
Debug tool specifically for year extraction issues.

This will help us see what's wrong with year extraction in your CrossRef service.
"""

import sys
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

try:
    from chemlit_extractor.models.schemas import CrossRefResponse
    from chemlit_extractor.services.crossref import CrossRefService
except ImportError as e:
    print(f"❌ Cannot import: {e}")
    sys.exit(1)


def debug_year_extraction(doi: str):
    """Debug year extraction step by step."""
    print(f"🔍 Debugging YEAR EXTRACTION for: {doi}")
    print("=" * 60)

    service = CrossRefService()

    try:
        # Step 1: Get raw CrossRef data
        print("Step 1: Getting raw CrossRef data...")
        raw_crossref_data = service.client.get_article_by_doi(doi)

        if raw_crossref_data is None:
            print("❌ No raw data returned")
            return

        print(f"✅ Got raw CrossRef data (type: {type(raw_crossref_data)})")

        # Step 2: Examine ALL date-related fields in raw data
        print("\nStep 2: Examining date fields in raw data...")

        date_field_names = [
            "published_online",
            "published_print",
            "issued",
            "created",
            "published-online",
            "published-print",  # Check both formats
            "deposited",
            "indexed",
        ]

        found_dates = {}

        for field_name in date_field_names:
            # Check if field exists (handle both attribute and dict access)
            field_value = None

            if hasattr(raw_crossref_data, field_name):
                field_value = getattr(raw_crossref_data, field_name)
            elif (
                hasattr(raw_crossref_data, "__dict__")
                and field_name in raw_crossref_data.__dict__
            ):
                field_value = raw_crossref_data.__dict__[field_name]

            if field_value is not None:
                found_dates[field_name] = field_value
                print(f"  ✅ {field_name}: {field_value}")

                # Try to extract year from this field
                year = extract_year_from_field(field_value)
                if year:
                    print(f"      → Year extracted: {year}")

        if not found_dates:
            print("  ❌ No date fields found in raw data!")
            print("  📋 Available fields:")
            if hasattr(raw_crossref_data, "__dict__"):
                available_fields = list(raw_crossref_data.__dict__.keys())
                for field in available_fields:
                    if (
                        "date" in field.lower()
                        or "publish" in field.lower()
                        or "issue" in field.lower()
                    ):
                        value = getattr(raw_crossref_data, field, "N/A")
                        print(f"      {field}: {value}")

        # Step 3: Test your service's conversion
        print("\nStep 3: Testing service conversion...")
        result = service.fetch_and_convert_article(doi)

        if result:
            article_data, authors_data = result
            print(f"  Service extracted year: {article_data.year}")

            if not article_data.year:
                print("  ❌ Service failed to extract year")
                print(
                    "  💡 This suggests an issue in your service's year extraction logic"
                )

        # Step 4: Manual year extraction test
        print("\nStep 4: Manual year extraction test...")
        manual_year = manual_extract_year(raw_crossref_data)
        print(f"  Manual extraction result: {manual_year}")

    except Exception as e:
        print(f"❌ Error during debugging: {e}")
        import traceback

        traceback.print_exc()

    finally:
        service.close()


def extract_year_from_field(field_value):
    """Extract year from a date field value."""
    if field_value is None:
        return None

    # Handle different formats
    if isinstance(field_value, dict):
        if "date-parts" in field_value:
            date_parts = field_value["date-parts"]
            if date_parts and len(date_parts) > 0 and len(date_parts[0]) > 0:
                try:
                    return int(date_parts[0][0])
                except (ValueError, TypeError):
                    pass

        # Check for other date formats
        if "timestamp" in field_value:
            import datetime

            try:
                timestamp = field_value["timestamp"] / 1000  # Convert from ms
                dt = datetime.datetime.fromtimestamp(timestamp)
                return dt.year
            except:
                pass

    elif isinstance(field_value, str):
        # Try to extract year from string
        import re

        year_match = re.search(r"(19|20)\d{2}", field_value)
        if year_match:
            return int(year_match.group())

    elif isinstance(field_value, (int, float)):
        # Might be a timestamp
        if field_value > 1000000000:  # Looks like a timestamp
            import datetime

            try:
                if field_value > 10000000000:  # Milliseconds
                    field_value = field_value / 1000
                dt = datetime.datetime.fromtimestamp(field_value)
                return dt.year
            except:
                pass

    return None


def manual_extract_year(crossref_data):
    """Manually extract year using various methods."""

    # Method 1: Check all attributes for date-like data
    if hasattr(crossref_data, "__dict__"):
        for attr_name, attr_value in crossref_data.__dict__.items():
            if any(
                keyword in attr_name.lower() for keyword in ["date", "publish", "issue"]
            ):
                year = extract_year_from_field(attr_value)
                if year:
                    print(f"    Found year {year} in {attr_name}")
                    return year

    # Method 2: Try common CrossRef field patterns
    common_patterns = [
        "published_online",
        "published_print",
        "issued",
        "created",
        "published-online",
        "published-print",
    ]

    for pattern in common_patterns:
        if hasattr(crossref_data, pattern):
            value = getattr(crossref_data, pattern)
            year = extract_year_from_field(value)
            if year:
                print(f"    Found year {year} in {pattern}")
                return year

    print("    No year found with manual extraction")
    return None


def test_known_working_case():
    """Test with the DOI we know should work."""
    print("🧪 Testing with known working DOI...")

    # Create test CrossRef data like in our earlier test
    test_data = CrossRefResponse(
        DOI="10.1039/d5ob00519a",
        title=["Test"],
        published_online={"date-parts": [[2025]]},  # This should give year 2025
        issued={"date-parts": [[2025]]},
    )

    print(f"Test data published_online: {test_data.published_online}")
    print(f"Test data issued: {test_data.issued}")

    # Try manual extraction
    year1 = extract_year_from_field(test_data.published_online)
    year2 = extract_year_from_field(test_data.issued)

    print(f"Manual extraction from published_online: {year1}")
    print(f"Manual extraction from issued: {year2}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        debug_year_extraction(sys.argv[1])
    else:
        # Test with the problematic DOI
        print("Testing known problematic DOI:")
        debug_year_extraction("10.1039/d5ob00519a")

        print("\n" + "=" * 60)
        test_known_working_case()

        print("\n💡 USAGE:")
        print(f"  python {sys.argv[0]} <DOI>   # Debug specific DOI")
