"""Main FastAPI application entry point."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from backend.app.api.v1.router import api_v1_router
from backend.app.config import get_settings
from backend.app.database import init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager: auto-initialize database and directories on startup."""
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    description="Your finances. Your files. Your AI. Local-first financial document processing backend.",
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

from fastapi.responses import RedirectResponse

# Configure Cross-Origin Resource Sharing (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(api_v1_router)

# Statically serve frontend assets if available
frontend_dir = Path("frontend")
if frontend_dir.exists():
    app.mount("/app", StaticFiles(directory="frontend", html=True), name="frontend")


from fastapi import Request
from fastapi.responses import RedirectResponse


@app.get("/", tags=["Root"])
def root(request: Request):
    """Serve metadata for API clients or redirect browser requests to the LedgerLeaf web UI."""
    accept = request.headers.get("accept", "")
    if "text/html" in accept and "application/json" not in accept:
        return RedirectResponse(url="/app/")
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs",
        "ui": "/app/",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host=settings.host, port=settings.port, reload=settings.debug)
