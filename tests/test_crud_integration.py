"""Integration test for CRUD operations with real database."""

import pytest

from chemlit_extractor.database import (
    ArticleCRUD,
    AuthorCRUD,
    CompoundCRUD,
    CompoundPropertyCRUD,
    get_database_stats,
    get_db_session,
)
from chemlit_extractor.models.schemas import (
    ArticleCreate,
    ArticleSearchQuery,
    AuthorCreate,
    CompoundCreate,
    CompoundPropertyCreate,
    ExtractionMethod,
)


@pytest.fixture(scope="function")
def real_db_session():
    """
    Get a real database session for integration testing.

    Note: This uses the actual database configured in .env
    Be careful with this fixture - it modifies real data!
    """
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


class TestCRUDIntegration:
    """Integration tests for CRUD operations with real database."""

    @pytest.mark.integration
    def test_full_workflow(self, real_db_session):
        """Test complete workflow: create article, author, compound, property."""
        # Create author
        author_data = AuthorCreate(
            first_name="Integration",
            last_name="Test",
            orcid="0000-0000-0000-9999",
            email="integration.test@example.com",
        )
        author = AuthorCRUD.get_or_create(real_db_session, author_data)

        # Create article with author
        article_data = ArticleCreate(
            doi="10.9999/integration.test",
            title="Integration Test Article",
            journal="Test Journal of Integration",
            year=2024,
            abstract="This is an integration test article.",
        )

        # Clean up any existing test data first
        existing_article = ArticleCRUD.get_by_doi(real_db_session, article_data.doi)
        if existing_article:
            ArticleCRUD.delete(real_db_session, article_data.doi)

        article = ArticleCRUD.create(real_db_session, article_data, [author_data])

        # Create compound
        compound_data = CompoundCreate(
            article_doi=article.doi,
            name="Integration Test Compound",
            extraction_method=ExtractionMethod.MANUAL,
            confidence_score=1.0,
            notes="Created during integration testing",
        )
        compound = CompoundCRUD.create(real_db_session, compound_data)

        # Create properties
        properties_data = [
            {
                "property_name": "Melting Point",
                "value": "100",
                "units": "°C",
                "measurement_type": "experimental",
            },
            {
                "property_name": "Molecular Weight",
                "value": "250.5",
                "units": "g/mol",
                "measurement_type": "calculated",
            },
        ]

        created_properties = []
        for prop_data in properties_data:
            property_create = CompoundPropertyCreate(
                compound_id=compound.id, **prop_data
            )
            prop = CompoundPropertyCRUD.create(real_db_session, property_create)
            created_properties.append(prop)

        # Verify the complete structure
        retrieved_article = ArticleCRUD.get_by_doi(real_db_session, article.doi)
        assert retrieved_article is not None
        assert len(retrieved_article.authors) >= 1

        compounds = CompoundCRUD.get_by_article(real_db_session, article.doi)
        assert len(compounds) >= 1

        properties = CompoundPropertyCRUD.get_by_compound(real_db_session, compound.id)
        assert len(properties) == 2

        # Test search functionality
        search_query = ArticleSearchQuery(title="Integration Test", limit=10)
        articles, total = ArticleCRUD.search(real_db_session, search_query)
        assert total >= 1
        assert any(a.doi == article.doi for a in articles)

        # Test database stats
        stats = get_database_stats(real_db_session)
        assert stats.total_articles >= 1
        assert stats.total_compounds >= 1
        assert stats.total_properties >= 2
        assert stats.total_authors >= 1

        # Clean up test data
        ArticleCRUD.delete(real_db_session, article.doi)

        # Verify cleanup (compound and properties should be cascade deleted)
        assert ArticleCRUD.get_by_doi(real_db_session, article.doi) is None
        assert CompoundCRUD.get_by_id(real_db_session, compound.id) is None

        # Author might still exist if used elsewhere, that's OK

        print("✅ Integration test completed successfully!")

    @pytest.mark.integration
    def test_author_deduplication(self, real_db_session):
        """Test that authors are properly deduplicated."""
        author_data = AuthorCreate(
            first_name="Dedup", last_name="Test", orcid="0000-0000-0000-8888"
        )

        # Create author twice
        author1 = AuthorCRUD.get_or_create(real_db_session, author_data)
        author2 = AuthorCRUD.get_or_create(real_db_session, author_data)

        # Should be the same author
        assert author1.id == author2.id

        # Clean up
        AuthorCRUD.delete(real_db_session, author1.id)

    @pytest.mark.integration
    def test_search_functionality(self, real_db_session):
        """Test search across different fields."""
        # This test assumes there's some data in the database
        # Just test that search doesn't crash and returns reasonable results

        search_queries = [
            ArticleSearchQuery(limit=5),  # Get any 5 articles
            ArticleSearchQuery(year=2023, limit=5),  # Articles from 2023
            ArticleSearchQuery(journal="nature", limit=5),  # Nature articles
        ]

        for query in search_queries:
            try:
                articles, total = ArticleCRUD.search(real_db_session, query)
                assert isinstance(articles, list)
                assert isinstance(total, int)
                assert total >= 0
                assert len(articles) <= query.limit
                print(
                    f"✅ Search query {query} returned {len(articles)}/{total} results"
                )
            except Exception as e:
                pytest.fail(f"Search query {query} failed: {e}")


# Run integration tests only when explicitly requested
def test_integration_tests_available():
    """This test confirms integration tests are available but skipped by default."""
    pytest.skip(
        "Integration tests require explicit --integration flag or -m integration"
    )


@pytest.mark.integration
def test_database_connection_real():
    """Simple test to verify we can connect to the real database."""
    try:
        db = get_db_session()
        stats = get_database_stats(db)
        db.close()

        assert isinstance(stats.total_articles, int)
        assert stats.total_articles >= 0
        print(f"✅ Database connection successful. Articles: {stats.total_articles}")

    except Exception as e:
        pytest.fail(f"Database connection failed: {e}")
