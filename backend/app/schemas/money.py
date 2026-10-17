"""Monetary value utilities for storing minor units (cents, paise) without floating-point drift."""

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Union

# Minor unit scale: 1 major unit = 10^decimals minor units
CURRENCY_DECIMALS = {
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
    "INR": 2,
    "CAD": 2,
    "AUD": 2,
    "SGD": 2,
    "CHF": 2,
    "JPY": 0,
    "KRW": 0,
}


def to_minor_units(
    amount: Optional[Union[float, int, Decimal, str]],
    currency: str = "USD",
) -> Optional[int]:
    """
    Convert a monetary value (e.g. 9.72 or "9.72") to integer minor units (e.g. 972 cents).
    Returns None if the amount is None or an empty string, supporting missing fields without inventing values.
    """
    if amount is None:
        return None
    if isinstance(amount, str):
        cleaned = amount.replace(",", "").strip()
        if not cleaned:
            return None
        val = Decimal(cleaned)
    else:
        val = Decimal(str(amount))

    decimals = CURRENCY_DECIMALS.get(currency.upper(), 2)
    multiplier = Decimal(10 ** decimals)
    return int((val * multiplier).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def from_minor_units(
    minor_units: Optional[int],
    currency: str = "USD",
) -> Optional[Decimal]:
    """
    Convert integer minor units (e.g. 972 cents) back to a Decimal major amount (e.g. 9.72).
    Returns None if minor_units is None.
    """
    if minor_units is None:
        return None
    decimals = CURRENCY_DECIMALS.get(currency.upper(), 2)
    divisor = Decimal(10 ** decimals)
    return (Decimal(minor_units) / divisor).quantize(Decimal(f"1e-{decimals}"))


def format_currency_amount(
    minor_units: Optional[int],
    currency: str = "USD",
) -> Optional[str]:
    """Format minor units as a formatted decimal string (e.g. "9.72")."""
    amount = from_minor_units(minor_units, currency)
    if amount is None:
        return None
    decimals = CURRENCY_DECIMALS.get(currency.upper(), 2)
    return f"{amount:.{decimals}f}"
