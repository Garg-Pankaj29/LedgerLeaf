"""Document management endpoints: upload, list, detail, delete, process, extraction edit, validate, approve, reject."""

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.app.config import get_settings
from backend.app.database import get_db
from backend.app.models.document import Document, ProcessingStatus, ReviewStatus
from backend.app.models.extraction import ExtractionResult, ExtractionMethod
from backend.app.models.provenance import FieldProvenance, ExtractionSource, ValidationStatus
from backend.app.models.ledger import LedgerEntry
from backend.app.schemas.document import DocumentResponse
from backend.app.schemas.extraction import ExtractionResultResponse, ExtractionResultUpdate
from backend.app.schemas.ledger import LedgerEntryResponse
from backend.app.schemas.common import ValidationResultResponse
from backend.app.schemas.money import to_minor_units
from backend.app.services.storage_service import (
    StorageService,
    StorageError,
    FileSizeLimitExceededError,
    UnsupportedFileTypeError,
    InvalidFileSignatureError,
)
from backend.app.services.text_extraction_service import (
    TextExtractionService,
    TextExtractionError,
    EmptyTextError,
    OCRError,
)
from backend.app.services.local_ai import (
    LocalAIService,
    LocalAIError,
    AIConnectionError,
    AITimeoutError,
    AIModelNotFoundError,
)
from backend.app.services.validation_service import ValidationService

router = APIRouter(prefix="/documents", tags=["Documents"])


def get_storage_service() -> StorageService:
    return StorageService()


def get_text_extraction_service() -> TextExtractionService:
    return TextExtractionService()


def get_ai_service() -> LocalAIService:
    return LocalAIService()


def get_validation_service() -> ValidationService:
    return ValidationService()


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
) -> DocumentResponse:
    """
    Upload a document (PDF, image, or text file).
    Validates file extension, size limit, MIME type, and magic bytes signature.
    Calculates SHA-256 and detects duplicates without deleting anything.
    """
    filename = file.filename or "unknown"
    content_type = file.content_type or "application/octet-stream"

    try:
        content = await file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read uploaded file: {exc}",
        )

    # Validate file
    try:
        storage.validate_file(filename, content_type, content)
    except FileSizeLimitExceededError as exc:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc))
    except (UnsupportedFileTypeError, InvalidFileSignatureError, StorageError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # Calculate hash and check for duplicates
    sha256_hash = storage.compute_sha256(content)
    existing_stmt = select(Document).where(Document.sha256_hash == sha256_hash)
    existing_doc = db.execute(existing_stmt).scalars().first()

    is_duplicate = False
    duplicate_of_id = None
    if existing_doc:
        is_duplicate = True
        duplicate_of_id = existing_doc.id

    # Save file to private storage outside public web directory
    stored_filename, _, file_size = storage.save_file(content, filename)

    # Attempt to extract text immediately so it is available for inspection even before AI runs
    extracted_txt = None
    try:
        extractor = TextExtractionService()
        f_path = storage.get_file_path(stored_filename)
        if f_path.exists():
            extracted_txt, _ = extractor.extract_text(f_path, content_type)
    except Exception:
        extracted_txt = None

    # Create document record
    doc = Document(
        original_filename=filename,
        stored_filename=stored_filename,
        file_type=content_type,
        file_size=file_size,
        sha256_hash=sha256_hash,
        extracted_text=extracted_txt,
        processing_status=ProcessingStatus.UPLOADED,
        review_status=ReviewStatus.UNREVIEWED,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    response = DocumentResponse.model_validate(doc)
    response.is_duplicate = is_duplicate
    response.duplicate_of_id = duplicate_of_id
    return response


@router.get("", response_model=List[DocumentResponse])
def list_documents(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> List[DocumentResponse]:
    """List all saved documents ordered by most recently created."""
    stmt = select(Document).order_by(Document.created_at.desc()).offset(skip).limit(limit)
    documents = db.execute(stmt).scalars().all()
    return [DocumentResponse.model_validate(doc) for doc in documents]


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
) -> DocumentResponse:
    """Retrieve details, extractions, and processing status for a specific document."""
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )
    return DocumentResponse.model_validate(doc)


@router.delete("/{document_id}", status_code=status.HTTP_200_OK)
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
) -> dict:
    """Safely delete a document from the database and remove its file from disk."""
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )

    # Remove stored file from disk
    storage.delete_file(doc.stored_filename)

    # Delete database record (cascades extractions and provenance)
    db.delete(doc)
    db.commit()

    return {
        "status": "success",
        "message": f"Document '{doc.original_filename}' ({document_id}) deleted successfully.",
    }


@router.post("/{document_id}/process", response_model=DocumentResponse)
async def process_document(
    document_id: str,
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    extractor: TextExtractionService = Depends(get_text_extraction_service),
    ai_service: LocalAIService = Depends(get_ai_service),
    validator: ValidationService = Depends(get_validation_service),
) -> DocumentResponse:
    """
    Process or retry processing a document:
    1. Extract text (PDF text parser, OCR for images/scans, or plain text).
    2. Submit text to local open-weight AI model for structured extraction.
    3. Validate with deterministic Math Guard checks and save ExtractionResult + Provenance.
    4. Move state to 'needs_review'.
    """
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )

    # Mark as processing
    doc.processing_status = ProcessingStatus.PROCESSING
    doc.error_details = None
    db.commit()

    file_path = storage.get_file_path(doc.stored_filename)
    if not file_path.exists():
        doc.processing_status = ProcessingStatus.FAILED
        doc.error_details = f"File '{doc.stored_filename}' is missing from storage."
        db.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=doc.error_details)

    # Step 1: Text Extraction
    try:
        extracted_text, text_method = extractor.extract_text(file_path, doc.file_type)
        doc.extracted_text = extracted_text
        db.commit()
    except EmptyTextError as exc:
        doc.processing_status = ProcessingStatus.FAILED
        doc.error_details = f"Text extraction failed: {str(exc)}"
        db.commit()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=doc.error_details)
    except OCRError as exc:
        doc.processing_status = ProcessingStatus.FAILED
        doc.error_details = f"OCR processing failed: {str(exc)}"
        db.commit()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=doc.error_details)
    except TextExtractionError as exc:
        doc.processing_status = ProcessingStatus.FAILED
        doc.error_details = f"Extraction error: {str(exc)}"
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=doc.error_details)

    # Step 2: Structured AI Extraction via LM Studio
    try:
        ai_output, model_name, extraction_method = await ai_service.extract_structured_data(extracted_text)
    except (AIConnectionError, AIModelNotFoundError) as exc:
        doc.processing_status = ProcessingStatus.FAILED
        doc.error_details = f"Local AI error: {str(exc)}"
        db.commit()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=doc.error_details)
    except AITimeoutError as exc:
        doc.processing_status = ProcessingStatus.FAILED
        doc.error_details = f"Local AI timeout: {str(exc)}"
        db.commit()
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=doc.error_details)
    except LocalAIError as exc:
        doc.processing_status = ProcessingStatus.FAILED
        doc.error_details = f"AI extraction failed: {str(exc)}"
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=doc.error_details)

    # Step 3: Monetary Unit Conversion & Math Guard Validation
    curr = ai_output.currency or "USD"
    subtotal_minor = to_minor_units(ai_output.subtotal, curr)
    tax_minor = to_minor_units(ai_output.tax, curr)
    total_minor = to_minor_units(ai_output.total, curr)

    # Save ExtractionResult
    extraction = ExtractionResult(
        document_id=doc.id,
        vendor=ai_output.vendor,
        invoice_number=ai_output.document_number,
        date=ai_output.date,
        due_date=ai_output.due_date,
        currency=curr,
        subtotal=subtotal_minor,
        tax=tax_minor,
        total=total_minor,
        category=ai_output.category,
        description=ai_output.description,
        line_items=ai_output.line_items,
        extraction_method=ExtractionMethod.LLM,
        model_name=model_name,
        validation_issues=[],
    )
    db.add(extraction)
    db.commit()
    db.refresh(extraction)

    # Step 4: Generate Field Provenance Records
    fields_to_track = [
        ("vendor", ai_output.vendor),
        ("number", ai_output.document_number),
        ("date", ai_output.date),
        ("currency", curr),
        ("total", str(ai_output.total) if ai_output.total is not None else None),
        ("subtotal", str(ai_output.subtotal) if ai_output.subtotal is not None else None),
        ("tax", str(ai_output.tax) if ai_output.tax is not None else None),
        ("category", ai_output.category),
    ]

    for field_name, value in fields_to_track:
        if not value:
            prov = FieldProvenance(
                extraction_result_id=extraction.id,
                field_name=field_name,
                extracted_value=None,
                source_snippet=None,
                start_offset=None,
                end_offset=None,
                extraction_source=ExtractionSource.AI_MODEL,
                is_user_edited=False,
                validation_status=ValidationStatus.MISSING,
            )
            db.add(prov)
            continue

        # Look for value in document text
        idx = extracted_text.lower().find(str(value).lower())
        snippet = None
        s_offset = None
        e_offset = None

        if idx != -1:
            s_offset = idx
            e_offset = idx + len(str(value))
            snippet = extracted_text[max(0, s_offset - 15) : min(len(extracted_text), e_offset + 15)].strip()

        prov = FieldProvenance(
            extraction_result_id=extraction.id,
            field_name=field_name,
            extracted_value=str(value),
            source_snippet=snippet or str(value),
            start_offset=s_offset,
            end_offset=e_offset,
            extraction_source=ExtractionSource.AI_MODEL,
            is_user_edited=False,
            validation_status=ValidationStatus.VALID,
        )
        db.add(prov)

    db.commit()
    db.refresh(extraction)

    # Step 5: Run Deterministic Validation & Store Diagnostics
    val_res = validator.validate(extraction, extracted_text, db)
    extraction.validation_issues = [*(val_res.issues), *(val_res.warnings)]

    # Update document status to needs_review
    doc.processing_status = ProcessingStatus.NEEDS_REVIEW
    doc.error_details = None
    db.commit()
    db.refresh(doc)

    return DocumentResponse.model_validate(doc)


# ==============================================================================
# Phase 3: Human Review, Editing, Validation, Approval, and Rejection Endpoints
# ==============================================================================


@router.get("/{document_id}/extraction", response_model=ExtractionResultResponse)
def get_document_extraction(
    document_id: str,
    db: Session = Depends(get_db),
    validator: ValidationService = Depends(get_validation_service),
) -> ExtractionResultResponse:
    """Retrieve the latest extracted fields and provenance records for a document."""
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found.")

    stmt = (
        select(ExtractionResult)
        .where(ExtractionResult.document_id == document_id)
        .order_by(ExtractionResult.created_at.desc())
    )
    extraction = db.execute(stmt).scalars().first()
    if not extraction:
        # If text is not extracted yet, try extracting it from stored file
        if not doc.extracted_text:
            try:
                storage = StorageService()
                extractor = TextExtractionService()
                f_path = storage.get_file_path(doc.stored_filename)
                if f_path.exists():
                    txt, _ = extractor.extract_text(f_path, doc.file_type)
                    doc.extracted_text = txt
            except Exception:
                pass

        extraction = ExtractionResult(
            document_id=document_id,
            currency="USD",
            extraction_method=ExtractionMethod.MANUAL,
            validation_issues=[],
        )
        db.add(extraction)
        db.commit()
        db.refresh(extraction)

        val_res = validator.validate(extraction, doc.extracted_text or "", db)
        extraction.validation_issues = [*(val_res.issues), *(val_res.warnings)]
        db.commit()
        db.refresh(extraction)

    return ExtractionResultResponse.model_validate(extraction)


@router.patch("/{document_id}/extraction", response_model=ExtractionResultResponse)
def update_document_extraction(
    document_id: str,
    update_data: ExtractionResultUpdate,
    db: Session = Depends(get_db),
    validator: ValidationService = Depends(get_validation_service),
) -> ExtractionResultResponse:
    """
    Allow the user to edit extracted fields before approval.
    Records user edits in FieldProvenance, never silently overrides numbers to force math to balance,
    and returns updated extraction with re-evaluated validation diagnostics.
    """
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found.")

    stmt = (
        select(ExtractionResult)
        .where(ExtractionResult.document_id == document_id)
        .order_by(ExtractionResult.created_at.desc())
    )
    extraction = db.execute(stmt).scalars().first()
    if not extraction:
        # If text is not extracted yet, try extracting it from stored file
        if not doc.extracted_text:
            try:
                storage = StorageService()
                extractor = TextExtractionService()
                f_path = storage.get_file_path(doc.stored_filename)
                if f_path.exists():
                    txt, _ = extractor.extract_text(f_path, doc.file_type)
                    doc.extracted_text = txt
            except Exception:
                pass

        extraction = ExtractionResult(
            document_id=document_id,
            currency="USD",
            extraction_method=ExtractionMethod.MANUAL,
            validation_issues=[],
        )
        db.add(extraction)
        db.commit()
        db.refresh(extraction)

    curr = (update_data.currency or extraction.currency or "USD").upper()

    # Track which fields were provided in the update payload
    provided_fields = update_data.model_dump(exclude_unset=True)

    def mark_provenance_edited(f_name: str, new_val: Any):
        """Mark a field as user-edited in field provenance table."""
        prov_stmt = select(FieldProvenance).where(
            FieldProvenance.extraction_result_id == extraction.id,
            FieldProvenance.field_name == f_name,
        )
        prov = db.execute(prov_stmt).scalars().first()
        if not prov:
            prov = FieldProvenance(
                extraction_result_id=extraction.id,
                field_name=f_name,
                extraction_source=ExtractionSource.USER_INPUT,
                start_offset=None,
                end_offset=None,
            )
            db.add(prov)

        prov.is_user_edited = True
        prov.user_value = str(new_val) if new_val is not None else ""
        prov.validation_status = ValidationStatus.VALID

    if "vendor" in provided_fields:
        extraction.vendor = update_data.vendor
        mark_provenance_edited("vendor", update_data.vendor)

    if "invoice_number" in provided_fields:
        extraction.invoice_number = update_data.invoice_number
        mark_provenance_edited("number", update_data.invoice_number)

    if "date" in provided_fields:
        extraction.date = update_data.date
        mark_provenance_edited("date", update_data.date)

    if "due_date" in provided_fields:
        extraction.due_date = update_data.due_date

    if "currency" in provided_fields:
        extraction.currency = curr
        mark_provenance_edited("currency", curr)

    if "subtotal" in provided_fields:
        extraction.subtotal = to_minor_units(update_data.subtotal, curr)
        mark_provenance_edited("subtotal", update_data.subtotal)

    if "tax" in provided_fields:
        extraction.tax = to_minor_units(update_data.tax, curr)
        mark_provenance_edited("tax", update_data.tax)

    if "total" in provided_fields:
        extraction.total = to_minor_units(update_data.total, curr)
        mark_provenance_edited("total", update_data.total)

    if "category" in provided_fields:
        extraction.category = update_data.category
        mark_provenance_edited("category", update_data.category)

    if "description" in provided_fields:
        extraction.description = update_data.description

    if "line_items" in provided_fields:
        extraction.line_items = update_data.line_items

    extraction.updated_at = datetime.now(timezone.utc)
    if doc.processing_status in [ProcessingStatus.UPLOADED, ProcessingStatus.FAILED]:
        doc.processing_status = ProcessingStatus.NEEDS_REVIEW
    db.commit()
    db.refresh(extraction)

    # Re-evaluate validation issues with user edits
    val_res = validator.validate(extraction, doc.extracted_text or "", db)
    extraction.validation_issues = [*(val_res.issues), *(val_res.warnings)]
    db.commit()
    db.refresh(extraction)

    return ExtractionResultResponse.model_validate(extraction)


@router.post("/{document_id}/validate", response_model=ValidationResultResponse)
def validate_document(
    document_id: str,
    db: Session = Depends(get_db),
    validator: ValidationService = Depends(get_validation_service),
) -> ValidationResultResponse:
    """
    Run deterministic validation checks on the document extraction.
    Checks required fields, valid dates, arithmetic balance, duplicates, and uncertain fields.
    """
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found.")

    stmt = (
        select(ExtractionResult)
        .where(ExtractionResult.document_id == document_id)
        .order_by(ExtractionResult.created_at.desc())
    )
    extraction = db.execute(stmt).scalars().first()
    if not extraction:
        raise HTTPException(
            status_code=404,
            detail=f"No extraction found for document '{document_id}'.",
        )

    val_res = validator.validate(extraction, doc.extracted_text or "", db)
    extraction.validation_issues = [*(val_res.issues), *(val_res.warnings)]
    db.commit()

    return val_res


@router.post("/{document_id}/approve", status_code=status.HTTP_200_OK)
def approve_document(
    document_id: str,
    db: Session = Depends(get_db),
    validator: ValidationService = Depends(get_validation_service),
) -> Dict[str, Any]:
    """
    Approve record and add to the persistent ledger.
    Fails if validation issues block approval.
    """
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found.")

    stmt = (
        select(ExtractionResult)
        .where(ExtractionResult.document_id == document_id)
        .order_by(ExtractionResult.created_at.desc())
    )
    extraction = db.execute(stmt).scalars().first()
    if not extraction:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve document '{document_id}' without an extraction result.",
        )

    # Run validation
    val_res = validator.validate(extraction, doc.extracted_text or "", db)
    if not val_res.can_approve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Document cannot be approved because validation checks failed.",
                "issues": val_res.issues,
                "warnings": val_res.warnings,
            },
        )

    # Check if already approved into ledger
    existing_entry_stmt = select(LedgerEntry).where(LedgerEntry.document_id == document_id)
    existing_entry = db.execute(existing_entry_stmt).scalars().first()

    if existing_entry:
        return {
            "status": "already_approved",
            "message": "Document is already in the ledger.",
            "ledger_entry": LedgerEntryResponse.model_validate(existing_entry),
            "document": DocumentResponse.model_validate(doc),
        }

    # Create approved LedgerEntry
    ledger_entry = LedgerEntry(
        document_id=doc.id,
        vendor=extraction.vendor or "Unknown",
        document_number=extraction.invoice_number,
        date=extraction.date,
        currency=(extraction.currency or "USD").upper(),
        subtotal=extraction.subtotal,
        tax=extraction.tax,
        total=extraction.total,
        category=extraction.category or "Other",
        approval_timestamp=datetime.now(timezone.utc),
        edits_count=val_res.edits_count,
        is_demo=False,
    )
    db.add(ledger_entry)

    # Update document status
    doc.processing_status = ProcessingStatus.APPROVED
    doc.review_status = ReviewStatus.APPROVED
    db.commit()
    db.refresh(ledger_entry)
    db.refresh(doc)

    return {
        "status": "approved",
        "message": "Record approved and committed to the ledger.",
        "ledger_entry": LedgerEntryResponse.model_validate(ledger_entry),
        "document": DocumentResponse.model_validate(doc),
    }


@router.post("/{document_id}/reject", status_code=status.HTTP_200_OK)
def reject_document(
    document_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Reject a document without adding it to the ledger."""
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found.")

    doc.review_status = ReviewStatus.REJECTED
    db.commit()
    db.refresh(doc)

    return {
        "status": "rejected",
        "message": f"Document '{doc.original_filename}' has been marked as rejected.",
        "document": DocumentResponse.model_validate(doc),
    }
