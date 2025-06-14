"""Test API endpoints."""

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from chemlit_extractor.database import get_db
from chemlit_extractor.database.models import Base
from chemlit_extractor.main import app


@pytest.fixture(scope="function")
def test_db_session():
    """Create a test database session."""
    # Use SQLite with specific connection parameters for thread safety
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,  # Use StaticPool to share connection
        connect_args={
            "check_same_thread": False,  # Allow SQLite to be used across threads
        },
    )
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(test_db_session):
    """Create a test client with test database."""

    def override_get_db():
        try:
            yield test_db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def sample_article_data():
    """Sample article data for testing."""
    return {
        "doi": "10.1000/test.article",
        "title": "Test Article About Chemistry",
        "journal": "Test Journal",
        "year": 2023,
        "abstract": "This is a test abstract.",
    }


@pytest.fixture
def sample_author_data():
    """Sample author data for testing."""
    return {
        "first_name": "Jane",
        "last_name": "Doe",
        "orcid": "0000-0000-0000-0000",
        "email": "jane.doe@university.edu",
    }


class TestRootEndpoints:
    """Test root endpoints."""

    def test_root_endpoint(self, client):
        """Test root endpoint."""
        response = client.get("/")
        assert response.status_code == 200

        data = response.json()
        assert data["message"] == "Welcome to ChemLit Extractor"
        assert data["version"] == "0.1.0"
        assert "/docs" in data["docs_url"]

    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "ChemLit Extractor"


class TestStatsEndpoints:
    """Test statistics endpoints."""

    def test_get_stats_empty_database(self, client):
        """Test stats endpoint with empty database."""
        response = client.get("/api/v1/stats/")
        assert response.status_code == 200

        data = response.json()
        assert data["total_articles"] == 0
        assert data["total_compounds"] == 0
        assert data["total_properties"] == 0
        assert data["total_authors"] == 0

    def test_get_stats_summary_empty(self, client):
        """Test stats summary with empty database."""
        response = client.get("/api/v1/stats/summary")
        assert response.status_code == 200

        data = response.json()
        assert data["total_articles"] == 0
        assert data["avg_compounds_per_article"] == 0.0
        assert "Database contains 0 articles" in data["summary"]


class TestArticleEndpoints:
    """Test article endpoints."""

    def test_create_article(self, client, sample_article_data):
        """Test creating an article."""
        response = client.post("/api/v1/articles/", json=sample_article_data)
        assert response.status_code == 201

        data = response.json()
        assert data["doi"] == sample_article_data["doi"]
        assert data["title"] == sample_article_data["title"]
        assert "created_at" in data

    def test_create_article_duplicate_doi(self, client, sample_article_data):
        """Test creating article with duplicate DOI."""
        # Create first article
        client.post("/api/v1/articles/", json=sample_article_data)

        # Try to create duplicate
        response = client.post("/api/v1/articles/", json=sample_article_data)
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_get_article_by_doi(self, client, sample_article_data):
        """Test getting article by DOI."""
        # Create article first
        client.post("/api/v1/articles/", json=sample_article_data)

        # Get article
        response = client.get(f"/api/v1/articles/{sample_article_data['doi']}")
        assert response.status_code == 200

        data = response.json()
        assert data["doi"] == sample_article_data["doi"]
        assert data["title"] == sample_article_data["title"]

    def test_get_article_not_found(self, client):
        """Test getting non-existent article."""
        response = client.get("/api/v1/articles/10.1000/nonexistent")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_search_articles_empty(self, client):
        """Test searching articles in empty database."""
        response = client.get("/api/v1/articles/")
        assert response.status_code == 200

        data = response.json()
        assert data["articles"] == []
        assert data["total_count"] == 0
        assert data["limit"] == 20
        assert data["offset"] == 0

    def test_search_articles_with_results(self, client, sample_article_data):
        """Test searching articles with results."""
        # Create article first
        client.post("/api/v1/articles/", json=sample_article_data)

        # Search by title
        response = client.get("/api/v1/articles/?title=Chemistry")
        assert response.status_code == 200

        data = response.json()
        assert len(data["articles"]) == 1
        assert data["total_count"] == 1
        assert data["articles"][0]["title"] == sample_article_data["title"]

    def test_search_articles_pagination(self, client):
        """Test article search pagination."""
        # Create multiple articles
        for i in range(5):
            article_data = {
                "doi": f"10.1000/test.{i}",
                "title": f"Test Article {i}",
                "year": 2023,
            }
            client.post("/api/v1/articles/", json=article_data)

        # Test pagination
        response = client.get("/api/v1/articles/?limit=2&offset=0")
        assert response.status_code == 200

        data = response.json()
        assert len(data["articles"]) == 2
        assert data["total_count"] == 5
        assert data["limit"] == 2
        assert data["offset"] == 0

        # Test second page
        response = client.get("/api/v1/articles/?limit=2&offset=2")
        data = response.json()
        assert len(data["articles"]) == 2
        assert data["offset"] == 2

    def test_update_article(self, client, sample_article_data):
        """Test updating an article."""
        # Create article first
        client.post("/api/v1/articles/", json=sample_article_data)

        # Update article
        update_data = {"title": "Updated Title", "year": 2024}
        response = client.put(
            f"/api/v1/articles/{sample_article_data['doi']}", json=update_data
        )
        assert response.status_code == 200

        data = response.json()
        assert data["title"] == "Updated Title"
        assert data["year"] == 2024
        assert data["journal"] == sample_article_data["journal"]  # Unchanged

    def test_update_article_not_found(self, client):
        """Test updating non-existent article."""
        update_data = {"title": "New Title"}
        response = client.put("/api/v1/articles/10.1000/nonexistent", json=update_data)
        assert response.status_code == 404

    def test_delete_article(self, client, sample_article_data):
        """Test deleting an article."""
        # Create article first
        client.post("/api/v1/articles/", json=sample_article_data)

        # Delete article
        response = client.delete(f"/api/v1/articles/{sample_article_data['doi']}")
        assert response.status_code == 204

        # Verify deletion
        response = client.get(f"/api/v1/articles/{sample_article_data['doi']}")
        assert response.status_code == 404

    def test_delete_article_not_found(self, client):
        """Test deleting non-existent article."""
        response = client.delete("/api/v1/articles/10.1000/nonexistent")
        assert response.status_code == 404

    @patch("chemlit_extractor.api.v1.endpoints.articles.CrossRefService")
    def test_create_article_from_doi_success(self, mock_service_class, client):
        """Test creating article from DOI via CrossRef."""
        # Setup mock
        mock_service = Mock()
        mock_service_class.return_value = mock_service

        # Mock CrossRef response - ensure data matches Pydantic schemas
        from chemlit_extractor.models.schemas import ArticleCreate, AuthorCreate

        article_data = ArticleCreate(
            doi="10.1000/crossref.test",
            title="CrossRef Test Article",
            journal="CrossRef Journal",
            year=2023,
        )
        authors_data = [AuthorCreate(first_name="John", last_name="Doe")]
        mock_service.fetch_and_convert_article.return_value = (
            article_data,
            authors_data,
        )

        # Make request
        response = client.post("/api/v1/articles/from-doi?doi=10.1000/crossref.test")

        # Debug output if test fails
        if response.status_code != 201:
            print(f"Response status: {response.status_code}")
            print(f"Response body: {response.json()}")

        assert response.status_code == 201

        data = response.json()
        assert data["doi"] == "10.1000/crossref.test"
        assert data["title"] == "CrossRef Test Article"
        assert len(data["authors"]) == 1

        # Verify service was called
        mock_service.fetch_and_convert_article.assert_called_once_with(
            "10.1000/crossref.test"
        )
        mock_service.close.assert_called_once()

    @patch("chemlit_extractor.services.crossref.CrossRefService")
    def test_create_article_from_doi_not_found(self, mock_service_class, client):
        """Test creating article from DOI when not found in CrossRef."""
        # Setup mock
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.fetch_and_convert_article.return_value = None

        # Make request
        response = client.post("/api/v1/articles/from-doi?doi=10.1000/notfound")
        assert response.status_code == 404
        assert "not found in CrossRef" in response.json()["detail"]

    @patch("chemlit_extractor.services.crossref.CrossRefService")
    def test_create_article_from_doi_already_exists(
        self, mock_service_class, client, sample_article_data
    ):
        """Test creating article from DOI when article already exists."""
        # Create article first
        client.post("/api/v1/articles/", json=sample_article_data)

        # Try to create same article from DOI
        response = client.post(
            f"/api/v1/articles/from-doi?doi={sample_article_data['doi']}"
        )
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]


class TestAuthorEndpoints:
    """Test author endpoints."""

    def test_create_author(self, client, sample_author_data):
        """Test creating an author."""
        response = client.post("/api/v1/authors/", json=sample_author_data)
        assert response.status_code == 201

        data = response.json()
        assert data["first_name"] == sample_author_data["first_name"]
        assert data["last_name"] == sample_author_data["last_name"]
        assert "id" in data

    def test_get_author_by_id(self, client, sample_author_data):
        """Test getting author by ID."""
        # Create author first
        create_response = client.post("/api/v1/authors/", json=sample_author_data)
        author_id = create_response.json()["id"]

        # Get author
        response = client.get(f"/api/v1/authors/{author_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == author_id
        assert data["first_name"] == sample_author_data["first_name"]

    def test_get_author_not_found(self, client):
        """Test getting non-existent author."""
        response = client.get("/api/v1/authors/999")
        assert response.status_code == 404

    def test_get_authors_pagination(self, client):
        """Test getting authors with pagination."""
        # Create multiple authors
        for i in range(5):
            author_data = {"first_name": f"Author{i}", "last_name": "Test"}
            client.post("/api/v1/authors/", json=author_data)

        # Test pagination
        response = client.get("/api/v1/authors/?limit=3")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 3

    def test_update_author(self, client, sample_author_data):
        """Test updating an author."""
        # Create author first
        create_response = client.post("/api/v1/authors/", json=sample_author_data)
        author_id = create_response.json()["id"]

        # Update author
        update_data = {"email": "new.email@university.edu"}
        response = client.put(f"/api/v1/authors/{author_id}", json=update_data)
        assert response.status_code == 200

        data = response.json()
        assert data["email"] == "new.email@university.edu"
        assert data["first_name"] == sample_author_data["first_name"]  # Unchanged

    def test_delete_author(self, client, sample_author_data):
        """Test deleting an author."""
        # Create author first
        create_response = client.post("/api/v1/authors/", json=sample_author_data)
        author_id = create_response.json()["id"]

        # Delete author
        response = client.delete(f"/api/v1/authors/{author_id}")
        assert response.status_code == 204

        # Verify deletion
        response = client.get(f"/api/v1/authors/{author_id}")
        assert response.status_code == 404


class TestCompoundEndpoints:
    """Test compound endpoints."""

    def test_create_compound_without_article(self, client):
        """Test creating compound when article doesn't exist."""
        compound_data = {"article_doi": "10.1000/nonexistent", "name": "Test Compound"}

        response = client.post("/api/v1/compounds/", json=compound_data)
        assert response.status_code == 400
        assert "not found" in response.json()["detail"]

    def test_create_compound_with_article(self, client, sample_article_data):
        """Test creating compound with existing article."""
        # Create article first
        client.post("/api/v1/articles/", json=sample_article_data)

        # Create compound
        compound_data = {
            "article_doi": sample_article_data["doi"],
            "name": "Test Compound",
            "extraction_method": "manual",
            "confidence_score": 0.95,
        }

        response = client.post("/api/v1/compounds/", json=compound_data)
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "Test Compound"
        assert data["article_doi"] == sample_article_data["doi"]
        assert data["extraction_method"] == "manual"
        assert "id" in data

    def test_get_compound_by_id(self, client, sample_article_data):
        """Test getting compound by ID."""
        # Create article and compound
        client.post("/api/v1/articles/", json=sample_article_data)

        compound_data = {
            "article_doi": sample_article_data["doi"],
            "name": "Test Compound",
        }
        create_response = client.post("/api/v1/compounds/", json=compound_data)
        compound_id = create_response.json()["id"]

        # Get compound
        response = client.get(f"/api/v1/compounds/{compound_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == compound_id
        assert data["name"] == "Test Compound"

    def test_get_article_compounds(self, client, sample_article_data):
        """Test getting compounds for an article."""
        # Create article first
        article_response = client.post("/api/v1/articles/", json=sample_article_data)
        assert article_response.status_code == 201

        # Create multiple compounds
        for i in range(3):
            compound_data = {
                "article_doi": sample_article_data["doi"],
                "name": f"Compound {i}",
            }
            compound_response = client.post("/api/v1/compounds/", json=compound_data)
            assert compound_response.status_code == 201

        # Get article compounds
        compounds_url = f"/api/v1/articles/{sample_article_data['doi']}/compounds"
        response = client.get(compounds_url)

        # Debug output if test fails
        if response.status_code != 200:
            print(f"URL: {compounds_url}")
            print(f"Response status: {response.status_code}")
            print(f"Response body: {response.text}")

            # Also check if article exists
            article_check = client.get(f"/api/v1/articles/{sample_article_data['doi']}")
            print(f"Article exists check: {article_check.status_code}")

        assert response.status_code == 200

        data = response.json()
        assert len(data) == 3
        assert all(c["article_doi"] == sample_article_data["doi"] for c in data)

    '''
    def test_get_article_compounds(self, client, sample_article_data):
        """Test getting compounds for an article."""
        # Create article first
        article_response = client.post("/api/v1/articles/", json=sample_article_data)
        assert article_response.status_code == 201

        # Create multiple compounds
        for i in range(3):
            compound_data = {
                "article_doi": sample_article_data["doi"],
                "name": f"Compound {i}",
            }
            compound_response = client.post("/api/v1/compounds/", json=compound_data)
            assert compound_response.status_code == 201

        # Get article compounds
        response = client.get(
            f"/api/v1/articles/{sample_article_data['doi']}/compounds"
        )
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 3
        assert all(c["article_doi"] == sample_article_data["doi"] for c in data)
i   '''


class TestEndpointIntegration:
    """Test integration between different endpoints."""

    def test_full_workflow(self, client):
        """Test complete workflow: create article, add compounds, add properties."""
        # 1. Create article
        article_data = {
            "doi": "10.1000/workflow.test",
            "title": "Workflow Test Article",
            "year": 2023,
        }
        response = client.post("/api/v1/articles/", json=article_data)
        assert response.status_code == 201

        # 2. Create compound
        compound_data = {
            "article_doi": article_data["doi"],
            "name": "Workflow Test Compound",
        }
        response = client.post("/api/v1/compounds/", json=compound_data)
        assert response.status_code == 201
        compound_id = response.json()["id"]

        # 3. Create property
        property_data = {
            "compound_id": compound_id,
            "property_name": "Melting Point",
            "value": "100",
            "units": "°C",
        }
        response = client.post(
            f"/api/v1/compounds/{compound_id}/properties", json=property_data
        )
        assert response.status_code == 201

        # 4. Verify stats
        response = client.get("/api/v1/stats/")
        stats = response.json()
        assert stats["total_articles"] >= 1
        assert stats["total_compounds"] >= 1
        assert stats["total_properties"] >= 1
