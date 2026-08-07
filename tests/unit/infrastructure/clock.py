from datetime import UTC, datetime

from nuself.runtime.clock import utc_now, utc_now_iso


def test_utc_now_returns_aware_utc_datetime() -> None:
    current = utc_now()

    assert current.tzinfo is UTC


def test_utc_now_iso_round_trips_as_aware_utc_datetime() -> None:
    parsed = datetime.fromisoformat(utc_now_iso())

    assert parsed.tzinfo is UTC
