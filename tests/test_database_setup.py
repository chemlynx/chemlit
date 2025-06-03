"""Test Pydantic schemas."""

import pytest
from pydantic import ValidationError

from chemlit_extractor.models.schemas import (
    Article,
    ArticleCreate,
    Author,
    AuthorCreate,
    Compound,
    CompoundCreate,
    CompoundProperty,
    CompoundPropertyCreate,
    ExtractionMethod,
)


class TestAuthorSchemas:
    """Test Author-related schemas."""

    def test_author_create_valid(self) -> None:
        """Test valid AuthorCreate."""
        author_data = {
            "first_name": "Jane",
            "last_name": "Doe",
            "orcid": "0000-0000-0000-0000",
            "email": "jane.doe@university.edu",
        }

        author = AuthorCreate(**author_data)
        assert author.first_name == "Jane"
        assert author.last_name == "Doe"
        assert author.orcid == "0000-0000-0000-0000"
        assert author.email == "jane.doe@university.edu"

    def test_author_create_required_fields(self) -> None:
        """Test AuthorCreate with only required fields."""
        author = AuthorCreate(first_name="John", last_name="Smith")
        assert author.first_name == "John"
        assert author.last_name == "Smith"
        assert author.orcid is None
        assert author.email is None

    def test_author_create_validation_errors(self) -> None:
        """Test AuthorCreate validation errors."""
        # Empty first name
        with pytest.raises(ValidationError):
            AuthorCreate(first_name="", last_name="Doe")

        # Empty last name
        with pytest.raises(ValidationError):
            AuthorCreate(first_name="Jane", last_name="")

        # Missing required fields
        with pytest.raises(ValidationError):
            AuthorCreate(first_name="Jane")  # Missing last_name


class TestArticleSchemas:
    """Test Article-related schemas."""

    def test_article_create_valid(self) -> None:
        """Test valid ArticleCreate."""
        article_data = {
            "doi": "10.1000/example.doi",
            "title": "Example Article About Chemistry",
            "journal": "Journal of Chemistry",
            "year": 2023,
            "abstract": "This is an example abstract about chemical compounds.",
        }

        article = ArticleCreate(**article_data)
        assert article.doi == "10.1000/example.doi"
        assert article.title == "Example Article About Chemistry"
        assert article.year == 2023

    def test_article_create_required_fields_only(self) -> None:
        """Test ArticleCreate with only required fields."""
        article = ArticleCreate(doi="10.1000/minimal", title="Minimal Article")
        assert article.doi == "10.1000/minimal"
        assert article.title == "Minimal Article"
        assert article.journal is None
        assert article.year is None

    def test_article_doi_validation(self) -> None:
        """Test DOI validation."""
        # Valid DOI
        article = ArticleCreate(doi="10.1000/valid", title="Test")
        assert article.doi == "10.1000/valid"

        # Invalid DOI format
        with pytest.raises(ValidationError, match="DOI must start with '10.'"):
            ArticleCreate(doi="invalid-doi", title="Test")

        # DOI normalization (uppercase to lowercase)
        article = ArticleCreate(doi="10.1000/UPPERCASE", title="Test")
        assert article.doi == "10.1000/uppercase"

    def test_article_year_validation(self) -> None:
        """Test year validation."""
        # Valid year
        article = ArticleCreate(doi="10.1000/test", title="Test", year=2023)
        assert article.year == 2023

        # Year too early
        with pytest.raises(ValidationError):
            ArticleCreate(doi="10.1000/test", title="Test", year=1799)

        # Year too late
        with pytest.raises(ValidationError):
            ArticleCreate(doi="10.1000/test", title="Test", year=2031)


class TestCompoundSchemas:
    """Test Compound-related schemas."""

    def test_compound_create_valid(self) -> None:
        """Test valid CompoundCreate."""
        compound_data = {
            "article_doi": "10.1000/example.doi",
            "name": "Caffeine",
            "extraction_method": ExtractionMethod.DECIMER,
            "confidence_score": 0.95,
        }

        compound = CompoundCreate(**compound_data)
        assert compound.name == "Caffeine"
        assert compound.extraction_method == ExtractionMethod.DECIMER
        assert compound.confidence_score == 0.95

    def test_compound_create_required_fields_only(self) -> None:
        """Test CompoundCreate with only required fields."""
        compound = CompoundCreate(article_doi="10.1000/test", name="Test Compound")
        assert compound.article_doi == "10.1000/test"
        assert compound.name == "Test Compound"
        assert compound.extraction_method is None
        assert compound.confidence_score is None

    def test_compound_extraction_method_enum(self) -> None:
        """Test extraction method enum validation."""
        # Valid enum value
        compound = CompoundCreate(
            article_doi="10.1000/test",
            name="Test",
            extraction_method=ExtractionMethod.NAME_TO_STRUCTURE,
        )
        assert compound.extraction_method == ExtractionMethod.NAME_TO_STRUCTURE

        # Invalid enum value
        with pytest.raises(ValidationError):
            CompoundCreate(
                article_doi="10.1000/test",
                name="Test",
                extraction_method="invalid_method",
            )

    def test_compound_confidence_score_validation(self) -> None:
        """Test confidence score validation."""
        # Valid score
        compound = CompoundCreate(
            article_doi="10.1000/test", name="Test", confidence_score=0.5
        )
        assert compound.confidence_score == 0.5

        # Score too low
        with pytest.raises(ValidationError):
            CompoundCreate(
                article_doi="10.1000/test", name="Test", confidence_score=-0.1
            )

        # Score too high
        with pytest.raises(ValidationError):
            CompoundCreate(
                article_doi="10.1000/test", name="Test", confidence_score=1.1
            )


class TestCompoundPropertySchemas:
    """Test CompoundProperty-related schemas."""

    def test_compound_property_create_valid(self) -> None:
        """Test valid CompoundPropertyCreate."""
        property_data = {
            "compound_id": 1,
            "property_name": "Melting Point",
            "value": "238",
            "units": "°C",
            "measurement_type": "experimental",
        }

        prop = CompoundPropertyCreate(**property_data)
        assert prop.compound_id == 1
        assert prop.property_name == "Melting Point"
        assert prop.value == "238"
        assert prop.units == "°C"

    def test_compound_property_create_required_fields_only(self) -> None:
        """Test CompoundPropertyCreate with only required fields."""
        prop = CompoundPropertyCreate(
            compound_id=1, property_name="Test Property", value="Test Value"
        )
        assert prop.compound_id == 1
        assert prop.property_name == "Test Property"
        assert prop.value == "Test Value"
        assert prop.units is None

    def test_compound_property_validation_errors(self) -> None:
        """Test CompoundPropertyCreate validation errors."""
        # Invalid compound_id
        with pytest.raises(ValidationError):
            CompoundPropertyCreate(
                compound_id=0, property_name="Test", value="Test"  # Must be > 0
            )

        # Empty property name
        with pytest.raises(ValidationError):
            CompoundPropertyCreate(compound_id=1, property_name="", value="Test")


class TestJSONSerialization:
    """Test JSON serialization/deserialization."""

    def test_compound_json_serialization(self) -> None:
        """Test compound JSON serialization."""
        compound_data = {
            "article_doi": "10.1000/example.doi",
            "name": "Aspirin",
            "extraction_method": ExtractionMethod.NAME_TO_STRUCTURE,
            "confidence_score": 0.88,
        }

        compound = CompoundCreate(**compound_data)

        # Serialize to JSON
        json_data = compound.model_dump_json()
        assert "Aspirin" in json_data
        assert "name_to_structure" in json_data

        # Deserialize from JSON
        compound_from_json = CompoundCreate.model_validate_json(json_data)
        assert compound_from_json.name == "Aspirin"
        assert (
            compound_from_json.extraction_method == ExtractionMethod.NAME_TO_STRUCTURE
        )

    def test_article_json_serialization(self) -> None:
        """Test article JSON serialization."""
        article = ArticleCreate(doi="10.1000/test", title="Test Article", year=2023)

        # Test round-trip
        json_data = article.model_dump_json()
        article_from_json = ArticleCreate.model_validate_json(json_data)

        assert article_from_json.doi == article.doi
        assert article_from_json.title == article.title
        assert article_from_json.year == article.year


class TestExtractionMethodEnum:
    """Test ExtractionMethod enum."""

    def test_enum_values(self) -> None:
        """Test enum values are correct."""
        assert ExtractionMethod.DECIMER == "decimer"
        assert ExtractionMethod.NAME_TO_STRUCTURE == "name_to_structure"
        assert ExtractionMethod.MANUAL == "manual"

    def test_enum_membership(self) -> None:
        """Test enum membership."""
        assert "decimer" in ExtractionMethod
        assert "name_to_structure" in ExtractionMethod
        assert "manual" in ExtractionMethod
        assert "invalid" not in ExtractionMethod
