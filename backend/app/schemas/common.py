"""Common API response schemas."""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health status response."""
    status: str = Field(..., description="Application operational status, e.g. 'ok'")
    database: str = Field(..., description="Database connection status, e.g. 'connected'")
    version: str = Field(..., description="Application semantic version")
    timestamp: datetime = Field(..., description="UTC server timestamp")


class AIStatusResponse(BaseModel):
    """AI engine status response. Reflects honest local connectivity."""
    status: str = Field(
        ...,
        description="Connectivity status: 'connected', 'disconnected', or 'error'",
    )
    provider: str = Field(..., description="Configured AI provider, e.g. 'lm_studio' or 'ollama'")
    model: Optional[str] = Field(None, description="Active model name loaded in local engine")
    message: str = Field(..., description="Human-readable status summary")
    endpoint: Optional[str] = Field(None, description="AI endpoint URL")
    details: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Diagnostic details")


class ValidationResultResponse(BaseModel):
    """Deterministic validation diagnostics and approval eligibility."""
    is_valid: bool = Field(..., description="True if no blocking issues exist")
    can_approve: bool = Field(..., description="Whether document is eligible for approval gate")
    issues: List[str] = Field(default_factory=list, description="Blocking validation errors")
    warnings: List[str] = Field(default_factory=list, description="Non-blocking informational warnings")
    suggested_category: Optional[str] = Field(None, description="Rule-based suggested category if missing")
    edits_count: int = Field(0, description="Number of user-edited fields")
