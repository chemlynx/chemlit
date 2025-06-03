"""Test CRUD operations."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from chemlit_extractor.database.crud import (
    ArticleCRUD,
    AuthorCRUD,
    CompoundCRUD,
    CompoundPropertyCRUD,
    get_database_stats,
)
from chemlit_extractor.database.models import Base
from chemlit_extractor.models.schemas import (
    ArticleCreate,
    ArticleSearchQuery,
    ArticleUpdate,
    AuthorCreate,
    AuthorUpdate,
    CompoundCreate,
    CompoundPropertyCreate,
    CompoundUpdate,
    ExtractionMethod,
)


@pytest.fixture(scope="function")
def db_session():
    """
    Create a test database session.

    Uses an in-memory SQLite database for testing.
    """
    # Create in-memory SQLite database for testing
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def sample_author():
    """Sample author data."""
    return AuthorCreate(
        first_name="Jane",
        last_name="Doe",
        orcid="0000-0000-0000-0000",
        email="jane.doe@university.edu",
    )


@pytest.fixture
def sample_article():
    """Sample article data."""
    return ArticleCreate(
        doi="10.1000/test.article",
        title="Test Article About Chemistry",
        journal="Test Journal",
        year=2023,
        abstract="This is a test abstract.",
    )


@pytest.fixture
def sample_compound():
    """Sample compound data."""
    return CompoundCreate(
        article_doi="10.1000/test.article",
        name="Test Compound",
        extraction_method=ExtractionMethod.DECIMER,
        confidence_score=0.95,
    )


class TestAuthorCRUD:
    """Test Author CRUD operations."""

    def test_create_author(self, db_session, sample_author):
        """Test creating an author."""
        author = AuthorCRUD.create(db_session, sample_author)

        assert author.id is not None
        assert author.first_name == "Jane"
        assert author.last_name == "Doe"
        assert author.orcid == "0000-0000-0000-0000"
        assert author.created_at is not None

    def test_get_by_id(self, db_session, sample_author):
        """Test getting author by ID."""
        created_author = AuthorCRUD.create(db_session, sample_author)
        retrieved_author = AuthorCRUD.get_by_id(db_session, created_author.id)

        assert retrieved_author is not None
        assert retrieved_author.id == created_author.id
        assert retrieved_author.first_name == "Jane"

    def test_get_by_id_not_found(self, db_session):
        """Test getting non-existent author."""
        author = AuthorCRUD.get_by_id(db_session, 999)
        assert author is None

    def test_get_or_create_existing_by_orcid(self, db_session, sample_author):
        """Test get_or_create with existing author (by ORCID)."""
        # Create first author
        author1 = AuthorCRUD.create(db_session, sample_author)

        # Try to create same author again
        author2 = AuthorCRUD.get_or_create(db_session, sample_author)

        assert author1.id == author2.id  # Should return the same author

    def test_get_or_create_existing_by_name(self, db_session):
        """Test get_or_create with existing author (by name, no ORCID)."""
        author_data = AuthorCreate(first_name="John", last_name="Smith")

        # Create first author
        author1 = AuthorCRUD.create(db_session, author_data)

        # Try to create same author again
        author2 = AuthorCRUD.get_or_create(db_session, author_data)

        assert author1.id == author2.id

    def test_get_or_create_new(self, db_session):
        """Test get_or_create with new author."""
        author_data = AuthorCreate(first_name="New", last_name="Author")
        author = AuthorCRUD.get_or_create(db_session, author_data)

        assert author.id is not None
        assert author.first_name == "New"

    def test_update_author(self, db_session, sample_author):
        """Test updating an author."""
        author = AuthorCRUD.create(db_session, sample_author)

        update_data = AuthorUpdate(email="new.email@university.edu")
        updated_author = AuthorCRUD.update(db_session, author.id, update_data)

        assert updated_author is not None
        assert updated_author.email == "new.email@university.edu"
        assert updated_author.first_name == "Jane"  # Unchanged

    def test_update_author_not_found(self, db_session):
        """Test updating non-existent author."""
        update_data = AuthorUpdate(email="test@example.com")
        result = AuthorCRUD.update(db_session, 999, update_data)
        assert result is None

    def test_delete_author(self, db_session, sample_author):
        """Test deleting an author."""
        author = AuthorCRUD.create(db_session, sample_author)

        # Delete the author
        result = AuthorCRUD.delete(db_session, author.id)
        assert result is True

        # Verify deletion
        deleted_author = AuthorCRUD.get_by_id(db_session, author.id)
        assert deleted_author is None

    def test_delete_author_not_found(self, db_session):
        """Test deleting non-existent author."""
        result = AuthorCRUD.delete(db_session, 999)
        assert result is False

    def test_get_multi(self, db_session):
        """Test getting multiple authors."""
        # Create multiple authors
        for i in range(5):
            author_data = AuthorCreate(first_name=f"Author{i}", last_name="Test")
            AuthorCRUD.create(db_session, author_data)

        authors = AuthorCRUD.get_multi(db_session, skip=0, limit=3)
        assert len(authors) == 3

        # Test pagination
        authors_page2 = AuthorCRUD.get_multi(db_session, skip=3, limit=3)
        assert len(authors_page2) == 2

    def test_count(self, db_session, sample_author):
        """Test counting authors."""
        assert AuthorCRUD.count(db_session) == 0

        AuthorCRUD.create(db_session, sample_author)
        assert AuthorCRUD.count(db_session) == 1


class TestArticleCRUD:
    """Test Article CRUD operations."""

    def test_create_article(self, db_session, sample_article):
        """Test creating an article."""
        article = ArticleCRUD.create(db_session, sample_article)

        assert article.doi == "10.1000/test.article"
        assert article.title == "Test Article About Chemistry"
        assert article.year == 2023
        assert article.created_at is not None

    def test_create_article_with_authors(
        self, db_session, sample_article, sample_author
    ):
        """Test creating an article with authors."""
        authors = [sample_author]
        article = ArticleCRUD.create(db_session, sample_article, authors)

        assert len(article.authors) == 1
        assert article.authors[0].first_name == "Jane"

    def test_create_article_duplicate_doi(self, db_session, sample_article):
        """Test creating article with duplicate DOI."""
        ArticleCRUD.create(db_session, sample_article)

        with pytest.raises(ValueError, match="already exists"):
            ArticleCRUD.create(db_session, sample_article)

    def test_get_by_doi(self, db_session, sample_article):
        """Test getting article by DOI."""
        created_article = ArticleCRUD.create(db_session, sample_article)
        retrieved_article = ArticleCRUD.get_by_doi(db_session, sample_article.doi)

        assert retrieved_article is not None
        assert retrieved_article.doi == created_article.doi

    def test_get_by_doi_not_found(self, db_session):
        """Test getting non-existent article."""
        article = ArticleCRUD.get_by_doi(db_session, "10.1000/nonexistent")
        assert article is None

    def test_update_article(self, db_session, sample_article):
        """Test updating an article."""
        article = ArticleCRUD.create(db_session, sample_article)

        update_data = ArticleUpdate(title="Updated Title", year=2024)
        updated_article = ArticleCRUD.update(db_session, article.doi, update_data)

        assert updated_article is not None
        assert updated_article.title == "Updated Title"
        assert updated_article.year == 2024
        assert updated_article.journal == "Test Journal"  # Unchanged

    def test_delete_article(self, db_session, sample_article):
        """Test deleting an article."""
        article = ArticleCRUD.create(db_session, sample_article)

        result = ArticleCRUD.delete(db_session, article.doi)
        assert result is True

        # Verify deletion
        deleted_article = ArticleCRUD.get_by_doi(db_session, article.doi)
        assert deleted_article is None

    def test_search_by_doi(self, db_session, sample_article):
        """Test searching articles by DOI."""
        ArticleCRUD.create(db_session, sample_article)

        query = ArticleSearchQuery(doi="test.article")
        articles, total = ArticleCRUD.search(db_session, query)

        assert total == 1
        assert len(articles) == 1
        assert articles[0].doi == "10.1000/test.article"

    def test_search_by_title(self, db_session, sample_article):
        """Test searching articles by title."""
        ArticleCRUD.create(db_session, sample_article)

        query = ArticleSearchQuery(title="Chemistry")
        articles, total = ArticleCRUD.search(db_session, query)

        assert total == 1
        assert len(articles) == 1

    def test_search_by_year(self, db_session, sample_article):
        """Test searching articles by year."""
        ArticleCRUD.create(db_session, sample_article)

        query = ArticleSearchQuery(year=2023)
        articles, total = ArticleCRUD.search(db_session, query)

        assert total == 1
        assert len(articles) == 1
        assert articles[0].year == 2023

    def test_search_by_author(self, db_session, sample_article, sample_author):
        """Test searching articles by author name."""
        authors = [sample_author]
        ArticleCRUD.create(db_session, sample_article, authors)

        query = ArticleSearchQuery(author="Jane")
        articles, total = ArticleCRUD.search(db_session, query)

        assert total == 1
        assert len(articles) == 1
        assert any(author.first_name == "Jane" for author in articles[0].authors)

    def test_search_with_pagination(self, db_session):
        """Test search with pagination."""
        # Create multiple articles
        for i in range(5):
            article_data = ArticleCreate(
                doi=f"10.1000/test.{i}", title=f"Test Article {i}", year=2023
            )
            ArticleCRUD.create(db_session, article_data)

        query = ArticleSearchQuery(year=2023, limit=2, offset=0)
        articles, total = ArticleCRUD.search(db_session, query)

        assert total == 5
        assert len(articles) == 2

        # Test second page
        query.offset = 2
        articles_page2, total2 = ArticleCRUD.search(db_session, query)
        assert total2 == 5
        assert len(articles_page2) == 2


class TestCompoundCRUD:
    """Test Compound CRUD operations."""

    def test_create_compound(self, db_session, sample_article, sample_compound):
        """Test creating a compound."""
        # Create article first
        ArticleCRUD.create(db_session, sample_article)

        compound = CompoundCRUD.create(db_session, sample_compound)

        assert compound.id is not None
        assert compound.name == "Test Compound"
        assert compound.extraction_method == ExtractionMethod.DECIMER
        assert compound.confidence_score == 0.95

    def test_create_compound_article_not_found(self, db_session, sample_compound):
        """Test creating compound when article doesn't exist."""
        with pytest.raises(ValueError, match="not found"):
            CompoundCRUD.create(db_session, sample_compound)

    def test_get_by_id(self, db_session, sample_article, sample_compound):
        """Test getting compound by ID."""
        ArticleCRUD.create(db_session, sample_article)
        created_compound = CompoundCRUD.create(db_session, sample_compound)

        retrieved_compound = CompoundCRUD.get_by_id(db_session, created_compound.id)

        assert retrieved_compound is not None
        assert retrieved_compound.id == created_compound.id
        assert retrieved_compound.name == "Test Compound"

    def test_get_by_article(self, db_session, sample_article):
        """Test getting compounds by article DOI."""
        ArticleCRUD.create(db_session, sample_article)

        # Create multiple compounds for the article
        for i in range(3):
            compound_data = CompoundCreate(
                article_doi=sample_article.doi,
                name=f"Compound {i}",
                extraction_method=ExtractionMethod.MANUAL,
            )
            CompoundCRUD.create(db_session, compound_data)

        compounds = CompoundCRUD.get_by_article(db_session, sample_article.doi)
        assert len(compounds) == 3
        assert all(c.article_doi == sample_article.doi for c in compounds)

    def test_update_compound(self, db_session, sample_article, sample_compound):
        """Test updating a compound."""
        ArticleCRUD.create(db_session, sample_article)
        compound = CompoundCRUD.create(db_session, sample_compound)

        update_data = CompoundUpdate(name="Updated Compound", confidence_score=0.88)
        updated_compound = CompoundCRUD.update(db_session, compound.id, update_data)

        assert updated_compound is not None
        assert updated_compound.name == "Updated Compound"
        assert updated_compound.confidence_score == 0.88
        assert (
            updated_compound.extraction_method == ExtractionMethod.DECIMER
        )  # Unchanged

    def test_delete_compound(self, db_session, sample_article, sample_compound):
        """Test deleting a compound."""
        ArticleCRUD.create(db_session, sample_article)
        compound = CompoundCRUD.create(db_session, sample_compound)

        result = CompoundCRUD.delete(db_session, compound.id)
        assert result is True

        # Verify deletion
        deleted_compound = CompoundCRUD.get_by_id(db_session, compound.id)
        assert deleted_compound is None


class TestCompoundPropertyCRUD:
    """Test CompoundProperty CRUD operations."""

    def test_create_property(self, db_session, sample_article, sample_compound):
        """Test creating a compound property."""
        ArticleCRUD.create(db_session, sample_article)
        compound = CompoundCRUD.create(db_session, sample_compound)

        property_data = CompoundPropertyCreate(
            compound_id=compound.id,
            property_name="Melting Point",
            value="238",
            units="°C",
        )

        prop = CompoundPropertyCRUD.create(db_session, property_data)

        assert prop.id is not None
        assert prop.compound_id == compound.id
        assert prop.property_name == "Melting Point"
        assert prop.value == "238"
        assert prop.units == "°C"

    def test_create_property_compound_not_found(self, db_session):
        """Test creating property when compound doesn't exist."""
        property_data = CompoundPropertyCreate(
            compound_id=999, property_name="Test", value="Test"
        )

        with pytest.raises(ValueError, match="not found"):
            CompoundPropertyCRUD.create(db_session, property_data)

    def test_get_by_compound(self, db_session, sample_article, sample_compound):
        """Test getting properties by compound ID."""
        ArticleCRUD.create(db_session, sample_article)
        compound = CompoundCRUD.create(db_session, sample_compound)

        # Create multiple properties
        properties_data = [
            {"property_name": "Melting Point", "value": "238", "units": "°C"},
            {"property_name": "Boiling Point", "value": "178", "units": "°C"},
            {"property_name": "Density", "value": "1.23", "units": "g/cm³"},
        ]

        for prop_data in properties_data:
            property_create = CompoundPropertyCreate(
                compound_id=compound.id, **prop_data
            )
            CompoundPropertyCRUD.create(db_session, property_create)

        properties = CompoundPropertyCRUD.get_by_compound(db_session, compound.id)
        assert len(properties) == 3
        assert all(p.compound_id == compound.id for p in properties)

        # Check ordering (should be by property_name)
        property_names = [p.property_name for p in properties]
        assert property_names == sorted(property_names)

    def test_update_property(self, db_session, sample_article, sample_compound):
        """Test updating a compound property."""
        ArticleCRUD.create(db_session, sample_article)
        compound = CompoundCRUD.create(db_session, sample_compound)

        property_data = CompoundPropertyCreate(
            compound_id=compound.id,
            property_name="Melting Point",
            value="238",
            units="°C",
        )
        prop = CompoundPropertyCRUD.create(db_session, property_data)

        from chemlit_extractor.models.schemas import CompoundPropertyUpdate

        update_data = CompoundPropertyUpdate(
            value="240", measurement_type="experimental"
        )
        updated_prop = CompoundPropertyCRUD.update(db_session, prop.id, update_data)

        assert updated_prop is not None
        assert updated_prop.value == "240"
        assert updated_prop.measurement_type == "experimental"
        assert updated_prop.property_name == "Melting Point"  # Unchanged

    def test_delete_property(self, db_session, sample_article, sample_compound):
        """Test deleting a compound property."""
        ArticleCRUD.create(db_session, sample_article)
        compound = CompoundCRUD.create(db_session, sample_compound)

        property_data = CompoundPropertyCreate(
            compound_id=compound.id, property_name="Test Property", value="Test Value"
        )
        prop = CompoundPropertyCRUD.create(db_session, property_data)

        result = CompoundPropertyCRUD.delete(db_session, prop.id)
        assert result is True

        # Verify deletion
        deleted_prop = CompoundPropertyCRUD.get_by_id(db_session, prop.id)
        assert deleted_prop is None


class TestDatabaseStats:
    """Test database statistics function."""

    def test_empty_database_stats(self, db_session):
        """Test stats for empty database."""
        stats = get_database_stats(db_session)

        assert stats.total_articles == 0
        assert stats.total_compounds == 0
        assert stats.total_properties == 0
        assert stats.total_authors == 0

    def test_populated_database_stats(self, db_session, sample_author, sample_article):
        """Test stats for populated database."""
        # Create author
        AuthorCRUD.create(db_session, sample_author)

        # Create article with author
        ArticleCRUD.create(db_session, sample_article, [sample_author])

        # Create compound
        compound_data = CompoundCreate(
            article_doi=sample_article.doi, name="Test Compound"
        )
        compound = CompoundCRUD.create(db_session, compound_data)

        # Create property
        property_data = CompoundPropertyCreate(
            compound_id=compound.id, property_name="Test Property", value="Test Value"
        )
        CompoundPropertyCRUD.create(db_session, property_data)

        stats = get_database_stats(db_session)

        assert stats.total_articles == 1
        assert stats.total_compounds == 1
        assert stats.total_properties == 1
        assert stats.total_authors == 1


class TestCRUDIntegration:
    """Test integration between different CRUD operations."""

    def test_cascade_delete_article(self, db_session, sample_author, sample_article):
        """Test that deleting an article also deletes its compounds and properties."""
        # Create full hierarchy
        AuthorCRUD.create(db_session, sample_author)
        ArticleCRUD.create(db_session, sample_article, [sample_author])

        compound_data = CompoundCreate(
            article_doi=sample_article.doi, name="Test Compound"
        )
        compound = CompoundCRUD.create(db_session, compound_data)

        property_data = CompoundPropertyCreate(
            compound_id=compound.id, property_name="Test Property", value="Test Value"
        )
        CompoundPropertyCRUD.create(db_session, property_data)

        # Verify everything exists
        assert ArticleCRUD.get_by_doi(db_session, sample_article.doi) is not None
        assert CompoundCRUD.get_by_id(db_session, compound.id) is not None
        assert len(CompoundPropertyCRUD.get_by_compound(db_session, compound.id)) == 1

        # Delete article
        ArticleCRUD.delete(db_session, sample_article.doi)

        # Verify cascade deletion
        assert ArticleCRUD.get_by_doi(db_session, sample_article.doi) is None
        assert CompoundCRUD.get_by_id(db_session, compound.id) is None
        assert len(CompoundPropertyCRUD.get_by_compound(db_session, compound.id)) == 0

        # Author should still exist (not cascaded)
        assert AuthorCRUD.count(db_session) == 1

    def test_cascade_delete_compound(self, db_session, sample_article):
        """Test that deleting a compound also deletes its properties."""
        ArticleCRUD.create(db_session, sample_article)

        compound_data = CompoundCreate(
            article_doi=sample_article.doi, name="Test Compound"
        )
        compound = CompoundCRUD.create(db_session, compound_data)

        # Create multiple properties
        for i in range(3):
            property_data = CompoundPropertyCreate(
                compound_id=compound.id,
                property_name=f"Property {i}",
                value=f"Value {i}",
            )
            CompoundPropertyCRUD.create(db_session, property_data)

        # Verify properties exist
        assert len(CompoundPropertyCRUD.get_by_compound(db_session, compound.id)) == 3

        # Delete compound
        CompoundCRUD.delete(db_session, compound.id)

        # Verify cascade deletion of properties
        assert CompoundCRUD.get_by_id(db_session, compound.id) is None
        assert len(CompoundPropertyCRUD.get_by_compound(db_session, compound.id)) == 0

        # Article should still exist
        assert ArticleCRUD.get_by_doi(db_session, sample_article.doi) is not None
