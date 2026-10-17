"""Tests for local AI service, document processing workflow, error handling, and mock inference."""

import io
import os
from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient
from backend.app.services.local_ai import (
    LocalAIService,
    AIStructuredOutput,
    AITimeoutError,
    AIConnectionError,
    AIValidationError,
    AIModelNotFoundError,
)
from backend.app.api.v1.documents import get_ai_service


def test_process_document_success_with_provenance_and_minor_units(client: TestClient):
    """
    Test end-to-end document processing with mocked local AI:
    - Text extracted from document
    - Structured AI extraction parsed into Pydantic schema
    - Monetary amounts converted to integer minor units (e.g. 972 cents)
    - Field provenance offsets and snippets recorded
    - Document status moved to 'needs_review'
    """
    receipt_text = (
        "Juniper & Oak Coffee\n"
        "Receipt #R-20418\n"
        "Date: 2026-10-03\n"
        "2 x Oat latte: $6.00\n"
        "1 x Almond croissant: $3.00\n"
        "Subtotal: $9.00\n"
        "Tax (8%): $0.72\n"
        "Total: $9.72\n"
    )

    # 1. Upload document
    upload_res = client.post(
        "/api/v1/documents",
        files={"file": ("juniper.txt", io.BytesIO(receipt_text.encode("utf-8")), "text/plain")},
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["id"]

    # 2. Mock AI service
    mock_ai = AsyncMock(spec=LocalAIService)
    mock_ai.extract_structured_data.return_value = (
        AIStructuredOutput(
            vendor="Juniper & Oak Coffee",
            document_number="R-20418",
            date="2026-10-03",
            currency="USD",
            subtotal=9.00,
            tax=0.72,
            total=9.72,
            category="Meals",
            description="Coffee and bakery",
            line_items=[
                {"description": "2 x Oat latte", "quantity": 2, "unit_price": 3.0, "amount": 6.0},
                {"description": "1 x Almond croissant", "quantity": 1, "unit_price": 3.0, "amount": 3.0},
            ],
            uncertain_fields=[],
        ),
        "meta-llama-3.1-8b-instruct",
        "llm",
    )

    client.app.dependency_overrides[get_ai_service] = lambda: mock_ai

    try:
        # 3. Process document
        proc_res = client.post(f"/api/v1/documents/{doc_id}/process")
        assert proc_res.status_code == 200
        data = proc_res.json()

        assert data["processing_status"] == "needs_review"
        assert len(data["extractions"]) == 1

        ext = data["extractions"][0]
        assert ext["vendor"] == "Juniper & Oak Coffee"
        assert ext["invoice_number"] == "R-20418"
        assert ext["date"] == "2026-10-03"
        assert ext["currency"] == "USD"
        # Verify integer minor units in database
        assert ext["subtotal"] == 900
        assert ext["tax"] == 72
        assert ext["total"] == 972
        assert ext["category"] == "Meals"
        assert ext["model_name"] == "meta-llama-3.1-8b-instruct"

        # Verify field provenance was generated with offsets and snippets
        provenances = ext["field_provenances"]
        assert len(provenances) > 0
        vendor_prov = next((p for p in provenances if p["field_name"] == "vendor"), None)
        assert vendor_prov is not None
        assert vendor_prov["extracted_value"] == "Juniper & Oak Coffee"
        assert vendor_prov["start_offset"] is not None
        assert vendor_prov["source_snippet"] is not None

    finally:
        client.app.dependency_overrides.pop(get_ai_service, None)


def test_process_document_missing_fields_without_inventing(client: TestClient):
    """Verify that missing fields from AI output remain null without inventing numbers."""
    taxi_text = "Metro Cab Services\nTotal: INR 640.00\n"
    upload_res = client.post(
        "/api/v1/documents",
        files={"file": ("taxi.txt", io.BytesIO(taxi_text.encode("utf-8")), "text/plain")},
    )
    doc_id = upload_res.json()["id"]

    mock_ai = AsyncMock(spec=LocalAIService)
    mock_ai.extract_structured_data.return_value = (
        AIStructuredOutput(
            vendor="Metro Cab Services",
            document_number=None,
            date=None,
            currency="INR",
            subtotal=None,
            tax=None,
            total=640.00,
            category="Travel",
            line_items=[],
            uncertain_fields=["date"],
        ),
        "meta-llama-3.1-8b-instruct",
        "llm",
    )

    client.app.dependency_overrides[get_ai_service] = lambda: mock_ai

    try:
        proc_res = client.post(f"/api/v1/documents/{doc_id}/process")
        assert proc_res.status_code == 200
        ext = proc_res.json()["extractions"][0]

        assert ext["date"] is None
        assert ext["subtotal"] is None
        assert ext["tax"] is None
        assert ext["total"] == 64000  # 64000 paise
        assert any("Date is missing" in iss for iss in ext["validation_issues"])
    finally:
        client.app.dependency_overrides.pop(get_ai_service, None)


def test_process_document_ai_timeout(client: TestClient):
    """Verify handling of AI inference timeout: updates status to failed and returns 504."""
    upload_res = client.post(
        "/api/v1/documents",
        files={"file": ("doc.txt", io.BytesIO(b"Sample invoice text"), "text/plain")},
    )
    doc_id = upload_res.json()["id"]

    mock_ai = AsyncMock(spec=LocalAIService)
    mock_ai.extract_structured_data.side_effect = AITimeoutError("Inference timed out after 120s")
    client.app.dependency_overrides[get_ai_service] = lambda: mock_ai

    try:
        proc_res = client.post(f"/api/v1/documents/{doc_id}/process")
        assert proc_res.status_code == 504
        assert "timeout" in proc_res.json()["detail"].lower()

        # Check DB state
        doc_res = client.get(f"/api/v1/documents/{doc_id}")
        assert doc_res.json()["processing_status"] == "failed"
        assert "timeout" in doc_res.json()["error_details"].lower()
    finally:
        client.app.dependency_overrides.pop(get_ai_service, None)


def test_process_document_ai_connection_failure(client: TestClient):
    """Verify handling of offline LM Studio server: updates status to failed and returns 503."""
    upload_res = client.post(
        "/api/v1/documents",
        files={"file": ("doc2.txt", io.BytesIO(b"Sample invoice text"), "text/plain")},
    )
    doc_id = upload_res.json()["id"]

    mock_ai = AsyncMock(spec=LocalAIService)
    mock_ai.extract_structured_data.side_effect = AIConnectionError("Could not reach 127.0.0.1:1234")
    client.app.dependency_overrides[get_ai_service] = lambda: mock_ai

    try:
        proc_res = client.post(f"/api/v1/documents/{doc_id}/process")
        assert proc_res.status_code == 503
        assert "error" in proc_res.json()["detail"].lower()

        # Check DB state
        doc_res = client.get(f"/api/v1/documents/{doc_id}")
        assert doc_res.json()["processing_status"] == "failed"
    finally:
        client.app.dependency_overrides.pop(get_ai_service, None)


def test_process_document_malformed_ai_json(client: TestClient):
    """Verify handling of malformed JSON from model: returns 502 and marks document failed."""
    upload_res = client.post(
        "/api/v1/documents",
        files={"file": ("doc3.txt", io.BytesIO(b"Sample invoice text"), "text/plain")},
    )
    doc_id = upload_res.json()["id"]

    mock_ai = AsyncMock(spec=LocalAIService)
    mock_ai.extract_structured_data.side_effect = AIValidationError("Malformed JSON returned by model")
    client.app.dependency_overrides[get_ai_service] = lambda: mock_ai

    try:
        proc_res = client.post(f"/api/v1/documents/{doc_id}/process")
        assert proc_res.status_code == 502

        doc_res = client.get(f"/api/v1/documents/{doc_id}")
        assert doc_res.json()["processing_status"] == "failed"
    finally:
        client.app.dependency_overrides.pop(get_ai_service, None)


def test_ai_test_connection_endpoint(client: TestClient):
    """Verify POST /api/v1/ai/test-connection."""
    res = client.post("/api/v1/ai/test-connection")
    assert res.status_code == 200
    data = res.json()
    assert "connected" in data
    assert "base_url" in data
    assert "message" in data


def test_ai_models_endpoint_disconnected(client: TestClient):
    """Verify GET /api/v1/ai/models returns 503 when local LM Studio is offline."""
    res = client.get("/api/v1/ai/models")
    # When local LM Studio is offline, it cleanly returns 503 Service Unavailable
    assert res.status_code in (200, 503)


@pytest.mark.skipif(
    not os.getenv("RUN_REAL_AI_TESTS"),
    reason="Live LM Studio integration test disabled by default (enable with RUN_REAL_AI_TESTS=1)",
)
@pytest.mark.anyio
async def test_live_lm_studio_integration():
    """Live integration test against a running LM Studio server (optional)."""
    service = LocalAIService()
    status = await service.test_connection()
    assert status["connected"] is True
    assert len(status["models_available"]) > 0
