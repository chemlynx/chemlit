"""
Simple journal mapper that reads from CSV file.

Clean implementation focusing only on exact journal mapping with no fallbacks.
"""

import csv
import logging
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)


class JournalInfo(NamedTuple):
    """Journal information."""

    short_name: str
    full_name: str
    publisher: str


class JournalMapper:
    """Simple journal mapper using CSV data file."""

    def __init__(self, csv_file: str = "journal_mappings.csv"):
        """
        Initialize journal mapper.

        Args:
            csv_file: Path to CSV file with journal mappings
        """
        self.csv_file = csv_file
        self.mappings: list[tuple] = []
        self._load_mappings()

    def _load_mappings(self) -> None:
        """Load journal mappings from CSV file."""
        csv_path = Path(self.csv_file)

        if not csv_path.exists():
            logger.warning(f"Journal mappings file not found: {csv_path}")
            return

        try:
            with open(csv_path, encoding="utf-8") as f:
                reader = csv.reader(f)

                for line_num, row in enumerate(reader, 1):
                    # Skip empty lines and comments
                    if not row or row[0].startswith("#"):
                        continue

                    if len(row) >= 4:
                        pattern, short_name, full_name, publisher = row[:4]
                        self.mappings.append(
                            (
                                pattern.strip(),
                                JournalInfo(
                                    short_name=short_name.strip(),
                                    full_name=full_name.strip(),
                                    publisher=publisher.strip(),
                                ),
                            )
                        )
                    else:
                        logger.warning(f"Invalid row at line {line_num}: {row}")

            logger.info(f"Loaded {len(self.mappings)} journal mappings")

        except Exception as e:
            logger.error(f"Error loading journal mappings: {e}")

    def get_journal_info(self, doi: str) -> JournalInfo | None:
        """
        Get journal information from DOI.

        Args:
            doi: DOI string (e.g., "10.1039/d5ob00519a")

        Returns:
            JournalInfo if found, None otherwise
        """
        if not doi:
            return None

        doi_lower = doi.lower()

        for pattern, journal_info in self.mappings:
            if self._matches_pattern(doi_lower, pattern.lower()):
                return journal_info

        return None

    def _matches_pattern(self, doi: str, pattern: str) -> bool:
        """
        Check if DOI matches pattern.

        Handles special RSC patterns like "10.1039/..ob" where ".." represents
        any 2 characters and "ob" must match characters 3-4 of the final section.

        Args:
            doi: DOI to check
            pattern: Pattern to match against

        Returns:
            True if DOI matches pattern
        """
        # Handle RSC special patterns (10.1039/..XX)
        if pattern.startswith("10.1039/.."):
            if not doi.startswith("10.1039/"):
                return False

            # Extract the final section after "10.1039/"
            final_section = doi[8:]  # Everything after "10.1039/"

            if len(final_section) < 4:
                return False

            # Get characters 3-4 of final section (0-indexed: positions 2-3)
            journal_code = final_section[2:4]

            # Get expected journal code from pattern (everything after "..")
            expected_code = pattern[10:]  # Everything after "10.1039/.."

            return journal_code == expected_code

        # Handle exact prefix matching for other publishers
        else:
            return doi.startswith(pattern)

    def reload_mappings(self) -> None:
        """Reload mappings from CSV file."""
        self.mappings.clear()
        self._load_mappings()


def test_journal_mapper():
    """Test the journal mapper with known DOIs."""

    # Test DOIs
    test_cases = [
        # RSC journals - test the 3rd/4th character matching
        ("10.1039/d5ob00519a", "Org. Biomol. Chem."),  # ob at positions 3-4
        ("10.1039/c9cc12345", "Chem. Commun."),  # cc at positions 3-4
        ("10.1039/d1dt01234", "Dalton Trans."),  # dt at positions 3-4
        # ACS journals - test exact prefix matching
        ("10.1021/acs.joc.5c00313", "J. Org. Chem."),
        ("10.1021/ja.2023.12345", "J. Am. Chem. Soc."),
        ("10.1021/ol.2023.12345", "Org. Lett."),
        # Beilstein
        ("10.3762/bjoc.21.83", "Beilstein J. Org. Chem."),
        # Should not match
        ("10.1039/d5xx00519a", None),  # Wrong journal code
        ("10.1000/unknown", None),  # Unknown publisher
    ]

    print("🧪 Testing Journal Mapper")
    print("=" * 50)

    mapper = JournalMapper("journal_mappings.csv")

    if not mapper.mappings:
        print("❌ No mappings loaded - check if journal_mappings.csv exists")
        return

    success_count = 0

    for doi, expected_short_name in test_cases:
        journal_info = mapper.get_journal_info(doi)

        if expected_short_name is None:
            # Should not find a match
            if journal_info is None:
                print(f"✅ {doi} → No match (expected)")
                success_count += 1
            else:
                print(f"❌ {doi} → {journal_info.short_name} (should be no match)")
        else:
            # Should find a match
            if journal_info and journal_info.short_name == expected_short_name:
                print(f"✅ {doi} → {journal_info.short_name}")
                success_count += 1
            elif journal_info:
                print(
                    f"❌ {doi} → {journal_info.short_name} (expected {expected_short_name})"
                )
            else:
                print(f"❌ {doi} → No match (expected {expected_short_name})")

    print(f"\nResults: {success_count}/{len(test_cases)} tests passed")

    if success_count == len(test_cases):
        print("🎉 All tests passed!")
    else:
        print("🔧 Some tests failed - check patterns in CSV file")


def enhance_article_with_journal_mapping(
    article_data, doi: str, csv_file: str = "journal_mappings.csv"
):
    """
    Enhance article data with journal mapping.

    Use this in your CrossRef service to add journal info when missing.

    Args:
        article_data: Your ArticleCreate object
        doi: DOI string
        csv_file: Path to journal mappings CSV

    Returns:
        Enhanced article_data
    """
    mapper = JournalMapper(csv_file)

    # Only enhance if journal is missing or generic
    if not article_data.journal or article_data.journal in ["Unknown Title", ""]:
        journal_info = mapper.get_journal_info(doi)

        if journal_info:
            article_data.journal = journal_info.full_name
            logger.info(
                f"Enhanced journal: {journal_info.short_name} → {journal_info.full_name}"
            )

    return article_data


if __name__ == "__main__":
    test_journal_mapper()
