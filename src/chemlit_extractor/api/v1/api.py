"""API v1 router setup."""

from fastapi import APIRouter

from chemlit_extractor.api.v1.endpoints import (
    articles,
    authors,
    compounds,
    files,
    register,
    stats,
)

api_router = APIRouter()

api_router.include_router(articles.router, prefix="/articles", tags=["articles"])
api_router.include_router(authors.router, prefix="/authors", tags=["authors"])
api_router.include_router(compounds.router, prefix="/compounds", tags=["compounds"])
api_router.include_router(files.router, prefix="/files", tags=["files"])
api_router.include_router(stats.router, prefix="/stats", tags=["stats"])
api_router.include_router(register.router, prefix="/register", tags=["register"])
api_router.include_router(register.router, prefix="/register", tags=["register"])
