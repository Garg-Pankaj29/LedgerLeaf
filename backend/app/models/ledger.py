"""Ledger entry database model."""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.database import Base

if TYPE_CHECKING:
    from backend.app.models.document import Document


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LedgerEntry(Base):
    """Represents an approved, immutable-by-default ledger record ready for accounting export."""

    __tablename__ = "ledger_entries"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    document_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    vendor: Mapped[str] = mapped_column(String(255), nullable=False)
    document_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    currency: Mapped[str] = mapped_column(String(3), nullable=False)  # USD, EUR, GBP, INR

    # Monetary values in integer minor units (paise/cents)
    subtotal: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tax: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total: Mapped[int] = mapped_column(Integer, nullable=False)

    category: Mapped[str] = mapped_column(String(100), nullable=False)

    approval_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    edits_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    # Relationship
    document: Mapped[Optional["Document"]] = relationship(
        "Document",
        back_populates="ledger_entries",
    )

    def __repr__(self) -> str:
        return (
            f"<LedgerEntry(id={self.id}, vendor={self.vendor}, "
            f"date={self.date}, total={self.total} {self.currency})>"
        )
