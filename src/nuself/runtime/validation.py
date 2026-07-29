"""Shared validation for runtime control values."""

from __future__ import annotations

from math import isfinite


def validate_timeout(
    value: float | None,
    *,
    field_name: str,
    allow_none: bool,
) -> float | None:
    """Return one finite non-negative timeout or raise a stable error."""

    if value is None:
        if allow_none:
            return None
        raise ValueError(f"{field_name} must be finite and non-negative")
    if (
        isinstance(value, bool)
        or type(value) not in {int, float}
        or not isfinite(value)
        or value < 0
    ):
        raise ValueError(f"{field_name} must be finite and non-negative")
    return float(value)
