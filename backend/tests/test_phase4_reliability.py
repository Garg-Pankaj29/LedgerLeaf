"""Reliability, security, and data integrity tests for Phase 4."""

import io
import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from backend.app.services.storage_service import StorageService, StorageError
from backend.app.services.local_ai import (
    LocalAIService,
    AIStructuredOutput,
    AIConnectionError,
)
from backend.app.api.v1.documents import get_ai_service


def test_repeated_approval_idempotency(client: TestClient):
    """Verify that repeated approval requests on the same document do not create duplicate ledger entries."""
    up = client.post(
        "/api/v1/documents",
        files={"file": ("stationery.txt", io.BytesIO(b"Paper Supply Co\nDate: 2026-10-04\nTotal: $12.00\n"), "text/plain")},
    )
    doc_id = up.json()["id"]

    # Patch with valid data
    client.patch(
        f"/api/v1/documents/{doc_id}/extraction",
        json={
            "vendor": "Paper Supply Co",
            "date": "2026-10-04",
            "currency": "USD",
            "total": 12.00,
            "category": "Office",
        },
    )

    # First approval -> 200 approved
    app1 = client.post(f"/api/v1/documents/{doc_id}/approve")
    assert app1.status_code == 200
    assert app1.json()["status"] == "approved"
    entry_id = app1.json()["ledger_entry"]["id"]

    # Second approval -> 200 already_approved with same entry ID
    app2 = client.post(f"/api/v1/documents/{doc_id}/approve")
    assert app2.status_code == 200
    assert app2.json()["status"] == "already_approved"
    assert app2.json()["ledger_entry"]["id"] == entry_id

    # Ledger must only contain 1 entry for this document
    ledger = client.get("/api/v1/ledger").json()
    matching = [e for e in ledger if e["document_id"] == doc_id]
    assert len(matching) == 1


def test_path_traversal_defense():
    """Verify that path traversal attempts in StorageService are blocked."""
    storage = StorageService()

    with pytest.raises(StorageError, match="path traversal detected"):
        storage.get_file_path("../../etc/passwd")

    with pytest.raises(StorageError, match="path traversal detected"):
        storage.get_file_path("/etc/shadow")

    with pytest.raises(StorageError, match="path traversal detected"):
        storage.get_file_path("sub/folder/secret.txt")


def test_document_deletion_cascades_and_cleans_file(client: TestClient):
    """Verify document deletion removes stored disk file and cascades database records."""
    up = client.post(
        "/api/v1/documents",
        files={"file": ("to_delete.txt", io.BytesIO(b"Delete me\nDate: 2026-10-05\nTotal: $20.00\n"), "text/plain")},
    )
    doc_id = up.json()["id"]
    stored_name = up.json()["stored_filename"]

    storage = StorageService()
    file_path = storage.get_file_path(stored_name)
    assert file_path.exists()

    # Create extraction and approve
    client.patch(
        f"/api/v1/documents/{doc_id}/extraction",
        json={"vendor": "Delete Co", "date": "2026-10-05", "total": 20.00, "category": "Other", "currency": "USD"},
    )
    client.post(f"/api/v1/documents/{doc_id}/approve")

    # Delete document
    del_res = client.delete(f"/api/v1/documents/{doc_id}")
    assert del_res.status_code == 200

    # Stored file must be unlinked
    assert not file_path.exists()

    # Document must be gone
    get_res = client.get(f"/api/v1/documents/{doc_id}")
    assert get_res.status_code == 404


def test_csv_rfc4180_escaping_and_trust_metadata(client: TestClient):
    """Verify CSV export properly escapes commas, quotes, and newlines according to RFC 4180."""
    up = client.post(
        "/api/v1/documents",
        files={"file": ("special_vendor.txt", io.BytesIO(b"Vendor With, Comma & \"Quotes\"\nDate: 2026-10-06\nTotal: $15.50\n"), "text/plain")},
    )
    doc_id = up.json()["id"]

    client.patch(
        f"/api/v1/documents/{doc_id}/extraction",
        json={
            "vendor": 'Acme, Inc. "Premier"',
            "date": "2026-10-06",
            "currency": "USD",
            "total": 15.50,
            "category": "Services",
        },
    )
    client.post(f"/api/v1/documents/{doc_id}/approve")

    csv_res = client.get("/api/v1/ledger/export.csv")
    assert csv_res.status_code == 200
    csv_text = csv_res.text

    # Must be properly escaped in CSV with double quotes: "Acme, Inc. ""Premier"""
    assert '"Acme, Inc. ""Premier"""' in csv_text or 'Acme, Inc. ""Premier""' in csv_text


def test_multi_currency_strict_segregation(client: TestClient):
    """Verify that summaries never merge different currencies together."""
    currencies_to_test = [
        ("USD Vendor", "USD", 10.00, "Meals"),
        ("EUR Vendor", "EUR", 20.00, "Software"),
        ("INR Vendor", "INR", 500.00, "Travel"),
    ]

    for vendor, curr, total, cat in currencies_to_test:
        client.post(
            "/api/v1/ledger/demo-sample",
            json={
                "vendor": vendor,
                "date": "2026-10-07",
                "currency": curr,
                "total": total,
                "category": cat,
            },
        )

    summary_res = client.get("/api/v1/ledger/summary")
    assert summary_res.status_code == 200
    summary = summary_res.json()["currencies"]

    # Must have segregated summaries
    assert "USD" in summary
    assert "EUR" in summary
    assert "INR" in summary

    assert summary["USD"]["total"] >= 10.00
    assert summary["EUR"]["total"] >= 20.00
    assert summary["INR"]["total"] >= 500.00


def test_demo_sample_seeding_and_tagging(client: TestClient):
    """Verify explicit demo seeding populates the ledger with is_demo=True."""
    seed_res = client.post("/api/v1/ledger/seed-demo-samples")
    assert seed_res.status_code == 201
    assert seed_res.json()["status"] == "success"

    ledger = client.get("/api/v1/ledger").json()
    demo_entries = [e for e in ledger if e["is_demo"] is True]
    assert len(demo_entries) >= 3

    # Check CSV distinguishes demo records
    csv_res = client.get("/api/v1/ledger/export.csv")
    assert "demo" in csv_res.text


def test_offline_ai_behavior_returns_service_unavailable(client: TestClient):
    """Verify that when local AI is disconnected, the endpoint fails with a 503 rather than fake output."""
    up = client.post(
        "/api/v1/documents",
        files={"file": ("test_offline.txt", io.BytesIO(b"Vendor Test\nTotal: $10.00\n"), "text/plain")},
    )
    doc_id = up.json()["id"]

    mock_ai = AsyncMock(spec=LocalAIService)
    mock_ai.extract_structured_data.side_effect = AIConnectionError("LM Studio not running on 127.0.0.1:1234")
    client.app.dependency_overrides[get_ai_service] = lambda: mock_ai

    try:
        proc_res = client.post(f"/api/v1/documents/{doc_id}/process")
        assert proc_res.status_code == 503
        assert "Local AI error" in proc_res.json()["detail"]

        # Document status should be failed
        doc = client.get(f"/api/v1/documents/{doc_id}").json()
        assert doc["processing_status"] == "failed"
        assert "LM Studio not running" in doc["error_details"]
    finally:
        client.app.dependency_overrides.pop(get_ai_service, None)
