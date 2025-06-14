#!/usr/bin/env python3
"""
Simple test to see raw CrossRef JSON response.
"""


import httpx


def test_raw_crossref(doi):
    """Get raw CrossRef response and show date fields."""
    print(f"🔍 Raw CrossRef data for: {doi}")

    url = f"https://api.crossref.org/works/{doi}"
    headers = {"User-Agent": "ChemLit-Extractor/1.0 (mailto:test@example.com)"}

    with httpx.Client() as client:
        response = client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

    message = data.get("message", {})

    print("📅 ALL DATE-RELATED FIELDS:")
    for key, value in message.items():
        if any(word in key.lower() for word in ["date", "publish", "issue"]):
            print(f"  {key}: {value}")

    # Check specifically for year
    if "published" in message:
        pub_data = message["published"]
        if isinstance(pub_data, dict) and "date-parts" in pub_data:
            year = pub_data["date-parts"][0][0]
            print(f"\n🎯 YEAR FOUND in 'published' field: {year}")


if __name__ == "__main__":
    test_raw_crossref("10.1039/d5ob00519a")
