# pyright: reportPrivateUsage=false
"""Tests for notification outbox and log-only adapter."""

from __future__ import annotations

import multiprocessing
from multiprocessing.context import SpawnContext
from multiprocessing.synchronize import Event
from pathlib import Path

from nuself.notification import (
    LogOnlyNotificationAdapter,
    NotificationOutbox,
    OutboxEntry,
    OutboxEntryNotFound,
)


class _PausingNotificationOutbox(NotificationOutbox):
    def __init__(
        self,
        project_root: Path,
        *,
        scanned: Event,
        release: Event,
    ) -> None:
        super().__init__(project_root)
        self._scanned = scanned
        self._release = release

    def _find_by_idempotency_key(self, key: str) -> OutboxEntry | None:
        existing = super()._find_by_idempotency_key(key)
        self._scanned.set()
        if not self._release.wait(timeout=10):
            raise RuntimeError("parent did not release outbox admission")
        return existing


def _pause_during_outbox_add(
    project_root: str,
    scanned: Event,
    release: Event,
) -> None:
    outbox = _PausingNotificationOutbox(
        Path(project_root),
        scanned=scanned,
        release=release,
    )
    outbox.add(
        OutboxEntry(
            id="first",
            title="First",
            body="First body",
            status="pending",
            idempotency_key="shared-key",
        )
    )


def _add_competing_outbox_entry(
    project_root: str,
    attempted: Event,
    done: Event,
) -> None:
    attempted.set()
    NotificationOutbox(Path(project_root)).add(
        OutboxEntry(
            id="second",
            title="Second",
            body="Second body",
            status="pending",
            idempotency_key="shared-key",
        )
    )
    done.set()


def _spawn_context() -> SpawnContext:
    return multiprocessing.get_context("spawn")


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


def test_outbox_add_is_idempotent_across_processes(tmp_path: Path) -> None:
    context = _spawn_context()
    scanned = context.Event()
    release = context.Event()
    attempted = context.Event()
    done = context.Event()
    first = context.Process(
        target=_pause_during_outbox_add,
        args=(str(tmp_path), scanned, release),
    )
    second = context.Process(
        target=_add_competing_outbox_entry,
        args=(str(tmp_path), attempted, done),
    )
    first.start()
    assert scanned.wait(timeout=10)
    second.start()
    try:
        assert attempted.wait(timeout=10)
        assert not done.wait(timeout=0.2)
    finally:
        release.set()
        first.join(timeout=10)
        second.join(timeout=10)
        for process in (first, second):
            if process.is_alive():
                process.terminate()
                process.join(timeout=10)

    assert first.exitcode == 0
    assert second.exitcode == 0
    entries = NotificationOutbox(tmp_path).list()
    assert len(entries) == 1
    assert entries[0].id == "first"


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
