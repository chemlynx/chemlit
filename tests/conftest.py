"""Pytest configuration and fixtures."""

import os
import sys
from pathlib import Path

import pytest

# Get project root directory (parent of tests directory)
project_root = Path(__file__).parent.parent
os.chdir(project_root)

# Add src to Python path so we can import our modules
src_path = project_root / "src"
sys.path.insert(0, str(src_path))


@pytest.fixture(scope="session")
def project_root_path() -> Path:
    """
    Get project root path.

    Returns:
        Path to project root directory.
    """
    return project_root


@pytest.fixture(scope="session")
def test_env_setup() -> None:
    """
    Set up test environment.

    Ensures .env file exists and test environment is properly configured.
    """
    env_file = project_root / ".env"
    if not env_file.exists():
        pytest.skip("No .env file found - skipping tests that require configuration")


# Sample data fixtures for testing
@pytest.fixture
def sample_author_data() -> dict[str, str]:
    """Sample author data for testing."""
    return {
        "first_name": "Jane",
        "last_name": "Doe",
        "orcid": "0000-0000-0000-0000",
        "email": "jane.doe@university.edu",
    }


@pytest.fixture
def sample_article_data() -> dict[str, str | int]:
    """Sample article data for testing."""
    return {
        "doi": "10.1000/example.doi",
        "title": "Example Article About Chemistry",
        "journal": "Journal of Chemistry",
        "year": 2023,
        "abstract": "This is an example abstract about chemical compounds.",
    }


@pytest.fixture
def sample_compound_data() -> dict[str, str | float]:
    """Sample compound data for testing."""
    return {
        "article_doi": "10.1000/example.doi",
        "name": "Caffeine",
        "extraction_method": "decimer",
        "confidence_score": 0.95,
    }


@pytest.fixture
def sample_property_data() -> dict[str, str | int]:
    """Sample compound property data for testing."""
    return {
        "compound_id": 1,
        "property_name": "Melting Point",
        "value": "238",
        "units": "°C",
        "measurement_type": "experimental",
    }
