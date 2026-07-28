"""Tests for NotificationDeliveryLoop."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

import nuself.notification as notification_module
from nuself.logs import read_log_events
from nuself.notification import (
    LogOnlyNotificationAdapter,
    NotificationDeliveryLoop,
    NotificationOutbox,
    OutboxEntry,
)
from nuself.notification.email import EmailNotificationAdapter
from nuself.runtime.context import (
    RuntimeContext,
    current_runtime_context,
    runtime_context,
)
from nuself.storage import (
    FileStorageBackend,
    StorageBackend,
    StorageCollection,
)


class FakeAdapter:
    """Test adapter that records deliveries and can be configured to fail."""

    def __init__(self, succeed: bool = True) -> None:
        self.succeed = succeed
        self.sent_entries: list[OutboxEntry] = []
        self.contexts: list[RuntimeContext] = []

    def send(self, entry: OutboxEntry) -> bool:
        self.sent_entries.append(entry)
        self.contexts.append(current_runtime_context())
        return self.succeed


class DeleteFailingCollection:
    def __init__(self, delegate: StorageCollection) -> None:
        self._delegate = delegate

    def get(self, key: str) -> dict[str, object] | None:
        return self._delegate.get(key)

    def put(self, key: str, value: dict[str, object]) -> None:
        self._delegate.put(key, value)

    def delete(self, key: str) -> None:
        raise OSError(f"delete unavailable for {key}")

    def list(self) -> tuple[dict[str, object], ...]:
        return self._delegate.list()

    def find(self, **filters: object) -> tuple[dict[str, object], ...]:
        return self._delegate.find(**filters)


class DeleteFailingBackend:
    def __init__(self, root: Path) -> None:
        delegate = FileStorageBackend(root)
        self._delegate = delegate
        self._outbox = DeleteFailingCollection(
            delegate.collection("notification_outbox")
        )

    def collection(self, name: str) -> StorageCollection:
        if name == "notification_outbox":
            return self._outbox
        return self._delegate.collection(name)

    def transaction(self) -> AbstractContextManager[None]:
        return self._delegate.transaction()


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


def test_outbox_context_round_trip_and_legacy_decode(
    tmp_path: Path,
) -> None:
    with runtime_context(
        request_id="request-1",
        thread_id="thread-1",
        turn_id="turn-1",
        trace_id="trace-1",
        source="reflection",
    ):
        entry = OutboxEntry(
            id="context",
            title="Context",
            body="Body",
            status="pending",
            idempotency_key="context",
        )

    outbox = NotificationOutbox(tmp_path)
    outbox.add(entry)
    stored = outbox.get(entry.id)

    assert stored.context == entry.context
    assert outbox.mark_sent(entry.id).context == entry.context
    assert outbox.dismiss(entry.id).context == entry.context

    legacy = entry.to_wire()
    legacy.pop("context")
    assert OutboxEntry.from_wire(legacy).context == RuntimeContext()


def test_delivery_activates_entry_context_and_restores_ambient(
    tmp_path: Path,
) -> None:
    with runtime_context(
        request_id="origin-request",
        thread_id="origin-thread",
        turn_id="origin-turn",
        trace_id="origin-trace",
        source="reflection",
    ):
        entry = OutboxEntry(
            id="correlated",
            title="T",
            body="B",
            status="pending",
            idempotency_key="correlated",
        )
    NotificationOutbox(tmp_path).add(entry)
    adapter = FakeAdapter()
    loop = NotificationDeliveryLoop(tmp_path, adapters=[adapter])

    with runtime_context(
        request_id="ambient-request",
        source="test",
    ):
        assert loop.run_once() == 1
        assert current_runtime_context() == RuntimeContext(
            request_id="ambient-request",
            source="test",
        )

    assert adapter.contexts == [
        RuntimeContext(
            request_id="origin-request",
            thread_id="origin-thread",
            turn_id="origin-turn",
            trace_id="origin-trace",
            source="daemon.worker.notification_delivery",
        )
    ]


def test_delivery_log_projects_origin_correlation(
    tmp_path: Path,
) -> None:
    with runtime_context(
        request_id="notification-request",
        thread_id="notification-thread",
    ):
        entry = OutboxEntry(
            id="logged",
            title="T",
            body="B",
            status="pending",
            idempotency_key="logged",
        )
    NotificationOutbox(tmp_path).add(entry)

    NotificationDeliveryLoop(
        tmp_path,
        adapters=[LogOnlyNotificationAdapter(tmp_path)],
    ).run_once()

    event = read_log_events(
        project_root=tmp_path,
        component="outbox",
    )[-1]
    assert event.request_id == "notification-request"
    assert event.thread_id == "notification-thread"
    assert event.source == "daemon.worker.notification_delivery"


def test_delivery_restores_context_when_adapter_raises(
    tmp_path: Path,
) -> None:
    class RaisingAdapter:
        def send(self, entry: OutboxEntry) -> bool:
            del entry
            raise RuntimeError("adapter crashed")

    NotificationOutbox(tmp_path).add(
        OutboxEntry(
            id="raising",
            title="T",
            body="B",
            status="pending",
            idempotency_key="raising",
            context=RuntimeContext(request_id="origin"),
        )
    )
    loop = NotificationDeliveryLoop(
        tmp_path,
        adapters=[RaisingAdapter()],
    )

    with runtime_context(request_id="ambient"):
        with pytest.raises(RuntimeError, match="adapter crashed"):
            loop.run_once()
        assert current_runtime_context() == RuntimeContext(
            request_id="ambient"
        )


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


def test_failure_diagnostic_store_cannot_prevent_failed_transition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("audit store unavailable")

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    outbox = NotificationOutbox(tmp_path)
    outbox.add(
        OutboxEntry(
            id="email-no-config",
            title="T",
            body="B",
            status="pending",
            idempotency_key="email-no-config",
        )
    )
    loop = NotificationDeliveryLoop(
        tmp_path,
        adapters=[
            EmailNotificationAdapter(tmp_path, dry_run=False)
        ],
    )

    with pytest.warns(
        RuntimeWarning,
        match="outbox/email_no_config",
    ):
        delivered = loop.run_once()

    assert delivered == 0
    [failed] = outbox.list(status="failed")
    assert failed.id == "email-no-config"
    assert failed.attempts == 1
    assert outbox.list(status="pending") == []


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


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("created_at", "not-a-timestamp"),
        ("created_at", "2026-01-01T00:00:00"),
        ("sent_at", "2026-01-01T00:00:00"),
        ("sent_at", 42),
    ),
)
def test_outbox_list_isolates_invalid_persisted_timestamps(
    tmp_path: Path,
    field_name: str,
    value: object,
) -> None:
    backend = FileStorageBackend(tmp_path / "private")
    wire = OutboxEntry(
        id="corrupt-time",
        title="Private title",
        body="Private body",
        status="dismissed",
        idempotency_key="corrupt-time",
    ).to_wire()
    wire[field_name] = value
    backend.collection("notification_outbox").put("corrupt-time", wire)
    outbox = NotificationOutbox(tmp_path, backend=backend)

    assert outbox.list() == []

    event = read_log_events(project_root=tmp_path, component="outbox")[-1]
    assert event.event == "record_decode_failed"
    assert event.metadata == {
        "collection": "notification_outbox",
        "record_id": "corrupt-time",
    }
    assert "Private title" not in str(event.to_record())
    assert "Private body" not in str(event.to_record())
    with pytest.raises(ValueError):
        outbox.get("corrupt-time")


def test_outbox_list_isolates_invalid_present_context(
    tmp_path: Path,
) -> None:
    backend = FileStorageBackend(tmp_path / "private")
    wire = OutboxEntry(
        id="corrupt-context",
        title="Private title",
        body="Private body",
        status="pending",
        idempotency_key="corrupt-context",
    ).to_wire()
    wire["context"] = {"unknown": "value"}
    backend.collection("notification_outbox").put(
        "corrupt-context",
        wire,
    )
    outbox = NotificationOutbox(tmp_path, backend=backend)

    assert outbox.list() == []
    with pytest.raises(ValueError, match="unknown fields"):
        outbox.get("corrupt-context")


@pytest.mark.parametrize("days", (-1, True, 1.5))
def test_outbox_clear_rejects_invalid_retention_days(
    tmp_path: Path,
    days: object,
) -> None:
    outbox = NotificationOutbox(tmp_path)

    with pytest.raises(
        ValueError,
        match="retention days must be a non-negative integer",
    ):
        outbox.clear_dismissed_older_than(cast(int, days))


def test_outbox_clear_propagates_delete_failure(tmp_path: Path) -> None:
    backend: StorageBackend = DeleteFailingBackend(tmp_path / "private")
    outbox = NotificationOutbox(tmp_path, backend=backend)
    outbox.add(
        OutboxEntry(
            id="old",
            title="Old",
            body="B",
            status="dismissed",
            idempotency_key="old",
            created_at=(
                datetime.now(UTC) - timedelta(days=10)
            ).isoformat(),
        )
    )

    with pytest.raises(OSError, match="delete unavailable for old"):
        outbox.clear_dismissed_older_than(days=7)


def test_outbox_clear_retains_entry_exactly_at_cutoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 28, 12, tzinfo=UTC)
    monkeypatch.setattr(notification_module, "utc_now", lambda: now)
    outbox = NotificationOutbox(tmp_path)
    at_cutoff = OutboxEntry(
        id="at-cutoff",
        title="At cutoff",
        body="B",
        status="dismissed",
        idempotency_key="at-cutoff",
        created_at=(now - timedelta(days=7)).isoformat(),
    )
    before_cutoff = OutboxEntry(
        id="before-cutoff",
        title="Before cutoff",
        body="B",
        status="dismissed",
        idempotency_key="before-cutoff",
        created_at=(
            now - timedelta(days=7, microseconds=1)
        ).isoformat(),
    )
    outbox.add(at_cutoff)
    outbox.add(before_cutoff)

    assert outbox.clear_dismissed_older_than(days=7) == 1
    assert outbox.list(status="dismissed") == [at_cutoff]


def test_delivery_loop_auto_clears_old_dismissed_entries(tmp_path: Path) -> None:
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
