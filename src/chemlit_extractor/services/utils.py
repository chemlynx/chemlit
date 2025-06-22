"""Simplified journal mapping service."""

from pathlib import Path
from typing import NamedTuple

# Move this data into the service itself - no need for external CSV
JOURNAL_MAPPINGS = {
    # RSC journals - check characters 3-4 of final DOI section
    "10.1039/..ob": ("Org. Biomol. Chem.", "Organic & Biomolecular Chemistry", "RSC"),
    "10.1039/..cc": ("Chem. Commun.", "Chemical Communications", "RSC"),
    "10.1039/..dt": ("Dalton Trans.", "Dalton Transactions", "RSC"),
    "10.1039/..cs": ("Chem. Soc. Rev.", "Chemical Society Reviews", "RSC"),
    # ACS journals
    "10.1021/acs.joc": ("J. Org. Chem.", "The Journal of Organic Chemistry", "ACS"),
    "10.1021/ja": (
        "J. Am. Chem. Soc.",
        "Journal of the American Chemical Society",
        "ACS",
    ),
    "10.1021/jo": ("J. Org. Chem.", "The Journal of Organic Chemistry", "ACS"),
    # Beilstein
    "10.3762/bjoc": (
        "Beilstein J. Org. Chem.",
        "Beilstein Journal of Organic Chemistry",
        "Beilstein",
    ),
}


class JournalInfo(NamedTuple):
    """Journal information."""

    short_name: str
    full_name: str
    publisher: str


def get_journal_info(doi: str) -> JournalInfo | None:
    """
    Get journal info from DOI pattern.

    Args:
        doi: DOI string

    Returns:
        JournalInfo if found, None otherwise
    """
    if not doi:
        return None

    doi_lower = doi.lower()

    # Handle RSC special pattern
    if doi_lower.startswith("10.1039/"):
        final_section = doi_lower[8:]  # After "10.1039/"
        if len(final_section) >= 4:
            journal_code = final_section[2:4]  # Characters 3-4
            pattern_key = f"10.1039/..{journal_code}"
            if pattern_key in JOURNAL_MAPPINGS:
                return JournalInfo(*JOURNAL_MAPPINGS[pattern_key])

    # Check exact prefix matches
    for pattern, journal_data in JOURNAL_MAPPINGS.items():
        if not ".." in pattern and doi_lower.startswith(pattern):
            return JournalInfo(*journal_data)

    return None


def enhance_article_with_journal(article_data, doi: str):
    """
    Enhance article data with journal mapping if missing.

    This modifies the article_data in place.
    """
    if not article_data.journal or article_data.journal == "Unknown Title":
        journal_info = get_journal_info(doi)
        if journal_info:
            article_data.journal = journal_info.full_name
    return article_data


"""Shared utilities for services."""

# Copy the journal mapping logic from the artifact
"""Simplified year extraction from CrossRef data."""

from typing import Any


def extract_year_from_crossref(crossref_data: Any) -> int | None:
    """
    Extract year from CrossRef response data.

    Tries multiple date fields in order of preference.

    Args:
        crossref_data: CrossRef response object

    Returns:
        Year as integer or None if not found
    """
    # Fields to check in order of preference
    date_fields = [
        "published",
        "published_online",
        "published-online",
        "issued",
        "published_print",
        "published-print",
        "created",
    ]

    for field_name in date_fields:
        # Try both attribute access and dict access
        date_value = None

        if hasattr(crossref_data, field_name):
            date_value = getattr(crossref_data, field_name)
        elif (
            hasattr(crossref_data, "__dict__") and field_name in crossref_data.__dict__
        ):
            date_value = crossref_data.__dict__[field_name]

        year = _extract_year_from_date_value(date_value)
        if year:
            return year

    return None


def _extract_year_from_date_value(date_value: Any) -> int | None:
    """Extract year from a CrossRef date value."""
    if not date_value:
        return None

    # Handle CrossRef date-parts format
    if isinstance(date_value, dict) and "date-parts" in date_value:
        date_parts = date_value["date-parts"]
        if date_parts and len(date_parts) > 0 and len(date_parts[0]) > 0:
            try:
                return int(date_parts[0][0])
            except (ValueError, TypeError, IndexError):
                pass

    return None
