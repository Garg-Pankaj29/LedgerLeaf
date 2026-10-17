"""Pydantic schemas for Document."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from backend.app.models.document import ProcessingStatus, ReviewStatus
from backend.app.schemas.extraction import ExtractionResultResponse


class DocumentBase(BaseModel):
    original_filename: str = Field(..., max_length=255)
    file_type: str = Field(..., max_length=100)
    file_size: int = Field(..., ge=0)


class DocumentCreate(DocumentBase):
    stored_filename: str
    sha256_hash: str
    extracted_text: Optional[str] = None


class DocumentUpdate(BaseModel):
    processing_status: Optional[ProcessingStatus] = None
    review_status: Optional[ReviewStatus] = None
    extracted_text: Optional[str] = None
    error_details: Optional[str] = None


class DocumentResponse(DocumentBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    stored_filename: str
    sha256_hash: str
    processing_status: ProcessingStatus
    review_status: ReviewStatus
    extracted_text: Optional[str] = None
    error_details: Optional[str] = None
    is_duplicate: bool = False
    duplicate_of_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    extractions: List[ExtractionResultResponse] = Field(default_factory=list)
