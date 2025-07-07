"""Main FastAPI application module for ChemLit Extractor.

This module sets up the FastAPI application with middleware, routers,
and lifespan management for extracting chemical data from journal articles.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from chemlit_extractor.api.v1.api import api_router, ui_router
from chemlit_extractor.core.config import settings
from chemlit_extractor.database.connection import create_tables
from chemlit_extractor.services.article_service import get_service_container


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Manage application lifespan with service container."""
    # Startup
    create_tables()
    container = get_service_container()

    print("🚀 Starting ChemLit Extractor...")
    print(f"📊 Database: {settings.database_url}")
    print("📝 Documentation: http://127.0.0.1:8000/docs")
    print("🔧 Services initialized")
    print("✅ ChemLit Extractor started successfully!")

    yield

    # Shutdown
    container.close()
    print("🔚 Services cleaned up")
    print("👋 Shutting down ChemLit Extractor...")


# Create FastAPI app with updated lifespan
app = FastAPI(
    title="ChemLit Extractor",
    description="Web interface for extracting chemical data from journal articles",
    version="0.1.0",
    openapi_url="/api/v1/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    debug=settings.debug,
    lifespan=lifespan,
)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files if static directory exists
static_dir = Path(__file__).parent.parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include routers
app.include_router(api_router, prefix="/api/v1")
app.include_router(ui_router)  # UI routes at root level


@app.get("/health", response_model=dict[str, str])
async def health_check() -> dict[str, str]:
    """Check application health status.

    Returns:
        dict[str, str]: Health status information including service name
            and version.

    Examples:
        >>> response = await health_check()
        >>> assert response["status"] == "healthy"
    """
    return {
        "status": "healthy",
        "service": "ChemLit Extractor",
        "version": "0.1.0",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "chemlit_extractor.main:app",
        host="127.0.0.1",
        port=8000,
        reload=settings.debug,
        log_level="info",
    )
