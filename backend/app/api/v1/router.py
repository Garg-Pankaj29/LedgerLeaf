"""V1 API router combining health, AI status, documents, and ledger endpoints."""

from fastapi import APIRouter
from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.ai import router as ai_router
from backend.app.api.v1.documents import router as documents_router
from backend.app.api.v1.ledger import router as ledger_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health_router)
api_v1_router.include_router(ai_router)
api_v1_router.include_router(documents_router)
api_v1_router.include_router(ledger_router)
