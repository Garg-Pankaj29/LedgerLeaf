"""AI status probing service. Strictly checks local AI endpoint with zero faking."""

import httpx
from typing import Dict, Any, Optional
from backend.app.config import get_settings
from backend.app.schemas.common import AIStatusResponse


class AIService:
    """Service to probe and interact with local open-weight models."""

    def __init__(self) -> None:
        self.settings = get_settings()

    async def check_status(self) -> AIStatusResponse:
        """
        Probe the configured local AI server (LM Studio, Ollama, etc.).
        Reports honest connectivity status without mocking or pretending.
        """
        provider = self.settings.ai_provider
        base_url = self.settings.ai_base_url.rstrip("/")
        timeout = min(self.settings.ai_timeout_seconds, 5.0)  # fast probe

        if provider == "none":
            return AIStatusResponse(
                status="disconnected",
                provider="none",
                model=None,
                message="AI provider is disabled in configuration.",
                endpoint=None,
                details={},
            )

        probe_url = f"{base_url}/models" if provider == "lm_studio" else f"{base_url}/api/tags"

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(probe_url)
                if response.status_code == 200:
                    data = response.json()
                    loaded_model: Optional[str] = None

                    if provider == "lm_studio" and "data" in data and len(data["data"]) > 0:
                        loaded_model = data["data"][0].get("id")
                    elif provider == "ollama" and "models" in data and len(data["models"]) > 0:
                        loaded_model = data["models"][0].get("name")

                    return AIStatusResponse(
                        status="connected",
                        provider=provider,
                        model=loaded_model or self.settings.ai_model_name,
                        message=f"Local {provider} server is connected and responsive.",
                        endpoint=base_url,
                        details={"models_available": [m.get("id", m.get("name")) for m in data.get("data", data.get("models", []))]},
                    )
                else:
                    return AIStatusResponse(
                        status="error",
                        provider=provider,
                        model=None,
                        message=f"Local AI server returned status code {response.status_code}.",
                        endpoint=base_url,
                        details={"status_code": response.status_code},
                    )
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError) as exc:
            return AIStatusResponse(
                status="disconnected",
                provider=provider,
                model=None,
                message=(
                    f"No local AI server found at {base_url}. "
                    f"Start LM Studio or Ollama locally to enable inference."
                ),
                endpoint=base_url,
                details={"error_type": exc.__class__.__name__},
            )
