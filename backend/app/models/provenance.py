"""Field provenance database model."""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, Optional
from sqlalchemy import String, Integer, Boolean, DateTime, Text, JSON, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.database import Base

if TYPE_CHECKING:
    from backend.app.models.extraction import ExtractionResult


class ValidationStatus(str, Enum):
    VALID = "valid"
    WARNING = "warning"
    ERROR = "error"
    MISSING = "missing"


class ExtractionSource(str, Enum):
    RULE_BASED = "rule_based"
    AI_MODEL = "ai_model"
    USER_INPUT = "user_input"
    RULE_GUESS = "rule_guess"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FieldProvenance(Base):
    """Tracks origin, source snippet/location, user overrides, and verification status for each field."""

    __tablename__ = "field_provenance"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    extraction_result_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("extraction_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    field_name: Mapped[str] = mapped_column(String(50), nullable=False)  # vendor, date, total, etc.
    extracted_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Source location within document text or PDF/Image coordinates
    source_snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    start_offset: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    end_offset: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bounding_box: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Provenance source & user review tracking
    extraction_source: Mapped[ExtractionSource] = mapped_column(
        SQLEnum(ExtractionSource, name="extraction_source_enum", native_enum=False),
        default=ExtractionSource.RULE_BASED,
        nullable=False,
    )
    is_user_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    user_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    validation_status: Mapped[ValidationStatus] = mapped_column(
        SQLEnum(ValidationStatus, name="validation_status_enum", native_enum=False),
        default=ValidationStatus.VALID,
        nullable=False,
    )

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

    # Relationship
    extraction_result: Mapped["ExtractionResult"] = relationship(
        "ExtractionResult",
        back_populates="field_provenances",
    )

    def __repr__(self) -> str:
        return (
            f"<FieldProvenance(id={self.id}, field={self.field_name}, "
            f"edited={self.is_user_edited}, status={self.validation_status})>"
        )
