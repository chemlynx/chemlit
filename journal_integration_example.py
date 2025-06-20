"""
Integration example for journal mapping in CrossRef service.

Shows exactly how to integrate the journal mapper with your existing code.
"""


# Example of how to integrate with your existing CrossRef service
def integrate_journal_mapping_example():
    """
    Example of how to modify your existing CrossRef service.
    """
    print("🔧 INTEGRATION STEPS:")
    print("=" * 50)

    print("1. Save files:")
    print("   - journal_mappings.csv → project root")
    print("   - simple_journal_mapper.py → src/chemlit_extractor/services/")

    print("\n2. In your CrossRef service, add this import:")
    print("   from .simple_journal_mapper import enhance_article_with_journal_mapping")

    print("\n3. In your fetch_and_convert_article method, before returning:")
    print(
        """
   # Your existing code that creates article_data...
   
   # Add this line before returning:
   article_data = enhance_article_with_journal_mapping(article_data, doi)
   
   return article_data, authors_data
   """
    )

    print("4. Test with the register page!")


def test_with_real_dois():
    """Test the journal mapping with your real problematic DOIs."""
    from chemlit_extractor.services.simple_journal_mapper import JournalMapper

    print("🧪 Testing with Real DOIs")
    print("=" * 40)

    # Your actual problematic DOIs
    test_dois = [
        "10.1039/d5ob00519a",  # RSC - should find Org. Biomol. Chem.
        "10.1021/acs.joc.5c00313",  # ACS - should find J. Org. Chem.
        "10.3762/bjoc.21.83",  # Beilstein - should find Beilstein J. Org. Chem.
    ]

    mapper = JournalMapper("journal_mappings.csv")

    for doi in test_dois:
        journal_info = mapper.get_journal_info(doi)

        if journal_info:
            print(f"✅ {doi}")
            print(f"   → {journal_info.short_name}")
            print(f"   → {journal_info.full_name}")
        else:
            print(f"❌ {doi} → No mapping found")
        print()


def validate_rsc_pattern_matching():
    """Validate that RSC pattern matching works correctly."""
    from chemlit_extractor.services.simple_journal_mapper import JournalMapper

    print("🔍 Validating RSC Pattern Matching")
    print("=" * 40)

    # Test RSC DOI structure understanding
    test_rsc_dois = [
        ("10.1039/d5ob00519a", "ob", "Org. Biomol. Chem."),
        ("10.1039/c9cc12345", "cc", "Chem. Commun."),
        ("10.1039/d1dt01234", "dt", "Dalton Trans."),
        ("10.1039/b2cs98765", "cs", "Chem. Soc. Rev."),
    ]

    mapper = JournalMapper("journal_mappings.csv")

    print("DOI Structure Analysis:")
    for doi, expected_code, expected_journal in test_rsc_dois:
        final_section = doi[8:]  # After "10.1039/"
        actual_code = final_section[2:4]  # Characters 3-4 (0-indexed: 2-3)

        print(f"  {doi}")
        print(f"    Final section: {final_section}")
        print(f"    Characters 3-4: {actual_code} (expected: {expected_code})")

        journal_info = mapper.get_journal_info(doi)
        if journal_info:
            print(f"    Mapped to: {journal_info.short_name}")
            success = journal_info.short_name == expected_journal
            print(f"    Result: {'✅' if success else '❌'}")
        else:
            print("    Result: ❌ No mapping found")
        print()


if __name__ == "__main__":
    integrate_journal_mapping_example()
    print("\n" + "=" * 50)
    test_with_real_dois()
    print("\n" + "=" * 50)
    validate_rsc_pattern_matching()
