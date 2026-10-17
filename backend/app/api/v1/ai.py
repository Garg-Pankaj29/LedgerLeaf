"""AI subsystem endpoints for status, connection testing, and model discovery."""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException
from backend.app.schemas.common import AIStatusResponse
from backend.app.services.local_ai import LocalAIService, LocalAIError

router = APIRouter(prefix="/ai", tags=["AI"])


def get_ai_service() -> LocalAIService:
    return LocalAIService()


@router.get("/status", response_model=AIStatusResponse)
async def get_ai_status(
    ai_service: LocalAIService = Depends(get_ai_service),
) -> AIStatusResponse:
    """
    Check the status of the local open-weight AI backend.
    Returns honest connectivity status (never mock-connected).
    """
    return await ai_service.get_status()


@router.post("/test-connection")
async def test_ai_connection(
    ai_service: LocalAIService = Depends(get_ai_service),
) -> Dict[str, Any]:
    """
    Test real connection to LM Studio / local OpenAI-compatible server.
    Returns connection status, server URL, measured latency, and available models.
    """
    return await ai_service.test_connection()


@router.get("/models")
async def list_ai_models(
    ai_service: LocalAIService = Depends(get_ai_service),
) -> Dict[str, Any]:
    """
    List models currently available on the local LM Studio server.
    """
    try:
        models = await ai_service.get_models()
        return {
            "status": "connected",
            "models": models,
            "count": len(models),
        }
    except LocalAIError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Local AI server is not reachable: {str(exc)}",
        )
