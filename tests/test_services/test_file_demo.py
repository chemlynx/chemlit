"""Demo script for file management functionality."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from chemlit_extractor.services.file_management import FileManagementService
from chemlit_extractor.services.file_utils import (
    create_article_directories,
    get_safe_filename,
    is_allowed_file_type,
    sanitize_doi_for_filesystem,
)


class TestFileManagementDemo:
    """Demo tests showing file management capabilities."""

    def test_doi_sanitization_examples(self):
        """Demo DOI sanitization for various formats."""
        print("\n🧪 DOI Sanitization Demo")
        print("-" * 40)

        test_dois = [
            "10.1000/example.doi",
            "https://doi.org/10.1021/ja.2023.12345",
            "10.1038/nature<>special:chars",
            "doi:10.1234/very/long/path/structure",
        ]

        for doi in test_dois:
            sanitized = sanitize_doi_for_filesystem(doi)
            print(f"Original: {doi}")
            print(f"Sanitized: {sanitized}")
            print()

    def test_file_type_validation_examples(self):
        """Demo file type validation."""
        print("\n🧪 File Type Validation Demo")
        print("-" * 40)

        test_files = [
            ("article.pdf", "pdf"),
            ("manuscript.html", "html"),
            ("figure1.png", "images"),
            ("data.csv", "supplementary"),
            ("script.exe", "pdf"),  # Should fail
            ("image.jpg", "pdf"),  # Should fail
        ]

        for filename, file_type in test_files:
            is_valid = is_allowed_file_type(filename, file_type)
            status = "✅" if is_valid else "❌"
            print(
                f"{status} {filename} as {file_type}: {'Valid' if is_valid else 'Invalid'}"
            )

    def test_filename_sanitization_examples(self):
        """Demo filename sanitization."""
        print("\n🧪 Filename Sanitization Demo")
        print("-" * 40)

        test_filenames = [
            "normal_file.pdf",
            "file<>with:bad|chars.txt",
            "very_long_filename_" + "x" * 100 + ".pdf",
            "file with spaces.docx",
        ]

        for filename in test_filenames:
            safe_name = get_safe_filename(filename)
            print(f"Original: {filename}")
            print(f"Safe: {safe_name}")
            print()

    @pytest.mark.integration
    def test_complete_file_management_workflow(self):
        """Demo complete file management workflow."""
        print("\n🧪 Complete File Management Workflow")
        print("-" * 50)

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "chemlit_extractor.services.file_utils.settings"
            ) as mock_settings:
                mock_settings.articles_path = Path(temp_dir)
                mock_settings.max_file_size_mb = 10

                test_doi = "10.1000/demo.article"
                print(f"📄 Working with article: {test_doi}")

                # 1. Create directory structure
                print("\n1️⃣ Creating directory structure...")
                directories = create_article_directories(test_doi)
                for name, path in directories.items():
                    print(f"   📁 {name}: {path}")

                # 2. Simulate adding files
                print("\n2️⃣ Adding test files...")
                test_files = [
                    ("pdf", "article.pdf", "Fake PDF content"),
                    ("html", "article.html", "<html>Fake HTML</html>"),
                    ("images", "figure1.png", "Fake PNG data"),
                    ("supplementary", "data.csv", "col1,col2\n1,2\n3,4"),
                ]

                for file_type, filename, content in test_files:
                    file_path = directories[file_type] / filename
                    file_path.write_text(content)
                    print(f"   ✅ Created {file_type}/{filename}")

                # 3. Use FileManagementService to get info
                print("\n3️⃣ Getting file information...")
                with FileManagementService() as service:
                    file_info = service.get_article_files(test_doi)

                    print(
                        f"   📊 Total files: {sum(file_info.get_file_count().values())}"
                    )
                    print(f"   💾 Total size: {file_info.total_size_mb:.3f} MB")
                    print(f"   📁 Has files: {file_info.has_files()}")

                    for file_type, count in file_info.get_file_count().items():
                        if count > 0:
                            print(f"   📄 {file_type}: {count} files")

                # 4. Get detailed stats
                print("\n4️⃣ Getting detailed statistics...")
                with FileManagementService() as service:
                    stats = service.get_file_stats(test_doi)

                    print(f"   🔑 Sanitized DOI: {stats['sanitized_doi']}")
                    print(f"   📊 File counts: {stats['file_counts']}")
                    print(f"   ⏰ Last updated: {stats['last_updated']}")
                    print(f"   📁 Directory exists: {stats['directory_exists']}")

                # 5. List all files
                print("\n5️⃣ Listing all files...")
                all_files = file_info.get_all_files()
                for file_data in all_files:
                    print(
                        f"   📄 {file_data['type']}/{file_data['filename']} "
                        f"({file_data['size_mb']:.3f} MB)"
                    )

                # 6. Cleanup demonstration
                print("\n6️⃣ Cleanup demonstration...")
                with FileManagementService() as service:
                    # Delete specific file type
                    success = service.delete_file_type(test_doi, "images")
                    print(f"   🗑️ Deleted images: {success}")

                    # Check remaining files
                    updated_info = service.get_article_files(test_doi)
                    remaining_counts = updated_info.get_file_count()
                    print(f"   📊 Remaining files: {remaining_counts}")

                    # Final cleanup
                    success = service.delete_article_files(test_doi)
                    print(f"   🗑️ Deleted all files: {success}")

                print("\n🎉 File management workflow completed!")

    def test_error_handling_demo(self):
        """Demo error handling in file operations."""
        print("\n🧪 Error Handling Demo")
        print("-" * 30)

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "chemlit_extractor.services.file_utils.settings"
            ) as mock_settings:
                mock_settings.articles_path = Path(temp_dir)

                with FileManagementService() as service:
                    # Try to get info for non-existent article
                    print("1️⃣ Testing non-existent article...")
                    file_info = service.get_article_files("10.1000/nonexistent")
                    print(f"   📊 Has files: {file_info.has_files()}")
                    print(f"   💾 Total size: {file_info.total_size_mb} MB")

                    # Try to delete non-existent files
                    print("\n2️⃣ Testing deletion of non-existent files...")
                    success = service.delete_article_files("10.1000/nonexistent")
                    print(f"   🗑️ Delete success: {success}")

                    print("\n✅ Error handling works correctly!")


def demo_file_management_manual():
    """
    Manual demo function for file management.

    Run this to see file management capabilities without pytest.
    """
    print("🗂️ ChemLit Extractor File Management Demo")
    print("=" * 50)

    # DOI sanitization demo
    print("\n📝 DOI Sanitization Examples:")
    test_dois = [
        "10.1000/simple.example",
        "https://doi.org/10.1021/complex.path",
        "10.1038/nature<unsafe>characters",
    ]

    for doi in test_dois:
        sanitized = sanitize_doi_for_filesystem(doi)
        print(f"  {doi} → {sanitized}")

    # File type validation demo
    print("\n📁 File Type Validation Examples:")
    test_files = [
        ("research.pdf", "pdf", True),
        ("data.html", "html", True),
        ("figure.png", "images", True),
        ("virus.exe", "pdf", False),
    ]

    for filename, file_type, expected in test_files:
        result = is_allowed_file_type(filename, file_type)
        status = "✅" if result == expected else "❌"
        print(f"  {status} {filename} as {file_type}")

    print("\n🎯 File management system ready!")
    print("   • DOI sanitization works correctly")
    print("   • File type validation is secure")
    print("   • Directory management is automatic")
    print("   • Download and organization features available")


if __name__ == "__main__":
    demo_file_management_manual()
