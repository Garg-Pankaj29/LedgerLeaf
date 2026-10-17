"""Document database model."""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import String, Integer, DateTime, Text, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.database import Base

if TYPE_CHECKING:
    from backend.app.models.extraction import ExtractionResult
    from backend.app.models.ledger import LedgerEntry


class ProcessingStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"
    APPROVED = "approved"
    # Aliases for backward compatibility
    PENDING = "uploaded"
    COMPLETED = "needs_review"


class ReviewStatus(str, Enum):
    UNREVIEWED = "unreviewed"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Document(Base):
    """Represents an uploaded financial document (receipt, invoice, statement)."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(100), nullable=False)  # MIME type
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)  # Size in bytes
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    processing_status: Mapped[ProcessingStatus] = mapped_column(
        SQLEnum(ProcessingStatus, name="processing_status_enum", native_enum=False),
        default=ProcessingStatus.UPLOADED,
        nullable=False,
        index=True,
    )
    review_status: Mapped[ReviewStatus] = mapped_column(
        SQLEnum(ReviewStatus, name="review_status_enum", native_enum=False),
        default=ReviewStatus.UNREVIEWED,
        nullable=False,
        index=True,
    )

    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    # Relationships
    extractions: Mapped[List["ExtractionResult"]] = relationship(
        "ExtractionResult",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="desc(ExtractionResult.created_at)",
    )
    ledger_entries: Mapped[List["LedgerEntry"]] = relationship(
        "LedgerEntry",
        back_populates="document",
    )

    def __repr__(self) -> str:
        return (
            f"<Document(id={self.id}, name={self.original_filename}, "
            f"status={self.processing_status}, review={self.review_status})>"
        )
