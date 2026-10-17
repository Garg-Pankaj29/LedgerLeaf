"""Pydantic schemas for ExtractionResult."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from backend.app.models.extraction import ExtractionMethod
from backend.app.schemas.provenance import FieldProvenanceResponse
from backend.app.schemas.money import from_minor_units


class LineItem(BaseModel):
    description: str
    quantity: Optional[float] = 1.0
    unit_price: Optional[float] = None
    amount: Optional[float] = None


class ExtractionResultBase(BaseModel):
    vendor: Optional[str] = None
    invoice_number: Optional[str] = None
    date: Optional[str] = None
    due_date: Optional[str] = None
    currency: Optional[str] = Field(None, max_length=3)
    # Monetary values in integer minor units (paise/cents)
    subtotal: Optional[int] = None
    tax: Optional[int] = None
    total: Optional[int] = None
    category: Optional[str] = None
    description: Optional[str] = None
    line_items: Optional[List[Dict[str, Any]]] = None
    extraction_method: ExtractionMethod = ExtractionMethod.RULE_BASED
    model_name: Optional[str] = None
    validation_issues: Optional[List[str]] = None


class ExtractionResultCreate(ExtractionResultBase):
    document_id: str


class ExtractionResultUpdate(BaseModel):
    """Schema for editing extracted fields before approval."""
    vendor: Optional[str] = None
    invoice_number: Optional[str] = None
    date: Optional[str] = None
    due_date: Optional[str] = None
    currency: Optional[str] = None
    subtotal: Optional[float] = None  # Accepts major unit decimal (e.g. 9.00)
    tax: Optional[float] = None       # Accepts major unit decimal (e.g. 0.72)
    total: Optional[float] = None     # Accepts major unit decimal (e.g. 9.72)
    category: Optional[str] = None
    description: Optional[str] = None
    line_items: Optional[List[Dict[str, Any]]] = None


class ExtractionResultResponse(ExtractionResultBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    created_at: datetime
    updated_at: datetime
    field_provenances: List[FieldProvenanceResponse] = Field(default_factory=list)

    @property
    def total_decimal(self) -> Optional[float]:
        dec = from_minor_units(self.total, self.currency or "USD")
        return float(dec) if dec is not None else None

    @property
    def subtotal_decimal(self) -> Optional[float]:
        dec = from_minor_units(self.subtotal, self.currency or "USD")
        return float(dec) if dec is not None else None

    @property
    def tax_decimal(self) -> Optional[float]:
        dec = from_minor_units(self.tax, self.currency or "USD")
        return float(dec) if dec is not None else None
