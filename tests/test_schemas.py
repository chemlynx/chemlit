#!/usr/bin/env python3
"""Test script to verify Pydantic schemas work correctly."""

import os
import sys
from pathlib import Path

# Get project root directory (parent of tests directory)
project_root = Path(__file__).parent.parent
os.chdir(project_root)

# Add src to Python path so we can import our modules
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

from chemlit_extractor.models.schemas import (
    ArticleCreate,
    AuthorCreate,
    CompoundCreate,
    CompoundPropertyCreate,
    ExtractionMethod,
)


def test_author_schema() -> None:
    """Test Author schemas."""
    print("🧪 Testing Author schemas...")

    # Test AuthorCreate
    author_data = {
        "first_name": "Jane",
        "last_name": "Doe",
        "orcid": "0000-0000-0000-0000",
        "email": "jane.doe@university.edu",
    }

    author_create = AuthorCreate(**author_data)
    print(f"✅ AuthorCreate: {author_create.first_name} {author_create.last_name}")

    # Test validation
    try:
        AuthorCreate(first_name="", last_name="Doe")  # Should fail
        print("❌ Validation should have failed for empty first_name")
    except ValueError:
        print("✅ Validation correctly rejected empty first_name")


def test_article_schema() -> None:
    """Test Article schemas."""
    print("\n🧪 Testing Article schemas...")

    # Test ArticleCreate
    article_data = {
        "doi": "10.1000/example.doi",
        "title": "Example Article About Chemistry",
        "journal": "Journal of Chemistry",
        "year": 2023,
        "abstract": "This is an example abstract about chemical compounds.",
    }

    article_create = ArticleCreate(**article_data)
    print(f"✅ ArticleCreate: {article_create.title[:50]}...")

    # Test DOI validation
    try:
        ArticleCreate(doi="invalid-doi", title="Test")  # Should fail
        print("❌ DOI validation should have failed")
    except ValueError:
        print("✅ DOI validation correctly rejected invalid format")


def test_compound_schema() -> None:
    """Test Compound schemas."""
    print("\n🧪 Testing Compound schemas...")

    # Test CompoundCreate
    compound_data = {
        "article_doi": "10.1000/example.doi",
        "name": "Caffeine",
        "extraction_method": ExtractionMethod.DECIMER,
        "confidence_score": 0.95,
    }

    compound_create = CompoundCreate(**compound_data)
    print(
        f"✅ CompoundCreate: {compound_create.name} (method: {compound_create.extraction_method})"
    )

    # Test enum validation
    try:
        CompoundCreate(
            article_doi="10.1000/test", name="Test", extraction_method="invalid_method"
        )
        print("❌ Enum validation should have failed")
    except ValueError:
        print("✅ Enum validation correctly rejected invalid extraction method")


def test_compound_property_schema() -> None:
    """Test CompoundProperty schemas."""
    print("\n🧪 Testing CompoundProperty schemas...")

    # Test CompoundPropertyCreate
    property_data = {
        "compound_id": 1,
        "property_name": "Melting Point",
        "value": "238",
        "units": "°C",
        "measurement_type": "experimental",
    }

    property_create = CompoundPropertyCreate(**property_data)
    print(
        f"✅ CompoundPropertyCreate: {property_create.property_name} = {property_create.value} {property_create.units}"
    )


def test_json_serialization() -> None:
    """Test JSON serialization/deserialization."""
    print("\n🧪 Testing JSON serialization...")

    # Create a compound
    compound_data = {
        "article_doi": "10.1000/example.doi",
        "name": "Aspirin",
        "extraction_method": ExtractionMethod.NAME_TO_STRUCTURE,
        "confidence_score": 0.88,
    }

    compound = CompoundCreate(**compound_data)

    # Serialize to JSON
    json_data = compound.model_dump_json()
    print(f"✅ JSON serialization: {json_data}")

    # Deserialize from JSON
    compound_from_json = CompoundCreate.model_validate_json(json_data)
    print(f"✅ JSON deserialization: {compound_from_json.name}")


def main() -> None:
    """Run all schema tests."""
    print("🧪 Testing Pydantic Schemas...")

    try:
        test_author_schema()
        test_article_schema()
        test_compound_schema()
        test_compound_property_schema()
        test_json_serialization()

        print("\n🎉 All schema tests passed!")

    except Exception as e:
        print(f"\n❌ Schema test failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
