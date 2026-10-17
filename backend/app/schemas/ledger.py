"""Pydantic schemas for LedgerEntry and Ledger analytics."""

from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from backend.app.schemas.money import from_minor_units


class LedgerEntryBase(BaseModel):
    vendor: str = Field(..., max_length=255)
    document_number: Optional[str] = Field(None, max_length=100)
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD")
    currency: str = Field(..., min_length=3, max_length=3)
    # Stored in integer minor units (paise/cents)
    subtotal: Optional[int] = None
    tax: Optional[int] = None
    total: int = Field(..., description="Total amount in integer minor units")
    category: str = Field(..., max_length=100)
    edits_count: int = Field(0, ge=0)
    is_demo: bool = False


class LedgerEntryCreate(LedgerEntryBase):
    document_id: Optional[str] = None


class DemoEntryCreate(BaseModel):
    vendor: str = Field(..., max_length=255)
    document_number: Optional[str] = Field(None, max_length=100)
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    currency: str = Field(..., min_length=3, max_length=3)
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: float
    category: str = Field(..., max_length=100)
    edits_count: int = 0


class LedgerEntryResponse(LedgerEntryBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: Optional[str] = None
    approval_timestamp: datetime
    created_at: datetime

    @property
    def total_decimal(self) -> float:
        dec = from_minor_units(self.total, self.currency)
        return float(dec) if dec is not None else 0.0

    @property
    def formatted_total(self) -> str:
        """Formatted total for convenience display."""
        dec = from_minor_units(self.total, self.currency)
        return f"{self.currency} {dec:.2f}" if dec is not None else ""


class CurrencySummary(BaseModel):
    currency: str
    count: int
    total: float  # Total sum in major units (e.g. 12.50)
    minor_total: int
    categories: Dict[str, float]  # Breakdown by category: {"Software": 10.00, ...}


class LedgerSummaryResponse(BaseModel):
    """Multi-currency ledger summary. Currencies are strictly kept isolated."""
    total_records: int
    currencies: Dict[str, CurrencySummary]
