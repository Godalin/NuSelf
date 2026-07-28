"""Tests for notification outbox and log-only adapter."""

from __future__ import annotations

from pathlib import Path

from nuself.notification import (
    LogOnlyNotificationAdapter,
    NotificationOutbox,
    OutboxEntry,
    OutboxEntryNotFound,
)


def test_outbox_add_and_list(tmp_path: Path) -> None:
    outbox = NotificationOutbox(tmp_path)
    entry = outbox.add(
        OutboxEntry(
            id="e1",
            title="Test",
            body="Hello",
            status="pending",
            idempotency_key="key-1",
        )
    )
    assert entry.id == "e1"
    assert outbox.list() == [entry]


def test_outbox_add_deduplicates_by_idempotency_key(tmp_path: Path) -> None:
    outbox = NotificationOutbox(tmp_path)
    first = outbox.add(
        OutboxEntry(
            id="e1",
            title="First",
            body="Hello",
            status="pending",
            idempotency_key="key-1",
        )
    )
    second = outbox.add(
        OutboxEntry(
            id="e2",
            title="Second",
            body="World",
            status="pending",
            idempotency_key="key-1",
        )
    )
    assert second.id == "e1"
    assert outbox.list() == [first]


def test_outbox_mark_sent(tmp_path: Path) -> None:
    outbox = NotificationOutbox(tmp_path)
    outbox.add(
        OutboxEntry(id="e1", title="T", body="B", status="pending", idempotency_key="k")
    )
    updated = outbox.mark_sent("e1")
    assert updated.status == "sent"
    assert updated.attempts == 1
    assert updated.sent_at is not None


def test_outbox_mark_failed(tmp_path: Path) -> None:
    outbox = NotificationOutbox(tmp_path)
    outbox.add(
        OutboxEntry(id="e1", title="T", body="B", status="pending", idempotency_key="k")
    )
    updated = outbox.mark_failed("e1")
    assert updated.status == "failed"
    assert updated.attempts == 1


def test_outbox_dismiss(tmp_path: Path) -> None:
    outbox = NotificationOutbox(tmp_path)
    outbox.add(
        OutboxEntry(id="e1", title="T", body="B", status="pending", idempotency_key="k")
    )
    updated = outbox.dismiss("e1")
    assert updated.status == "dismissed"


def test_outbox_get_missing_raises(tmp_path: Path) -> None:
    outbox = NotificationOutbox(tmp_path)
    try:
        outbox.get("missing")
        raise AssertionError("expected OutboxEntryNotFound")
    except OutboxEntryNotFound as exc:
        assert "missing" in str(exc)


def test_outbox_list_filters_by_status(tmp_path: Path) -> None:
    outbox = NotificationOutbox(tmp_path)
    outbox.add(
        OutboxEntry(id="e1", title="A", body="B", status="pending", idempotency_key="k1")
    )
    outbox.add(
        OutboxEntry(id="e2", title="C", body="D", status="sent", idempotency_key="k2")
    )
    pending = outbox.list(status="pending")
    assert len(pending) == 1
    assert pending[0].id == "e1"


def test_log_only_adapter_sends(tmp_path: Path) -> None:
    outbox = NotificationOutbox(tmp_path)
    entry = outbox.add(
        OutboxEntry(id="e1", title="T", body="B", status="pending", idempotency_key="k")
    )
    adapter = LogOnlyNotificationAdapter(tmp_path)
    assert adapter.send(entry)
    log_path = tmp_path / "private" / "logs" / "outbox.log"
    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert '"event": "outbox_delivered"' in content
    assert '"entry_id": "e1"' in content
    assert '"status": "delivered"' in content
    assert "T: B" not in content
    assert '"idempotency_key"' not in content
    assert "e1" in content


def test_outbox_round_trip_wire_format(tmp_path: Path) -> None:
    outbox = NotificationOutbox(tmp_path)
    original = OutboxEntry(
        id="e1",
        title="Title",
        body="Body",
        status="pending",
        idempotency_key="k",
        deep_link="nuself://thread-1",
    )
    outbox.add(original)
    loaded = outbox.get("e1")
    assert loaded.title == "Title"
    assert loaded.body == "Body"
    assert loaded.deep_link == "nuself://thread-1"
