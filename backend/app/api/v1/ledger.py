"""Ledger endpoints: listing approved records, multi-currency summary, and CSV export."""

import csv
import io
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from backend.app.database import get_db
from backend.app.models.document import Document, ProcessingStatus, ReviewStatus
from backend.app.models.ledger import LedgerEntry
from backend.app.schemas.ledger import (
    LedgerEntryResponse,
    LedgerSummaryResponse,
    CurrencySummary,
    DemoEntryCreate,
)
from backend.app.schemas.money import from_minor_units, to_minor_units

router = APIRouter(prefix="/ledger", tags=["Ledger"])


@router.get("", response_model=List[LedgerEntryResponse])
def get_ledger_entries(
    skip: int = 0,
    limit: int = 200,
    db: Session = Depends(get_db),
) -> List[LedgerEntryResponse]:
    """Retrieve all approved ledger records, ordered by date descending."""
    stmt = select(LedgerEntry).order_by(LedgerEntry.date.desc(), LedgerEntry.created_at.desc()).offset(skip).limit(limit)
    entries = db.execute(stmt).scalars().all()
    return [LedgerEntryResponse.model_validate(e) for e in entries]


@router.get("/summary", response_model=LedgerSummaryResponse)
def get_ledger_summary(
    db: Session = Depends(get_db),
) -> LedgerSummaryResponse:
    """
    Compute multi-currency totals and category distributions.
    Strictly keeps currencies separated — never merges different currencies into one meaningless sum.
    """
    stmt = select(LedgerEntry).order_by(LedgerEntry.date.desc())
    entries = db.execute(stmt).scalars().all()

    by_curr: Dict[str, Dict[str, Any]] = {}

    for entry in entries:
        curr = (entry.currency or "USD").upper()
        if curr not in by_curr:
            by_curr[curr] = {
                "currency": curr,
                "count": 0,
                "minor_total": 0,
                "categories_minor": {},
            }

        rec = by_curr[curr]
        rec["count"] += 1
        rec["minor_total"] += entry.total

        cat = entry.category or "Other"
        rec["categories_minor"][cat] = rec["categories_minor"].get(cat, 0) + entry.total

    # Format into response models with Decimal major units
    curr_summaries: Dict[str, CurrencySummary] = {}
    for curr, rec in by_curr.items():
        total_dec = from_minor_units(rec["minor_total"], curr)
        cats_dec = {
            c: float(from_minor_units(amt, curr) or 0.0)
            for c, amt in rec["categories_minor"].items()
        }
        curr_summaries[curr] = CurrencySummary(
            currency=curr,
            count=rec["count"],
            total=float(total_dec or 0.0),
            minor_total=rec["minor_total"],
            categories=cats_dec,
        )

    return LedgerSummaryResponse(
        total_records=len(entries),
        currencies=curr_summaries,
    )


@router.get("/export.csv")
def export_ledger_csv(
    db: Session = Depends(get_db),
) -> Response:
    """
    Export all approved ledger entries as RFC 4180 compliant CSV.
    Escapes quotes, commas, and formatting properly with explicit currency and trust metrics.
    """
    stmt = select(LedgerEntry).order_by(LedgerEntry.date.desc(), LedgerEntry.created_at.desc())
    entries = db.execute(stmt).scalars().all()

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    # Header
    writer.writerow([
        "id",
        "vendor",
        "document_number",
        "date",
        "currency",
        "subtotal",
        "tax",
        "total",
        "category",
        "trust",
        "approval_timestamp",
        "source",
    ])

    for entry in entries:
        curr = (entry.currency or "USD").upper()
        s_dec = from_minor_units(entry.subtotal, curr) if entry.subtotal is not None else ""
        t_dec = from_minor_units(entry.tax, curr) if entry.tax is not None else ""
        tot_dec = from_minor_units(entry.total, curr)

        trust = f"{entry.edits_count} fields corrected by you" if entry.edits_count > 0 else "reviewed as extracted"
        source = "demo" if entry.is_demo else "user"

        writer.writerow([
            entry.id,
            entry.vendor,
            entry.document_number or "",
            entry.date,
            curr,
            f"{s_dec:.2f}" if s_dec != "" else "",
            f"{t_dec:.2f}" if t_dec != "" else "",
            f"{tot_dec:.2f}" if tot_dec is not None else "0.00",
            entry.category,
            trust,
            entry.approval_timestamp.isoformat(),
            source,
        ])

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="ledgerleaf_approved.csv"',
        },
    )


@router.delete("/{entry_id}", status_code=status.HTTP_200_OK)
def delete_ledger_entry(
    entry_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """
    Delete a ledger entry.
    Restores the linked document to 'needs_review' status so it can be re-evaluated.
    """
    entry = db.get(LedgerEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Ledger entry '{entry_id}' not found.")

    doc_id = entry.document_id
    if doc_id:
        doc = db.get(Document, doc_id)
        if doc:
            doc.processing_status = ProcessingStatus.NEEDS_REVIEW
            doc.review_status = ReviewStatus.UNREVIEWED

    db.delete(entry)
    db.commit()

    return {
        "status": "success",
        "message": f"Ledger entry '{entry_id}' deleted successfully.",
    }


@router.post("/demo-sample", response_model=LedgerEntryResponse, status_code=status.HTTP_201_CREATED)
def add_demo_sample_to_ledger(
    payload: DemoEntryCreate,
    db: Session = Depends(get_db),
) -> LedgerEntryResponse:
    """
    Explicitly add a synthetic demo sample entry to the ledger.
    Guarantees demo records are tagged with is_demo=True and source='demo'.
    """
    curr = payload.currency.upper()
    entry = LedgerEntry(
        document_id=None,
        vendor=payload.vendor,
        document_number=payload.document_number,
        date=payload.date,
        currency=curr,
        subtotal=to_minor_units(payload.subtotal, curr) if payload.subtotal is not None else None,
        tax=to_minor_units(payload.tax, curr) if payload.tax is not None else None,
        total=to_minor_units(payload.total, curr) or 0,
        category=payload.category,
        approval_timestamp=datetime.now(timezone.utc),
        edits_count=payload.edits_count,
        is_demo=True,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return LedgerEntryResponse.model_validate(entry)


@router.post("/seed-demo-samples", status_code=status.HTTP_201_CREATED)
def seed_demo_samples(
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Seed 3 standard demo samples into the ledger with multiple currencies (USD, EUR, INR)
    for quick demonstration and testing of multi-currency summaries and CSV exports.
    """
    samples = [
        {
            "vendor": "Juniper & Oak Coffee",
            "document_number": "R-20418",
            "date": "2026-10-03",
            "currency": "USD",
            "subtotal": 900,
            "tax": 72,
            "total": 972,
            "category": "Meals",
            "edits_count": 0,
        },
        {
            "vendor": "Northfield Type Foundry",
            "document_number": "INV-3307",
            "date": "2026-09-21",
            "currency": "EUR",
            "subtotal": 120000,
            "tax": 22800,
            "total": 142800,
            "category": "Software",
            "edits_count": 1,
        },
        {
            "vendor": "Metro Cab Services",
            "document_number": "MC-88120",
            "date": "2026-10-01",
            "currency": "INR",
            "subtotal": None,
            "tax": None,
            "total": 64000,
            "category": "Travel",
            "edits_count": 0,
        },
    ]

    added = []
    for s in samples:
        entry = LedgerEntry(
            document_id=None,
            vendor=s["vendor"],
            document_number=s["document_number"],
            date=s["date"],
            currency=s["currency"],
            subtotal=s["subtotal"],
            tax=s["tax"],
            total=s["total"],
            category=s["category"],
            approval_timestamp=datetime.now(timezone.utc),
            edits_count=s["edits_count"],
            is_demo=True,
        )
        db.add(entry)
        added.append(s["vendor"])

    db.commit()
    return {
        "status": "success",
        "message": f"Successfully loaded {len(added)} demo records into the ledger.",
        "samples": added,
    }
