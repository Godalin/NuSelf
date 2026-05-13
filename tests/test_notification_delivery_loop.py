"""Tests for NotificationDeliveryLoop."""

from __future__ import annotations

from pathlib import Path

from nuself.notification import (
    NotificationDeliveryLoop,
    NotificationOutbox,
    OutboxEntry,
)


class FakeAdapter:
    """Test adapter that records deliveries and can be configured to fail."""

    def __init__(self, succeed: bool = True) -> None:
        self.succeed = succeed
        self.sent_entries: list[OutboxEntry] = []

    def send(self, entry: OutboxEntry) -> bool:
        self.sent_entries.append(entry)
        return self.succeed


def test_delivery_loop_sends_pending_entries(tmp_path: Path) -> None:
    outbox = NotificationOutbox(tmp_path)
    outbox.add(OutboxEntry(id="e1", title="T1", body="B1", status="pending", idempotency_key="k1"))
    outbox.add(OutboxEntry(id="e2", title="T2", body="B2", status="pending", idempotency_key="k2"))

    adapter = FakeAdapter(succeed=True)
    loop = NotificationDeliveryLoop(tmp_path, adapters=[adapter])
    delivered = loop.run_once()

    assert delivered == 2
    assert len(adapter.sent_entries) == 2
    assert len(outbox.list(status="sent")) == 2


def test_delivery_loop_marks_failed_on_adapter_failure(tmp_path: Path) -> None:
    outbox = NotificationOutbox(tmp_path)
    outbox.add(OutboxEntry(id="e1", title="T1", body="B1", status="pending", idempotency_key="k1"))

    adapter = FakeAdapter(succeed=False)
    loop = NotificationDeliveryLoop(tmp_path, adapters=[adapter])
    delivered = loop.run_once()

    assert delivered == 0
    assert len(adapter.sent_entries) == 1
    failed = outbox.list(status="failed")
    assert len(failed) == 1
    assert failed[0].attempts == 1


def test_delivery_loop_skips_non_pending(tmp_path: Path) -> None:
    outbox = NotificationOutbox(tmp_path)
    outbox.add(OutboxEntry(id="e1", title="T1", body="B1", status="sent", idempotency_key="k1"))

    adapter = FakeAdapter(succeed=True)
    loop = NotificationDeliveryLoop(tmp_path, adapters=[adapter])
    delivered = loop.run_once()

    assert delivered == 0
    assert len(adapter.sent_entries) == 0


def test_delivery_loop_all_adapters_must_succeed(tmp_path: Path) -> None:
    outbox = NotificationOutbox(tmp_path)
    outbox.add(OutboxEntry(id="e1", title="T1", body="B1", status="pending", idempotency_key="k1"))

    good = FakeAdapter(succeed=True)
    bad = FakeAdapter(succeed=False)
    loop = NotificationDeliveryLoop(tmp_path, adapters=[good, bad])
    delivered = loop.run_once()

    assert delivered == 0
    assert len(good.sent_entries) == 1
    assert len(bad.sent_entries) == 1
    assert len(outbox.list(status="failed")) == 1


def test_outbox_clear_dismissed_older_than_removes_old_entries(tmp_path: Path) -> None:
    from datetime import UTC, datetime, timedelta

    outbox = NotificationOutbox(tmp_path)
    old = OutboxEntry(
        id="old",
        title="Old",
        body="B",
        status="dismissed",
        idempotency_key="old",
        created_at=(datetime.now(UTC) - timedelta(days=10)).isoformat(),
    )
    recent = OutboxEntry(
        id="recent",
        title="Recent",
        body="B",
        status="dismissed",
        idempotency_key="recent",
        created_at=(datetime.now(UTC) - timedelta(days=3)).isoformat(),
    )
    outbox.add(old)
    outbox.add(recent)

    removed = outbox.clear_dismissed_older_than(days=7)

    assert removed == 1
    assert outbox.list(status="dismissed") == [recent]


def test_delivery_loop_auto_clears_old_dismissed_entries(tmp_path: Path) -> None:
    from datetime import UTC, datetime, timedelta

    outbox = NotificationOutbox(tmp_path)
    outbox.add(OutboxEntry(id="pending1", title="P", body="B", status="pending", idempotency_key="p1"))
    old_dismissed = OutboxEntry(
        id="old_dismissed",
        title="Old",
        body="B",
        status="dismissed",
        idempotency_key="od",
        created_at=(datetime.now(UTC) - timedelta(days=10)).isoformat(),
    )
    outbox.add(old_dismissed)

    adapter = FakeAdapter(succeed=True)
    loop = NotificationDeliveryLoop(tmp_path, adapters=[adapter])
    loop.run_once()

    assert outbox.list(status="dismissed") == []
