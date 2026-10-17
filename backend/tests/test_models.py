"""Tests for database models, UUID generation, monetary minor units, and relationships."""

import uuid
from decimal import Decimal
from sqlalchemy.orm import Session
from backend.app.models.document import Document, ProcessingStatus, ReviewStatus
from backend.app.models.extraction import ExtractionResult, ExtractionMethod
from backend.app.models.provenance import FieldProvenance, ExtractionSource, ValidationStatus
from backend.app.models.ledger import LedgerEntry
from backend.app.schemas.money import to_minor_units, from_minor_units, format_currency_amount


def test_monetary_minor_unit_conversions():
    """Verify precision handling for integer minor units (cents, paise)."""
    # USD: $9.72 -> 972 cents
    assert to_minor_units("9.72", "USD") == 972
    assert to_minor_units(9.72, "USD") == 972
    assert from_minor_units(972, "USD") == Decimal("9.72")
    assert format_currency_amount(972, "USD") == "9.72"

    # EUR: €1,200.00 -> 120000 cents
    assert to_minor_units("1,200.00", "EUR") == 120000
    assert from_minor_units(120000, "EUR") == Decimal("1200.00")

    # INR: ₹640.00 -> 64000 paise
    assert to_minor_units("640.00", "INR") == 64000
    assert from_minor_units(64000, "INR") == Decimal("640.00")

    # JPY: ¥5000 -> 5000 (0 decimals)
    assert to_minor_units(5000, "JPY") == 5000
    assert from_minor_units(5000, "JPY") == Decimal("5000")

    # Missing fields should return None without inventing values
    assert to_minor_units(None) is None
    assert to_minor_units("") is None
    assert from_minor_units(None) is None
    assert format_currency_amount(None) is None


def test_create_document_and_uuid(db_session: Session):
    """Verify Document model auto-assigns UUID and default statuses."""
    doc = Document(
        original_filename="receipt_coffee.pdf",
        stored_filename=f"{uuid.uuid4().hex}.pdf",
        file_type="application/pdf",
        file_size=1024,
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    assert doc.id is not None
    assert len(doc.id) == 36  # Valid UUID string
    assert doc.processing_status == ProcessingStatus.PENDING
    assert doc.review_status == ReviewStatus.UNREVIEWED
    assert doc.created_at is not None
    assert doc.error_details is None


def test_create_extraction_result_and_provenance(db_session: Session):
    """Verify ExtractionResult and FieldProvenance persistence with minor units and snippets."""
    doc = Document(
        original_filename="cafe_receipt.txt",
        stored_filename="cafe.txt",
        file_type="text/plain",
        file_size=150,
        sha256_hash="abc123hash",
    )
    db_session.add(doc)
    db_session.commit()

    extraction = ExtractionResult(
        document_id=doc.id,
        vendor="Juniper & Oak Coffee",
        invoice_number="R-20418",
        date="2026-10-03",
        currency="USD",
        subtotal=to_minor_units("9.00", "USD"),  # 900 cents
        tax=to_minor_units("0.72", "USD"),       # 72 cents
        total=to_minor_units("9.72", "USD"),     # 972 cents
        category="Meals",
        extraction_method=ExtractionMethod.RULE_BASED,
        validation_issues=[],
    )
    db_session.add(extraction)
    db_session.commit()
    db_session.refresh(extraction)

    assert extraction.subtotal == 900
    assert extraction.tax == 72
    assert extraction.total == 972

    # Add field provenance records
    prov_vendor = FieldProvenance(
        extraction_result_id=extraction.id,
        field_name="vendor",
        extracted_value="Juniper & Oak Coffee",
        source_snippet="Juniper & Oak Coffee",
        start_offset=0,
        end_offset=20,
        extraction_source=ExtractionSource.RULE_BASED,
        is_user_edited=False,
        validation_status=ValidationStatus.VALID,
    )
    prov_total = FieldProvenance(
        extraction_result_id=extraction.id,
        field_name="total",
        extracted_value="9.72",
        source_snippet="Total: $9.72",
        start_offset=95,
        end_offset=107,
        extraction_source=ExtractionSource.RULE_BASED,
        is_user_edited=False,
        validation_status=ValidationStatus.VALID,
    )
    db_session.add_all([prov_vendor, prov_total])
    db_session.commit()

    db_session.refresh(extraction)
    assert len(extraction.field_provenances) == 2
    assert extraction.field_provenances[0].field_name in ("vendor", "total")


def test_missing_fields_without_inventing_values(db_session: Session):
    """Verify missing fields (like missing subtotal/tax in taxi receipt) remain None."""
    doc = Document(
        original_filename="taxi_slip.txt",
        stored_filename="taxi.txt",
        file_type="text/plain",
        file_size=60,
        sha256_hash="def456hash",
    )
    db_session.add(doc)
    db_session.commit()

    extraction = ExtractionResult(
        document_id=doc.id,
        vendor="Metro Cab Services",
        invoice_number="MC-88120",
        date=None,  # Missing date in document
        currency="INR",
        subtotal=None,  # No subtotal
        tax=None,       # No tax
        total=to_minor_units("640.00", "INR"),  # 64000 paise
        category="Travel",
        validation_issues=["Date is missing.", "Subtotal or tax is missing."],
    )
    db_session.add(extraction)
    db_session.commit()
    db_session.refresh(extraction)

    assert extraction.date is None
    assert extraction.subtotal is None
    assert extraction.tax is None
    assert extraction.total == 64000
    assert len(extraction.validation_issues) == 2


def test_create_ledger_entry(db_session: Session):
    """Verify LedgerEntry approval and persistence with integer minor units."""
    entry = LedgerEntry(
        vendor="Juniper & Oak Coffee",
        document_number="R-20418",
        date="2026-10-03",
        currency="USD",
        subtotal=900,
        tax=72,
        total=972,
        category="Meals",
        edits_count=0,
        is_demo=False,
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)

    assert entry.id is not None
    assert entry.vendor == "Juniper & Oak Coffee"
    assert entry.total == 972
    assert entry.currency == "USD"
    assert entry.approval_timestamp is not None
