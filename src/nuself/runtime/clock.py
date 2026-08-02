"""Neutral UTC clock helpers shared across NuSelf domains."""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return the current time as an aware UTC datetime."""
    return datetime.now(UTC)


def utc_now_iso() -> str:
    """Return the current aware UTC time in ISO-8601 form."""
    return utc_now().isoformat()
