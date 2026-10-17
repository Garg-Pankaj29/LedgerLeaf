"""Pydantic schemas for FieldProvenance."""

from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field
from backend.app.models.provenance import ExtractionSource, ValidationStatus


class FieldProvenanceBase(BaseModel):
    field_name: str = Field(..., max_length=50)
    extracted_value: Optional[str] = None
    source_snippet: Optional[str] = None
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None
    bounding_box: Optional[Dict[str, Any]] = None
    extraction_source: ExtractionSource = ExtractionSource.RULE_BASED
    is_user_edited: bool = False
    user_value: Optional[str] = None
    validation_status: ValidationStatus = ValidationStatus.VALID


class FieldProvenanceCreate(FieldProvenanceBase):
    pass


class FieldProvenanceUpdate(BaseModel):
    user_value: Optional[str] = None
    is_user_edited: bool = True
    validation_status: Optional[ValidationStatus] = None


class FieldProvenanceResponse(FieldProvenanceBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    extraction_result_id: str
    created_at: datetime
    updated_at: datetime
