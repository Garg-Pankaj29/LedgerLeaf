"""Deterministic financial document validation rules and guard checks."""

import re
from datetime import datetime
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.app.models.extraction import ExtractionResult
from backend.app.models.provenance import ValidationStatus
from backend.app.models.ledger import LedgerEntry
from backend.app.schemas.common import ValidationResultResponse
from backend.app.schemas.money import from_minor_units

# Rule-based category matching keywords
CATEGORY_RULES = [
    ("Software", r"software|licen[cs]e|subscription|hosting|domain|cloud|saas|github|aws|digital"),
    ("Meals", r"coffee|latte|cafe|restaurant|lunch|dinner|food|bakery|croissant|breakfast|bistro|diner|meal"),
    ("Travel", r"cab|taxi|ride|flight|hotel|train|uber|lyft|airline|rail|fare|transit|airport"),
    ("Office", r"paper|printer|desk|stationery|supplies|hardware|office|postage"),
    ("Services", r"consult|design|freelance|service|legal|accounting|contractor|maintenance"),
]

STANDARD_CURRENCIES = {"USD", "EUR", "GBP", "INR", "CAD", "AUD", "SGD", "CHF", "JPY", "KRW"}


class ValidationService:
    """Performs deterministic verification on extracted document fields."""

    @staticmethod
    def suggest_category(text: str) -> Optional[str]:
        """Suggest a category based on keyword analysis of document text."""
        if not text:
            return None
        for cat, pattern in CATEGORY_RULES:
            if re.search(pattern, text, re.IGNORECASE):
                return cat
        return None

    def validate(
        self,
        extraction: ExtractionResult,
        raw_text: str = "",
        db_session: Optional[Session] = None,
    ) -> ValidationResultResponse:
        """
        Run deterministic rules against an ExtractionResult.
        Never alters numerical values to force math to balance.
        """
        issues: List[str] = []
        warnings: List[str] = []

        curr = (extraction.currency or "USD").upper()

        # 1. Required fields
        if not extraction.vendor or not extraction.vendor.strip():
            issues.append("Vendor is missing. Enter it from the document.")

        if not extraction.date or not extraction.date.strip():
            issues.append("Date is missing. Enter it from the document.")
        else:
            # 2. Date format and validity
            d = extraction.date.strip()
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", d):
                issues.append("Date must be formatted as YYYY-MM-DD.")
            else:
                try:
                    datetime.strptime(d, "%Y-%m-%d")
                except ValueError:
                    issues.append("Date must be a real calendar date like 2026-10-03.")

        if not extraction.currency or not extraction.currency.strip():
            issues.append("Currency is missing. Specify a 3-letter currency code (e.g. USD, EUR, INR).")
        elif curr not in STANDARD_CURRENCIES and len(curr) != 3:
            warnings.append(f"Currency '{curr}' is non-standard. Verify against the document.")

        if extraction.total is None:
            issues.append("Total is missing. Enter it from the document.")
        elif extraction.total < 0:
            issues.append("Total must be a non-negative amount.")

        if extraction.subtotal is not None and extraction.subtotal < 0:
            issues.append("Subtotal must be a non-negative amount.")

        if extraction.tax is not None and extraction.tax < 0:
            issues.append("Tax must be a non-negative amount.")

        # 3. Subtotal + Tax vs Total (Math Guard)
        s_minor = extraction.subtotal
        t_minor = extraction.tax
        tot_minor = extraction.total

        if s_minor is not None and t_minor is not None and tot_minor is not None:
            sum_minor = s_minor + t_minor
            diff_minor = abs(sum_minor - tot_minor)
            # Allow at most 1 minor unit tolerance for rounding (1 cent / 1 paise)
            if diff_minor > 1:
                s_dec = from_minor_units(s_minor, curr)
                t_dec = from_minor_units(t_minor, curr)
                tot_dec = from_minor_units(tot_minor, curr)
                exp_dec = from_minor_units(sum_minor, curr)
                diff_dec = from_minor_units(diff_minor, curr)
                issues.append(
                    f"Math guard: subtotal {s_dec:.2f} + tax {t_dec:.2f} = {exp_dec:.2f}, "
                    f"but total reads {tot_dec:.2f} (off by {diff_dec:.2f}). Check the document."
                )
        elif tot_minor is not None and (s_minor is None or t_minor is None):
            warnings.append("Subtotal or tax is missing, so the total cannot be cross-checked.")

        # 4. Category check & suggestions
        suggested: Optional[str] = None
        if not extraction.category or not extraction.category.strip():
            suggested = self.suggest_category(f"{extraction.vendor or ''} {extraction.description or ''} {raw_text}")
            issues.append("Category is missing. Choose a category.")
            if suggested:
                warnings.append(f"Category suggestion: consider '{suggested}'.")

        # 5. Duplicate warnings
        if db_session and extraction.vendor and extraction.date and tot_minor is not None:
            dup_stmt = select(LedgerEntry).where(
                LedgerEntry.vendor.ilike(extraction.vendor.strip()),
                LedgerEntry.date == extraction.date.strip(),
                LedgerEntry.total == tot_minor,
            )
            existing_entry = db_session.execute(dup_stmt).scalars().first()
            if existing_entry:
                warnings.append(
                    f"Likely duplicate: an approved ledger record for '{extraction.vendor}' "
                    f"on {extraction.date} for {curr} {from_minor_units(tot_minor, curr):.2f} already exists."
                )

        # 6. Uncertain extraction & user edits count
        edits_count = 0
        if extraction.field_provenances:
            for prov in extraction.field_provenances:
                if prov.is_user_edited:
                    edits_count += 1
                if prov.validation_status == ValidationStatus.WARNING:
                    warnings.append(f"Field '{prov.field_name}' had uncertain extraction confidence.")

        can_approve = (len(issues) == 0)

        return ValidationResultResponse(
            is_valid=can_approve,
            can_approve=can_approve,
            issues=issues,
            warnings=warnings,
            suggested_category=suggested,
            edits_count=edits_count,
        )
