"""Test file management API endpoints."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from chemlit_extractor.database import get_db
from chemlit_extractor.database.models import Base


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

    # Create a copy of the app for testing to avoid lifespan issues
    from fastapi import FastAPI

    from chemlit_extractor.api.v1.api import api_router

    test_app = FastAPI()
    test_app.include_router(api_router, prefix="/api/v1")

    # Override database dependency
    test_app.dependency_overrides[get_db] = override_get_db

    with TestClient(test_app) as test_client:
        yield test_client


@pytest.fixture
def temp_file_settings():
    """Temporary file settings for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a more comprehensive mock for settings
        mock_settings = MagicMock()
        mock_settings.articles_path = Path(temp_dir)
        mock_settings.max_file_size_mb = 10
        mock_settings.debug = True

        # Patch settings in all possible locations
        patches = []
        patch_locations = [
            "chemlit_extractor.services.file_utils.settings",
            "chemlit_extractor.services.file_management.settings",
            "chemlit_extractor.core.config.settings",
            "chemlit_extractor.api.v1.endpoints.files.settings",
        ]

        for location in patch_locations:
            try:
                p = patch(location, mock_settings)
                p.start()
                patches.append(p)
            except (ImportError, AttributeError):
                # Module/attribute might not exist, continue
                pass

        try:
            yield mock_settings
        finally:
            for p in patches:
                try:
                    p.stop()
                except:
                    pass


@pytest.fixture
def sample_article_with_files(client, temp_file_settings):
    """Create a sample article and set up test files."""
    # Create article first
    article_data = {
        "doi": "10.1000/file.test",
        "title": "File Test Article",
        "year": 2023,
    }
    response = client.post("/api/v1/articles/", json=article_data)
    assert response.status_code == 201

    # Mock the file utilities to use our temp directory
    with patch(
        "chemlit_extractor.services.file_utils.create_article_directories"
    ) as mock_create:
        article_dir = temp_file_settings.articles_path / "10_1000_file_test"
        directories = {
            "article": article_dir,
            "pdf": article_dir / "pdf",
            "html": article_dir / "html",
            "images": article_dir / "images",
            "supplementary": article_dir / "supplementary",
        }

        # Create directories
        for dir_path in directories.values():
            dir_path.mkdir(parents=True, exist_ok=True)

        mock_create.return_value = directories

        # Create test files
        (directories["pdf"] / "article.pdf").write_text("fake pdf content")
        (directories["html"] / "article.html").write_text("fake html content")
        (directories["images"] / "figure1.png").write_text("fake image")

        yield article_data["doi"], directories


class TestFileListingEndpoints:
    """Test file listing endpoints."""

    def test_debug_routes(self, client):
        """Debug test to check available routes."""
        # This test helps debug routing issues
        response = client.get("/api/v1/")
        print(f"Root API response: {response.status_code}")

        # Try to access a simple endpoint that should exist
        response = client.get("/api/v1/stats/")
        print(f"Stats endpoint response: {response.status_code}")

        # Test basic file endpoint structure
        response = client.get("/api/v1/files/10.1000/test.doi")
        print(f"Basic file endpoint: {response.status_code}")
        if response.status_code != 200:
            print(f"Error: {response.text}")

        # Test the specific failing endpoint
        response = client.get("/api/v1/files/10.1000/file.test/files/pdf")
        print(f"File type endpoint: {response.status_code}")
        if response.status_code != 200:
            print(f"Error: {response.text}")

    def test_debug_file_type_enum(self, client):
        """Debug the FileType enum values."""
        from chemlit_extractor.services.file_utils import FileType

        print(f"FileType type: {type(FileType)}")
        print(f"FileType: {FileType}")

        # Try different ways to access values
        try:
            print(f"FileType values: {list(FileType)}")
        except Exception as e:
            print(f"Can't list FileType: {e}")

        try:
            print(f"FileType.__members__: {FileType.__members__}")
        except Exception as e:
            print(f"No __members__: {e}")

        # FIRST CREATE AN ARTICLE for testing
        article_data = {"doi": "10.1000/test.doi", "title": "Test Article"}
        response = client.post("/api/v1/articles/", json=article_data)
        print(f"Create article: {response.status_code}")

        # Test with some common file types manually
        for file_type in ["pdf", "html", "images", "supplementary"]:
            response = client.get(f"/api/v1/files/10.1000/test.doi/files/{file_type}")
            print(f"FileType '{file_type}': {response.status_code}")
            if response.status_code not in [
                200,
                404,
            ]:  # 404 is expected for non-existent article
                print(f"Unexpected status for '{file_type}': {response.text}")
            elif response.status_code == 200:
                print(f"SUCCESS: {file_type} endpoint works!")

    def test_list_article_files_empty(self, client, temp_file_settings):
        """Test listing files for article with no files."""
        # Create article without files
        article_data = {"doi": "10.1000/empty.test", "title": "Empty Test"}
        response = client.post("/api/v1/articles/", json=article_data)
        assert response.status_code == 201

        # Mock FileManagementService to return empty file info
        with patch(
            "chemlit_extractor.api.v1.endpoints.files.FileManagementService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value.__enter__.return_value = mock_service

            # Mock file info and stats
            mock_file_info = MagicMock()
            mock_file_info.sanitized_doi = "10_1000_empty_test"
            mock_file_info.has_files.return_value = False
            mock_file_info.total_size_mb = 0.0
            mock_file_info.get_file_count.return_value = {
                "pdf": 0,
                "html": 0,
                "images": 0,
                "supplementary": 0,
            }
            mock_file_info.get_all_files.return_value = []

            mock_service.get_article_files.return_value = mock_file_info
            mock_service.get_file_stats.return_value = {"last_updated": None}

            response = client.get("/api/v1/files/10.1000/empty.test")
            assert response.status_code == 200

            data = response.json()
            assert data["doi"] == "10.1000/empty.test"
            assert data["has_files"] is False
            assert data["total_files"] == 0
            assert data["total_size_mb"] == 0.0
            assert len(data["files"]) == 0

    def test_list_article_files_with_files(self, client, sample_article_with_files):
        """Test listing files for article with files."""
        doi, directories = sample_article_with_files

        with patch(
            "chemlit_extractor.api.v1.endpoints.files.FileManagementService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value.__enter__.return_value = mock_service

            # Mock file info with files
            mock_file_info = MagicMock()
            mock_file_info.sanitized_doi = "10_1000_file_test"
            mock_file_info.has_files.return_value = True
            mock_file_info.total_size_mb = 1.5
            mock_file_info.get_file_count.return_value = {
                "pdf": 1,
                "html": 1,
                "images": 1,
                "supplementary": 0,
            }
            mock_file_info.get_all_files.return_value = [
                {"filename": "article.pdf", "type": "pdf", "size_mb": 0.5},
                {"filename": "article.html", "type": "html", "size_mb": 0.5},
                {"filename": "figure1.png", "type": "images", "size_mb": 0.5},
            ]

            mock_service.get_article_files.return_value = mock_file_info
            mock_service.get_file_stats.return_value = {
                "last_updated": "2023-01-01T12:00:00"
            }

            response = client.get(f"/api/v1/files/{doi}")
            assert response.status_code == 200

            data = response.json()
            assert data["doi"] == doi
            assert data["has_files"] is True
            assert data["total_files"] == 3
            assert data["file_counts"]["pdf"] == 1
            assert data["file_counts"]["html"] == 1
            assert data["file_counts"]["images"] == 1
            assert len(data["files"]) == 3

    def test_list_article_files_not_found(self, client, temp_file_settings):
        """Test listing files for non-existent article."""
        response = client.get("/api/v1/files/10.1000/nonexistent")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_list_files_by_type(self, client, sample_article_with_files):
        """Test listing files by specific type."""
        doi, directories = sample_article_with_files

        with patch(
            "chemlit_extractor.api.v1.endpoints.files.FileManagementService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value.__enter__.return_value = mock_service

            # Mock file info for specific type
            mock_file_info = MagicMock()
            mock_file_info.files = {
                "pdf": [{"filename": "article.pdf", "size_mb": 0.5}],
                "html": [],
                "images": [],
                "supplementary": [],
            }

            mock_service.get_article_files.return_value = mock_file_info

            response = client.get(f"/api/v1/files/{doi}/files/pdf")
            assert response.status_code == 200

            data = response.json()
            assert data["doi"] == doi
            assert data["file_type"] == "pdf"
            assert data["count"] == 1
            assert len(data["files"]) == 1
            assert data["files"][0]["filename"] == "article.pdf"

    def test_list_files_by_type_empty(self, client, sample_article_with_files):
        """Test listing files by type with no files of that type."""
        doi, directories = sample_article_with_files

        with patch(
            "chemlit_extractor.api.v1.endpoints.files.FileManagementService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value.__enter__.return_value = mock_service

            # Mock file info with no supplementary files
            mock_file_info = MagicMock()
            mock_file_info.files = {
                "pdf": [],
                "html": [],
                "images": [],
                "supplementary": [],
            }

            mock_service.get_article_files.return_value = mock_file_info

            response = client.get(f"/api/v1/files/{doi}/files/supplementary")
            assert response.status_code == 200

            data = response.json()
            assert data["file_type"] == "supplementary"
            assert data["count"] == 0
            assert len(data["files"]) == 0


class TestFileDownloadEndpoints:
    """Test file download endpoints."""

    @patch("chemlit_extractor.api.v1.endpoints.files.FileManagementService")
    def test_download_files_sync_success(
        self, mock_service_class, client, temp_file_settings
    ):
        """Test synchronous file download."""
        # Create article
        article_data = {"doi": "10.1000/download.test", "title": "Download Test"}
        response = client.post("/api/v1/articles/", json=article_data)
        assert response.status_code == 201

        # Setup mock
        mock_service = MagicMock()
        mock_service_class.return_value.__enter__.return_value = mock_service

        from chemlit_extractor.services.file_download import DownloadResult

        mock_results = {
            "https://example.com/test.pdf": DownloadResult(
                success=True,
                file_path=Path("test.pdf"),
                file_size_mb=1.5,
                content_type="application/pdf",
            )
        }
        mock_service.download_from_urls.return_value = mock_results

        # Make download request
        download_data = {"pdf_url": "https://example.com/test.pdf"}

        response = client.post(
            "/api/v1/files/10.1000/download.test/download/sync", json=download_data
        )
        assert response.status_code == 200

        data = response.json()
        assert data["doi"] == "10.1000/download.test"
        assert data["successful_downloads"] == 1
        assert data["failed_downloads"] == 0
        assert "https://example.com/test.pdf" in data["results"]

    @patch("chemlit_extractor.api.v1.endpoints.files.FileManagementService")
    def test_download_files_sync_partial_failure(
        self, mock_service_class, client, temp_file_settings
    ):
        """Test synchronous download with partial failures."""
        # Create article
        article_data = {"doi": "10.1000/partial.test", "title": "Partial Test"}
        response = client.post("/api/v1/articles/", json=article_data)
        assert response.status_code == 201

        # Setup mock with mixed results
        mock_service = MagicMock()
        mock_service_class.return_value.__enter__.return_value = mock_service

        from chemlit_extractor.services.file_download import DownloadResult

        mock_results = {
            "https://example.com/success.pdf": DownloadResult(
                success=True, file_path=Path("success.pdf"), file_size_mb=1.0
            ),
            "https://example.com/fail.pdf": DownloadResult(
                success=False, error="File not found"
            ),
        }
        mock_service.download_from_urls.return_value = mock_results

        # Make download request
        download_data = {
            "pdf_url": "https://example.com/success.pdf",
            "html_url": "https://example.com/fail.pdf",
        }

        response = client.post(
            "/api/v1/files/10.1000/partial.test/download/sync", json=download_data
        )
        assert response.status_code == 200

        data = response.json()
        assert data["successful_downloads"] == 1
        assert data["failed_downloads"] == 1
        assert len(data["results"]) == 2

    def test_download_files_no_urls(self, client, temp_file_settings):
        """Test download request with no URLs."""
        # Create article
        article_data = {"doi": "10.1000/empty.download", "title": "Empty Download"}
        response = client.post("/api/v1/articles/", json=article_data)
        assert response.status_code == 201

        # Make request with no URLs
        download_data = {}

        response = client.post(
            "/api/v1/files/10.1000/empty.download/download/sync", json=download_data
        )
        assert response.status_code == 400
        assert "At least one download URL" in response.json()["detail"]

    def test_download_files_article_not_found(self, client, temp_file_settings):
        """Test download for non-existent article."""
        download_data = {"pdf_url": "https://example.com/test.pdf"}

        response = client.post(
            "/api/v1/files/10.1000/nonexistent/download/sync", json=download_data
        )
        assert response.status_code == 404

    def test_download_files_background(self, client, temp_file_settings):
        """Test background file download."""
        # Create article
        article_data = {"doi": "10.1000/background.test", "title": "Background Test"}
        response = client.post("/api/v1/articles/", json=article_data)
        assert response.status_code == 201

        # Make background download request
        download_data = {
            "pdf_url": "https://example.com/test.pdf",
            "html_url": "https://example.com/test.html",
        }

        response = client.post(
            "/api/v1/files/10.1000/background.test/download", json=download_data
        )
        assert response.status_code == 200

        data = response.json()
        assert data["doi"] == "10.1000/background.test"
        assert data["requested_downloads"] == 2
        assert "Download started" in data["message"]


class TestFileServingEndpoints:
    """Test file serving endpoints."""

    def test_serve_file_success(self, client, sample_article_with_files):
        """Test serving an existing file."""
        doi, directories = sample_article_with_files

        # Mock the file path resolution - patch at the correct import location
        with patch(
            "chemlit_extractor.services.file_utils.get_file_type_directory"
        ) as mock_get_dir:
            mock_get_dir.return_value = directories["pdf"]

            response = client.get(f"/api/v1/files/{doi}/files/pdf/article.pdf")
            assert response.status_code == 200
            assert response.headers["content-type"] == "application/octet-stream"

    def test_serve_file_not_found(self, client, sample_article_with_files):
        """Test serving non-existent file."""
        doi, directories = sample_article_with_files

        # Mock the file path resolution to return empty directory
        with patch(
            "chemlit_extractor.services.file_utils.get_file_type_directory"
        ) as mock_get_dir:
            mock_get_dir.return_value = directories["pdf"]

            response = client.get(f"/api/v1/files/{doi}/files/pdf/nonexistent.pdf")
            assert response.status_code == 404
            assert "not found" in response.json()["detail"]

    def test_serve_file_article_not_found(self, client, temp_file_settings):
        """Test serving file for non-existent article."""
        response = client.get("/api/v1/files/10.1000/nonexistent/files/pdf/test.pdf")
        assert response.status_code == 404


class TestFileDeletionEndpoints:
    """Test file deletion endpoints."""

    def test_delete_article_files(self, client, sample_article_with_files):
        """Test deleting all files for an article."""
        doi, directories = sample_article_with_files

        # Mock file management service
        with patch(
            "chemlit_extractor.api.v1.endpoints.files.FileManagementService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value.__enter__.return_value = mock_service
            mock_service.delete_article_files.return_value = True

            # Delete files
            response = client.delete(f"/api/v1/files/{doi}")
            assert response.status_code == 204

    def test_delete_files_by_type(self, client, sample_article_with_files):
        """Test deleting files of specific type."""
        doi, directories = sample_article_with_files

        # Mock file management service
        with patch(
            "chemlit_extractor.api.v1.endpoints.files.FileManagementService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value.__enter__.return_value = mock_service
            mock_service.delete_file_type.return_value = True

            # Delete only PDF files
            response = client.delete(f"/api/v1/files/{doi}/files/pdf")
            assert response.status_code == 204

    def test_delete_files_article_not_found(self, client, temp_file_settings):
        """Test deleting files for non-existent article."""
        response = client.delete("/api/v1/files/10.1000/nonexistent")
        assert response.status_code == 404


class TestFileStatsEndpoints:
    """Test file statistics endpoints."""

    def test_get_file_stats_with_files(self, client, sample_article_with_files):
        """Test getting file statistics."""
        doi, directories = sample_article_with_files

        # Mock file management service
        with patch(
            "chemlit_extractor.api.v1.endpoints.files.FileManagementService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value.__enter__.return_value = mock_service

            mock_stats = {
                "doi": doi,
                "has_files": True,
                "total_files": 3,
                "file_counts": {"pdf": 1, "html": 1, "images": 1, "supplementary": 0},
                "directory_exists": True,
                "total_size_mb": 1.5,
                "last_updated": "2023-01-01T12:00:00",
            }
            mock_service.get_file_stats.return_value = mock_stats

            response = client.get(f"/api/v1/files/{doi}/stats")
            assert response.status_code == 200

            data = response.json()
            assert data["doi"] == doi
            assert data["has_files"] is True
            assert data["total_files"] == 3
            assert data["file_counts"]["pdf"] == 1
            assert data["file_counts"]["html"] == 1
            assert data["file_counts"]["images"] == 1
            assert data["directory_exists"] is True

    def test_get_file_stats_empty(self, client, temp_file_settings):
        """Test getting stats for article with no files."""
        # Create article without files
        article_data = {"doi": "10.1000/stats.empty", "title": "Stats Empty"}
        response = client.post("/api/v1/articles/", json=article_data)
        assert response.status_code == 201

        # Mock file management service
        with patch(
            "chemlit_extractor.api.v1.endpoints.files.FileManagementService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value.__enter__.return_value = mock_service

            mock_stats = {
                "doi": "10.1000/stats.empty",
                "has_files": False,
                "total_files": 0,
                "total_size_mb": 0.0,
                "directory_exists": False,
                "last_updated": None,
            }
            mock_service.get_file_stats.return_value = mock_stats

            response = client.get("/api/v1/files/10.1000/stats.empty/stats")
            assert response.status_code == 200

            data = response.json()
            assert data["has_files"] is False
            assert data["total_files"] == 0
            assert data["total_size_mb"] == 0.0

    def test_get_file_stats_article_not_found(self, client, temp_file_settings):
        """Test getting stats for non-existent article."""
        response = client.get("/api/v1/files/10.1000/nonexistent/stats")
        assert response.status_code == 404


class TestFileAPIIntegration:
    """Test file API integration with article workflow."""

    @patch("chemlit_extractor.api.v1.endpoints.files.FileManagementService")
    def test_complete_file_workflow(
        self, mock_service_class, client, temp_file_settings
    ):
        """Test complete file management workflow."""
        # Setup mock
        mock_service = MagicMock()
        mock_service_class.return_value.__enter__.return_value = mock_service

        from chemlit_extractor.services.file_download import DownloadResult

        mock_results = {
            "https://example.com/article.pdf": DownloadResult(
                success=True, file_path=Path("article.pdf"), file_size_mb=2.5
            )
        }
        mock_service.download_from_urls.return_value = mock_results

        # Mock file info and stats
        mock_file_info = MagicMock()
        mock_file_info.sanitized_doi = "10_1000_workflow_test"
        mock_file_info.has_files.return_value = True
        mock_file_info.total_size_mb = 2.5
        mock_file_info.get_file_count.return_value = {
            "pdf": 1,
            "html": 0,
            "images": 0,
            "supplementary": 0,
        }
        mock_file_info.get_all_files.return_value = [
            {"filename": "article.pdf", "type": "pdf", "size_mb": 2.5}
        ]

        mock_service.get_article_files.return_value = mock_file_info
        mock_service.get_file_stats.return_value = {
            "doi": "10.1000/workflow.test",
            "has_files": True,
            "total_files": 1,
            "total_size_mb": 2.5,
            "directory_exists": True,
            "last_updated": "2023-01-01T12:00:00",
        }
        mock_service.delete_article_files.return_value = True

        # 1. Create article
        article_data = {"doi": "10.1000/workflow.test", "title": "Workflow Test"}
        response = client.post("/api/v1/articles/", json=article_data)
        assert response.status_code == 201

        # 2. Download files
        download_data = {"pdf_url": "https://example.com/article.pdf"}
        response = client.post(
            "/api/v1/files/10.1000/workflow.test/download/sync", json=download_data
        )
        assert response.status_code == 200

        # 3. List files (would show downloaded files in real scenario)
        response = client.get("/api/v1/files/10.1000/workflow.test")
        assert response.status_code == 200

        # 4. Get stats
        response = client.get("/api/v1/files/10.1000/workflow.test/stats")
        assert response.status_code == 200

        # 5. Clean up
        response = client.delete("/api/v1/files/10.1000/workflow.test")
        assert response.status_code == 204
