"""API v1 router setup."""

from fastapi import APIRouter

from chemlit_extractor.api.v1.endpoints import (
    articles,
    authors,
    compounds,
    files,
    stats,
)

api_router = APIRouter()

# Include endpoint routers
api_router.include_router(
    stats.router,
    prefix="/stats",
    tags=["statistics"],
)

api_router.include_router(
    articles.router,
    prefix="/articles",
    tags=["articles"],
)

api_router.include_router(
    authors.router,
    prefix="/authors",
    tags=["authors"],
)

api_router.include_router(
    compounds.router,
    prefix="/compounds",
    tags=["compounds"],
)

api_router.include_router(
    files.router,
    prefix="/files",
    tags=["files"],
)
