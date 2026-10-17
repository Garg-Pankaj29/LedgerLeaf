"""Comprehensive tests for Phase 3: Human review, editing, validation rules, approval gate, and persistent ledger."""

import io
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from backend.app.services.local_ai import LocalAIService, AIStructuredOutput
from backend.app.api.v1.documents import get_ai_service


def test_full_human_review_editing_and_approval_workflow(client: TestClient):
    """
    Test the full workflow:
    1. Upload a receipt
    2. Extract with AI (initially missing category and bad math)
    3. Retrieve extraction and check validation issues
    4. Verify approval is blocked when issues exist
    5. Edit fields (correct math and assign category)
    6. Verify edits are recorded in FieldProvenance
    7. Validate passes
    8. Approve and verify persistent LedgerEntry in SQLite
    9. Verify multi-currency ledger summary
    10. Verify RFC 4180 CSV export
    """
    receipt_text = (
        "Northfield Type Foundry\n"
        "Invoice No: INV-3307\n"
        "Date: 2026-09-21\n"
        "Licence: font software, 3 seats\n"
        "Subtotal: €1,200.00\n"
        "VAT (19%): €228.00\n"
        "Total: €1,438.00\n"
    )

    # 1. Upload
    up_res = client.post(
        "/api/v1/documents",
        files={"file": ("northfield.txt", io.BytesIO(receipt_text.encode("utf-8")), "text/plain")},
    )
    assert up_res.status_code == 201
    doc_id = up_res.json()["id"]

    # 2. Process with AI returning a math mismatch and missing category
    # Subtotal 1200 + tax 228 = 1428, but total is 1438 (off by 10)
    mock_ai = AsyncMock(spec=LocalAIService)
    mock_ai.extract_structured_data.return_value = (
        AIStructuredOutput(
            vendor="Northfield Type Foundry",
            document_number="INV-3307",
            date="2026-09-21",
            currency="EUR",
            subtotal=1200.00,
            tax=228.00,
            total=1438.00,  # Bad math in document
            category=None,    # Missing category
            description="Font licence",
            line_items=[],
            uncertain_fields=[],
        ),
        "meta-llama-3.1-8b-instruct",
        "llm",
    )
    client.app.dependency_overrides[get_ai_service] = lambda: mock_ai

    try:
        proc_res = client.post(f"/api/v1/documents/{doc_id}/process")
        assert proc_res.status_code == 200
        assert proc_res.json()["processing_status"] == "needs_review"

        # 3. GET extraction
        ext_res = client.get(f"/api/v1/documents/{doc_id}/extraction")
        assert ext_res.status_code == 200
        ext_data = ext_res.json()
        assert ext_data["vendor"] == "Northfield Type Foundry"
        assert ext_data["total"] == 143800  # minor units in EUR (cents)

        # 4. Validate should fail approval because math mismatch and missing category
        val_res = client.post(f"/api/v1/documents/{doc_id}/validate")
        assert val_res.status_code == 200
        val_data = val_res.json()
        assert val_data["can_approve"] is False
        assert any("Math guard" in i for i in val_data["issues"])
        assert any("Category is missing" in i for i in val_data["issues"])

        # Attempting approval must fail with 400
        app_fail = client.post(f"/api/v1/documents/{doc_id}/approve")
        assert app_fail.status_code == 400

        # 5. User edits fields: fixes total to 1428.00 and assigns Category "Software"
        patch_res = client.patch(
            f"/api/v1/documents/{doc_id}/extraction",
            json={
                "total": 1428.00,
                "category": "Software",
            },
        )
        assert patch_res.status_code == 200
        patched = patch_res.json()
        assert patched["total"] == 142800
        assert patched["category"] == "Software"

        # 6. Verify FieldProvenance records user edit
        provs = patched["field_provenances"]
        total_prov = next(p for p in provs if p["field_name"] == "total")
        assert total_prov["is_user_edited"] is True
        assert total_prov["user_value"] == "1428.0"

        # 7. Validate now passes!
        val_pass = client.post(f"/api/v1/documents/{doc_id}/validate")
        assert val_pass.status_code == 200
        assert val_pass.json()["can_approve"] is True
        assert val_pass.json()["edits_count"] >= 1

        # 8. Approve document into persistent ledger
        app_res = client.post(f"/api/v1/documents/{doc_id}/approve")
        assert app_res.status_code == 200
        assert app_res.json()["status"] == "approved"
        ledger_entry = app_res.json()["ledger_entry"]
        assert ledger_entry["total"] == 142800
        assert ledger_entry["currency"] == "EUR"
        assert ledger_entry["category"] == "Software"
        assert ledger_entry["edits_count"] >= 1

        # Confirm document status is now 'approved'
        doc_check = client.get(f"/api/v1/documents/{doc_id}")
        assert doc_check.json()["processing_status"] == "approved"
        assert doc_check.json()["review_status"] == "approved"

        # 9. Multi-currency ledger summary
        summary_res = client.get("/api/v1/ledger/summary")
        assert summary_res.status_code == 200
        summary = summary_res.json()
        assert "EUR" in summary["currencies"]
        eur_summary = summary["currencies"]["EUR"]
        assert eur_summary["total"] == 1428.00
        assert eur_summary["categories"]["Software"] == 1428.00

        # 10. CSV Export
        csv_res = client.get("/api/v1/ledger/export.csv")
        assert csv_res.status_code == 200
        assert "text/csv" in csv_res.headers["content-type"]
        csv_text = csv_res.text
        assert "Northfield Type Foundry" in csv_text
        assert "1428.00" in csv_text
        assert "EUR" in csv_text
        assert "Software" in csv_text

    finally:
        client.app.dependency_overrides.pop(get_ai_service, None)


def test_reject_document(client: TestClient):
    """Verify rejecting a document sets review_status to rejected without adding to ledger."""
    up = client.post(
        "/api/v1/documents",
        files={"file": ("junk.txt", io.BytesIO(b"Unknown bill\nTotal: 10.00\n"), "text/plain")},
    )
    doc_id = up.json()["id"]

    rej_res = client.post(f"/api/v1/documents/{doc_id}/reject")
    assert rej_res.status_code == 200
    assert rej_res.json()["status"] == "rejected"
    assert rej_res.json()["document"]["review_status"] == "rejected"


def test_delete_ledger_entry(client: TestClient):
    """Verify deleting a ledger entry restores document status to needs_review."""
    up = client.post(
        "/api/v1/documents",
        files={"file": ("coffee.txt", io.BytesIO(b"Cafe\nDate: 2026-10-01\nTotal: $5.00\n"), "text/plain")},
    )
    doc_id = up.json()["id"]

    # Mock AI & process
    mock_ai = AsyncMock(spec=LocalAIService)
    mock_ai.extract_structured_data.return_value = (
        AIStructuredOutput(
            vendor="Cafe",
            document_number=None,
            date="2026-10-01",
            currency="USD",
            subtotal=5.00,
            tax=0.00,
            total=5.00,
            category="Meals",
            line_items=[],
        ),
        "test-model",
        "llm",
    )
    client.app.dependency_overrides[get_ai_service] = lambda: mock_ai

    try:
        client.post(f"/api/v1/documents/{doc_id}/process")
        app_res = client.post(f"/api/v1/documents/{doc_id}/approve")
        entry_id = app_res.json()["ledger_entry"]["id"]

        # Delete entry
        del_res = client.delete(f"/api/v1/ledger/{entry_id}")
        assert del_res.status_code == 200

        # Document should revert to needs_review
        doc = client.get(f"/api/v1/documents/{doc_id}").json()
        assert doc["processing_status"] == "needs_review"
    finally:
        client.app.dependency_overrides.pop(get_ai_service, None)
