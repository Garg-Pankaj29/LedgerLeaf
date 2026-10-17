"""Tests for document upload, validation, duplicate detection, listing, and deletion."""

import io
from fastapi.testclient import TestClient


def test_upload_valid_text_document(client: TestClient):
    """Verify successful upload of a plain text document."""
    file_content = b"Juniper & Oak Coffee\nDate: 2026-10-03\nTotal: $9.72\n"
    response = client.post(
        "/api/v1/documents",
        files={"file": ("receipt.txt", io.BytesIO(file_content), "text/plain")},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["original_filename"] == "receipt.txt"
    assert data["file_size"] == len(file_content)
    assert data["processing_status"] == "uploaded"
    assert data["review_status"] == "unreviewed"
    assert len(data["sha256_hash"]) == 64
    assert data["is_duplicate"] is False


def test_duplicate_document_detection(client: TestClient):
    """Verify duplicate document is detected by SHA-256 hash without silent deletion."""
    file_content = b"Northfield Type Foundry\nInvoice No: INV-3307\nTotal: EUR 1438.00\n"

    # First upload
    res1 = client.post(
        "/api/v1/documents",
        files={"file": ("invoice1.txt", io.BytesIO(file_content), "text/plain")},
    )
    assert res1.status_code == 201
    doc1 = res1.json()
    assert doc1["is_duplicate"] is False

    # Second upload with identical content
    res2 = client.post(
        "/api/v1/documents",
        files={"file": ("invoice2.txt", io.BytesIO(file_content), "text/plain")},
    )
    assert res2.status_code == 201
    doc2 = res2.json()
    assert doc2["is_duplicate"] is True
    assert doc2["duplicate_of_id"] == doc1["id"]
    assert doc2["id"] != doc1["id"]  # Preserved as a separate entry


def test_upload_invalid_extension(client: TestClient):
    """Verify unsupported file extension returns HTTP 400 with explanation."""
    response = client.post(
        "/api/v1/documents",
        files={"file": ("malicious.exe", io.BytesIO(b"MZ\x90\x00"), "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "not supported" in response.json()["detail"].lower()


def test_upload_corrupt_signature(client: TestClient):
    """Verify file with forged extension/MIME but wrong magic signature is rejected."""
    corrupt_pdf = b"THIS IS NOT A REAL PDF FILE"
    response = client.post(
        "/api/v1/documents",
        files={"file": ("corrupt.pdf", io.BytesIO(corrupt_pdf), "application/pdf")},
    )
    assert response.status_code == 400
    assert "signature" in response.json()["detail"].lower()


def test_upload_empty_file(client: TestClient):
    """Verify 0-byte file returns HTTP 400."""
    response = client.post(
        "/api/v1/documents",
        files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_list_and_get_document(client: TestClient):
    """Verify listing and retrieving document details."""
    content = b"Taxi slip\nDate: 2026-10-04\nTotal: INR 640.00\n"
    create_res = client.post(
        "/api/v1/documents",
        files={"file": ("taxi.txt", io.BytesIO(content), "text/plain")},
    )
    doc_id = create_res.json()["id"]

    # List
    list_res = client.get("/api/v1/documents")
    assert list_res.status_code == 200
    docs = list_res.json()
    assert any(d["id"] == doc_id for d in docs)

    # Get by ID
    get_res = client.get(f"/api/v1/documents/{doc_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == doc_id
    assert get_res.json()["original_filename"] == "taxi.txt"

    # Get non-existent
    bad_res = client.get("/api/v1/documents/non-existent-id")
    assert bad_res.status_code == 404


def test_delete_document(client: TestClient):
    """Verify safe deletion of document record and file from disk."""
    content = b"To be deleted\nTotal: $1.00\n"
    res = client.post(
        "/api/v1/documents",
        files={"file": ("delete_me.txt", io.BytesIO(content), "text/plain")},
    )
    doc_id = res.json()["id"]

    # Delete
    del_res = client.delete(f"/api/v1/documents/{doc_id}")
    assert del_res.status_code == 200
    assert "deleted successfully" in del_res.json()["message"]

    # Confirm 404 on subsequent get
    assert client.get(f"/api/v1/documents/{doc_id}").status_code == 404
