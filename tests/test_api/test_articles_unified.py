"""Test unified article creation endpoint."""

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
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
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


class TestUnifiedArticleEndpoint:
    """Test the new unified article creation endpoint."""

    # ==================== Direct Creation Tests ====================

    def test_create_article_direct(self, client, sample_article_data):
        """Test direct article creation with provided data."""
        request_data = {
            "article_data": sample_article_data,
            "fetch_from_crossref": False,
            "download_files": False,
        }

        response = client.post("/api/v1/articles/", json=request_data)
        assert response.status_code == 201

        data = response.json()
        assert data["success"] is True
        assert data["article"]["doi"] == sample_article_data["doi"]
        assert data["article"]["title"] == sample_article_data["title"]
        assert data["operation_type"] == "created"
        assert data["source"] == "direct"
        assert data["download_status"] is None
        assert "created_at" in data["article"]

    def test_create_article_direct_duplicate(self, client, sample_article_data):
        """Test creating duplicate article with direct data."""
        request_data = {
            "article_data": sample_article_data,
            "fetch_from_crossref": False,
            "download_files": False,
        }

        # Create first article
        response = client.post("/api/v1/articles/", json=request_data)
        assert response.status_code == 201

        # Try to create duplicate
        response = client.post("/api/v1/articles/", json=request_data)
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_create_article_direct_missing_data(self, client):
        """Test direct creation without article data."""
        request_data = {
            "fetch_from_crossref": False,
            "download_files": False,
            # Missing article_data
        }

        response = client.post("/api/v1/articles/", json=request_data)
        assert response.status_code == 422  # Validation error

    # ==================== CrossRef Fetch Tests ====================

    @patch("chemlit_extractor.api.v1.endpoints.articles.CrossRefService")
    def test_create_article_from_crossref(self, mock_service_class, client):
        """Test creating article by fetching from CrossRef."""
        # Setup mock
        mock_service = Mock()
        mock_service_class.return_value = mock_service

        from chemlit_extractor.models.schemas import ArticleCreate, AuthorCreate

        article_data = ArticleCreate(
            doi="10.1000/crossref.test",
            title="CrossRef Test Article",
            journal="CrossRef Journal",
            year=2023,
        )
        authors_data = [
            AuthorCreate(first_name="John", last_name="Doe"),
            AuthorCreate(
                first_name="Jane", last_name="Smith", orcid="0000-0000-0000-0001"
            ),
        ]
        mock_service.fetch_and_convert_article.return_value = (
            article_data,
            authors_data,
        )

        # Make request
        request_data = {
            "doi": "10.1000/crossref.test",
            "fetch_from_crossref": True,
            "download_files": False,
        }

        response = client.post("/api/v1/articles/", json=request_data)
        assert response.status_code == 201

        data = response.json()
        assert data["success"] is True
        assert data["article"]["doi"] == "10.1000/crossref.test"
        assert data["article"]["title"] == "CrossRef Test Article"
        assert data["operation_type"] == "fetched"
        assert data["source"] == "crossref"
        assert len(data["article"]["authors"]) == 2
        assert data["message"] == "Article fetched from CrossRef and created"

        # Verify service was called
        mock_service.fetch_and_convert_article.assert_called_once_with(
            "10.1000/crossref.test"
        )
        mock_service.close.assert_called_once()

    @patch("chemlit_extractor.api.v1.endpoints.articles.CrossRefService")
    def test_create_article_from_crossref_not_found(self, mock_service_class, client):
        """Test creating article from CrossRef when DOI not found."""
        # Setup mock
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.fetch_and_convert_article.return_value = None

        request_data = {
            "doi": "10.1000/notfound",
            "fetch_from_crossref": True,
            "download_files": False,
        }

        response = client.post("/api/v1/articles/", json=request_data)
        assert response.status_code == 404
        assert "not found in CrossRef" in response.json()["detail"]

    def test_create_article_from_crossref_missing_doi(self, client):
        """Test CrossRef fetch without DOI."""
        request_data = {
            "fetch_from_crossref": True,
            "download_files": False,
            # Missing DOI
        }

        response = client.post("/api/v1/articles/", json=request_data)
        assert response.status_code == 422  # Validation error

    @patch("chemlit_extractor.api.v1.endpoints.articles.CrossRefService")
    def test_create_article_from_crossref_already_exists(
        self, mock_service_class, client, sample_article_data
    ):
        """Test CrossRef fetch when article already exists."""
        # Create article first
        create_request = {
            "article_data": sample_article_data,
            "fetch_from_crossref": False,
            "download_files": False,
        }
        response = client.post("/api/v1/articles/", json=create_request)
        assert response.status_code == 201

        # Try to fetch same DOI from CrossRef
        request_data = {
            "doi": sample_article_data["doi"],
            "fetch_from_crossref": True,
            "download_files": False,
        }

        response = client.post("/api/v1/articles/", json=request_data)
        assert response.status_code == 201  # Should succeed but return existing

        data = response.json()
        assert data["success"] is True
        assert data["article"]["doi"] == sample_article_data["doi"]
        assert data["operation_type"] == "existed"
        assert data["source"] == "database"
        assert len(data["warnings"]) > 0
        assert "already exists" in data["warnings"][0]

    # ==================== File Download Tests ====================

    @patch("chemlit_extractor.api.v1.endpoints.articles.CrossRefService")
    @patch("chemlit_extractor.api.v1.endpoints.articles._download_files_for_article")
    def test_create_article_with_file_downloads(
        self, mock_download, mock_service_class, client
    ):
        """Test creating article from CrossRef with file downloads."""
        # Setup CrossRef mock
        mock_service = Mock()
        mock_service_class.return_value = mock_service

        from chemlit_extractor.models.schemas import ArticleCreate, AuthorCreate

        article_data = ArticleCreate(
            doi="10.1000/download.test",
            title="Download Test Article",
            journal="Test Journal",
            year=2023,
        )
        authors_data = [AuthorCreate(first_name="Test", last_name="Author")]
        mock_service.fetch_and_convert_article.return_value = (
            article_data,
            authors_data,
        )

        # Make request with file URLs
        request_data = {
            "doi": "10.1000/download.test",
            "fetch_from_crossref": True,
            "download_files": True,
            "file_urls": {
                "pdf_url": "https://example.com/article.pdf",
                "html_url": "https://example.com/article.html",
                "supplementary_urls": [
                    "https://example.com/supp1.zip",
                    "https://example.com/supp2.csv",
                ],
            },
        }

        response = client.post("/api/v1/articles/", json=request_data)
        assert response.status_code == 201

        data = response.json()
        assert data["success"] is True
        assert data["operation_type"] == "fetched"
        assert data["download_status"] is not None
        assert data["download_status"]["triggered"] is True
        assert (
            data["download_status"]["file_count"] == 4
        )  # 1 PDF + 1 HTML + 2 supplementary
        assert "pdf" in data["download_status"]["files"]
        assert "html" in data["download_status"]["files"]
        assert "supplementary" in data["download_status"]["files"]
        assert (
            "Article fetched from CrossRef and created. 4 file downloads triggered"
            in data["message"]
        )

        # Verify background task was triggered
        mock_download.assert_called_once_with(
            "10.1000/download.test",
            "https://example.com/article.pdf",
            "https://example.com/article.html",
            ["https://example.com/supp1.zip", "https://example.com/supp2.csv"],
        )

    def test_download_files_for_existing_article(self, client, sample_article_data):
        """Test downloading files for an already existing article."""
        # Create article first
        create_request = {
            "article_data": sample_article_data,
            "fetch_from_crossref": False,
            "download_files": False,
        }
        response = client.post("/api/v1/articles/", json=create_request)
        assert response.status_code == 201

        # Now try to add files
        with patch(
            "chemlit_extractor.api.v1.endpoints.articles._download_files_for_article"
        ):
            request_data = {
                "doi": sample_article_data["doi"],
                "fetch_from_crossref": True,  # Will detect existing article
                "download_files": True,
                "file_urls": {
                    "pdf_url": "https://example.com/existing.pdf",
                },
            }

            response = client.post("/api/v1/articles/", json=request_data)
            assert response.status_code == 201

            data = response.json()
            assert data["success"] is True
            assert data["operation_type"] == "existed"
            assert data["download_status"]["triggered"] is True
            assert data["download_status"]["file_count"] == 1
            assert (
                "Article already exists. 1 file downloads triggered" in data["message"]
            )

    def test_download_files_no_urls_provided(self, client):
        """Test download files enabled but no URLs provided."""
        with patch(
            "chemlit_extractor.api.v1.endpoints.articles.CrossRefService"
        ) as mock_service_class:
            mock_service = Mock()
            mock_service_class.return_value = mock_service

            from chemlit_extractor.models.schemas import ArticleCreate

            article_data = ArticleCreate(
                doi="10.1000/nofiles.test",
                title="No Files Test",
                journal="Test Journal",
                year=2023,
            )
            mock_service.fetch_and_convert_article.return_value = (article_data, [])

            request_data = {
                "doi": "10.1000/nofiles.test",
                "fetch_from_crossref": True,
                "download_files": True,
                # No file_urls provided
            }

            response = client.post("/api/v1/articles/", json=request_data)
            assert response.status_code == 201

            data = response.json()
            assert data["success"] is True
            assert data["download_status"]["triggered"] is False
            assert (
                data["download_status"]["message"]
                == "No file URLs provided for download"
            )

    # ==================== Validation Tests ====================

    def test_invalid_doi_format(self, client):
        """Test validation of invalid DOI format."""
        request_data = {
            "doi": "invalid-doi-format",
            "fetch_from_crossref": True,
            "download_files": False,
        }

        response = client.post("/api/v1/articles/", json=request_data)
        assert response.status_code == 422
        assert "DOI must start with '10.'" in response.text

    def test_conflicting_options(self, client, sample_article_data):
        """Test providing both article_data and fetch_from_crossref."""
        request_data = {
            "article_data": sample_article_data,
            "doi": "10.1000/different.doi",
            "fetch_from_crossref": True,  # This should be ignored when article_data is provided
            "download_files": False,
        }

        response = client.post("/api/v1/articles/", json=request_data)
        # Should use article_data and ignore CrossRef fetch
        assert response.status_code == 201

        data = response.json()
        assert (
            data["article"]["doi"] == sample_article_data["doi"]
        )  # Uses article_data DOI
        assert data["source"] == "direct"

    # ==================== Error Handling Tests ====================

    @patch("chemlit_extractor.api.v1.endpoints.articles.CrossRefService")
    def test_crossref_service_error(self, mock_service_class, client):
        """Test handling of CrossRef service errors."""
        # Setup mock to raise exception
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        mock_service.fetch_and_convert_article.side_effect = Exception(
            "CrossRef API error"
        )

        request_data = {
            "doi": "10.1000/error.test",
            "fetch_from_crossref": True,
            "download_files": False,
        }

        response = client.post("/api/v1/articles/", json=request_data)
        assert response.status_code == 502
        assert "Failed to fetch from CrossRef" in response.json()["detail"]

    @patch("chemlit_extractor.api.v1.endpoints.articles.ArticleCRUD.create")
    def test_database_error(self, mock_create, client, sample_article_data):
        """Test handling of database errors."""
        mock_create.side_effect = ValueError("Database constraint violation")

        request_data = {
            "article_data": sample_article_data,
            "fetch_from_crossref": False,
            "download_files": False,
        }

        response = client.post("/api/v1/articles/", json=request_data)
        assert response.status_code == 400
        assert "Database constraint violation" in response.json()["detail"]

    # ==================== Complex Scenario Tests ====================

    def test_complete_workflow_with_all_options(self, client):
        """Test the complete workflow with all options enabled."""
        with patch(
            "chemlit_extractor.api.v1.endpoints.articles.CrossRefService"
        ) as mock_service_class:
            with patch(
                "chemlit_extractor.api.v1.endpoints.articles._download_files_for_article"
            ):
                # Setup CrossRef mock
                mock_service = Mock()
                mock_service_class.return_value = mock_service

                from chemlit_extractor.models.schemas import ArticleCreate, AuthorCreate

                article_data = ArticleCreate(
                    doi="10.1000/complete.test",
                    title="Complete Workflow Test",
                    journal="Nature",
                    year=2024,
                    abstract="This tests everything.",
                )
                authors_data = [
                    AuthorCreate(
                        first_name="Alice",
                        last_name="Smith",
                        orcid="0000-0000-0000-0001",
                    ),
                    AuthorCreate(first_name="Bob", last_name="Jones"),
                ]
                mock_service.fetch_and_convert_article.return_value = (
                    article_data,
                    authors_data,
                )

                # Make request with all options
                request_data = {
                    "doi": "10.1000/complete.test",
                    "fetch_from_crossref": True,
                    "download_files": True,
                    "file_urls": {
                        "pdf_url": "https://nature.com/articles/complete.pdf",
                        "html_url": "https://nature.com/articles/complete.html",
                        "supplementary_urls": [
                            "https://nature.com/articles/complete_supp1.xlsx",
                            "https://nature.com/articles/complete_supp2.csv",
                            "https://nature.com/articles/complete_supp3.zip",
                        ],
                    },
                }

                response = client.post("/api/v1/articles/", json=request_data)
                assert response.status_code == 201

                data = response.json()

                # Verify article creation
                assert data["success"] is True
                assert data["article"]["doi"] == "10.1000/complete.test"
                assert data["article"]["title"] == "Complete Workflow Test"
                assert len(data["article"]["authors"]) == 2

                # Verify operation metadata
                assert data["operation_type"] == "fetched"
                assert data["source"] == "crossref"

                # Verify download status
                assert data["download_status"]["triggered"] is True
                assert (
                    data["download_status"]["file_count"] == 5
                )  # 1 PDF + 1 HTML + 3 supplementary
                assert "pdf" in data["download_status"]["files"]
                assert "html" in data["download_status"]["files"]
                assert "3 files" in data["download_status"]["files"]["supplementary"]

                # Verify message
                assert "Article fetched from CrossRef and created" in data["message"]
                assert "5 file downloads triggered" in data["message"]


class TestDeprecatedEndpoints:
    """Test that deprecated endpoints still work but show warnings."""

    @patch("chemlit_extractor.api.v1.endpoints.articles.CrossRefService")
    def test_deprecated_from_doi_endpoint(self, mock_service_class, client):
        """Test deprecated /from-doi endpoint still works."""
        # Setup mock
        mock_service = Mock()
        mock_service_class.return_value = mock_service

        from chemlit_extractor.models.schemas import ArticleCreate

        article_data = ArticleCreate(
            doi="10.1000/deprecated.test",
            title="Deprecated Endpoint Test",
            journal="Test Journal",
            year=2023,
        )
        mock_service.fetch_and_convert_article.return_value = (article_data, [])

        # Use deprecated endpoint
        with pytest.warns(DeprecationWarning):
            response = client.post(
                "/api/v1/articles/from-doi?doi=10.1000/deprecated.test"
            )

        assert response.status_code == 201
        data = response.json()
        assert data["doi"] == "10.1000/deprecated.test"

    def test_deprecated_trigger_downloads_endpoint(self, client, sample_article_data):
        """Test deprecated trigger-downloads endpoint still works."""
        # Create article first
        create_request = {
            "article_data": sample_article_data,
            "fetch_from_crossref": False,
            "download_files": False,
        }
        response = client.post("/api/v1/articles/", json=create_request)
        assert response.status_code == 201

        # Use deprecated endpoint
        with pytest.warns(DeprecationWarning):
            with patch(
                "chemlit_extractor.api.v1.endpoints.articles._download_files_for_article"
            ):
                response = client.post(
                    f"/api/v1/articles/{sample_article_data['doi']}/trigger-downloads"
                    "?pdf_url=https://example.com/test.pdf"
                )

        assert response.status_code == 200
        data = response.json()
        assert data["doi"] == sample_article_data["doi"]
        assert data["download_triggered"] is True
