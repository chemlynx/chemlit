#!/usr/bin/env python3
"""Development server script for ChemLit Extractor."""
import os
import sys
from pathlib import Path

# Add src to Python path
project_root = Path(__file__).parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

# Change to project root to find .env file
os.chdir(project_root)


def main():
    """Run the development server."""
    try:
        import uvicorn

        from chemlit_extractor.core.config import settings
        from chemlit_extractor.main import app

        print("🚀 Starting ChemLit Extractor development server...")
        print(f"📁 Project root: {project_root}")
        print(f"🔧 Debug mode: {settings.debug}")
        print(f"📊 Database: {settings.database_host}:{settings.database_port}")
        print()
        print("📖 API Documentation: http://localhost:8000/docs")
        print("📈 Database Stats: http://localhost:8000/api/v1/stats")
        print("🔍 Search Articles: http://localhost:8000/api/v1/articles")
        print()
        print("Press Ctrl+C to stop the server")
        print("-" * 50)

        uvicorn.run(
            "chemlit_extractor.main:app",
            host="127.0.0.1",
            port=8000,
            reload=True,  # Enable auto-reload for development
            log_level="info",
        )

    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("💡 Make sure you've installed all dependencies:")
        print("   uv add fastapi uvicorn sqlalchemy psycopg pydantic httpx")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Failed to start server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
