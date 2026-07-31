"""Tests for NotificationDeliveryLoop."""

from __future__ import annotations

from notification_fixtures import notification_outbox

from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta
import multiprocessing
from multiprocessing.context import SpawnContext
from multiprocessing.synchronize import Event
from pathlib import Path
from typing import cast

import pytest

import nuself.notification as notification_module
from nuself.logs import read_log_events
from nuself.config import runtime_paths
from nuself.notification import (
    LogOnlyNotificationAdapter,
    NotificationDeliveryLoop,
    OutboxEntry,
    deliver_entry_once,
)
from nuself.notification.email import EmailNotificationAdapter
from nuself.runtime.context import (
    RuntimeContext,
    current_runtime_context,
    runtime_context,
)
from nuself.storage import (
    auto_backend,
    StorageBackend,
    StorageCollection,
)


class FakeAdapter:
    """Test adapter that records deliveries and can be configured to fail."""

    def __init__(
        self,
        succeed: bool = True,
        *,
        delivery_id: str = "fake",
    ) -> None:
        self.succeed = succeed
        self.delivery_id = delivery_id
        self.sent_entries: list[OutboxEntry] = []
        self.contexts: list[RuntimeContext] = []

    def send(self, entry: OutboxEntry) -> bool:
        self.sent_entries.append(entry)
        self.contexts.append(current_runtime_context())
        return self.succeed


class _ProcessRecordingAdapter:
    delivery_id = "process"

    def __init__(
        self,
        effect_path: str,
        started: Event | None = None,
        release: Event | None = None,
    ) -> None:
        self._effect_path = Path(effect_path)
        self._started = started
        self._release = release

    def send(self, entry: OutboxEntry) -> bool:
        with self._effect_path.open("a", encoding="utf-8") as stream:
            stream.write(f"{entry.id}\n")
            stream.flush()
        if self._started is not None:
            self._started.set()
        if self._release is not None and not self._release.wait(timeout=10):
            raise RuntimeError("parent did not release notification adapter")
        return True


def _spawn_context() -> SpawnContext:
    return multiprocessing.get_context("spawn")


def _deliver_in_process(
    project_root: str,
    entry_id: str,
    effect_path: str,
    start: Event,
    started: Event | None = None,
    release: Event | None = None,
) -> None:
    if not start.wait(timeout=10):
        raise RuntimeError("parent did not start notification delivery")
    outbox = notification_outbox(Path(project_root))
    deliver_entry_once(
        outbox,
        entry_id,
        [
            _ProcessRecordingAdapter(
                effect_path,
                started=started,
                release=release,
            )
        ],
    )


def _dismiss_in_process(
    project_root: str,
    entry_id: str,
    attempted: Event,
    done: Event,
) -> None:
    attempted.set()
    notification_outbox(Path(project_root)).dismiss(entry_id)
    done.set()


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
        delegate = auto_backend(root)
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
    outbox = notification_outbox(tmp_path)
    outbox.add(OutboxEntry(id="e1", title="T1", body="B1", status="pending", idempotency_key="k1"))
    outbox.add(OutboxEntry(id="e2", title="T2", body="B2", status="pending", idempotency_key="k2"))

    adapter = FakeAdapter(succeed=True)
    loop = NotificationDeliveryLoop(notification_outbox(tmp_path), adapters=[adapter])
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

    outbox = notification_outbox(tmp_path)
    outbox.add(entry)
    stored = outbox.get(entry.id)

    assert stored.context == entry.context
    outbox.prepare_delivery(entry.id, ("log",))
    outbox.begin_adapter_delivery(entry.id, "log")
    outbox.record_adapter_result(entry.id, "log", success=True)
    assert outbox.finalize_delivery(entry.id).context == entry.context
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
    notification_outbox(tmp_path).add(entry)
    adapter = FakeAdapter()
    loop = NotificationDeliveryLoop(notification_outbox(tmp_path), adapters=[adapter])

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
    notification_outbox(tmp_path).add(entry)

    NotificationDeliveryLoop(
        notification_outbox(tmp_path),
        adapters=[LogOnlyNotificationAdapter(runtime_paths(tmp_path))],
    ).run_once()

    event = read_log_events(
        project_root=tmp_path,
        component="outbox",
    )[-1]
    assert event.request_id == "notification-request"
    assert event.thread_id == "notification-thread"
    assert event.source == "daemon.worker.notification_delivery"
    assert event.status == "delivered"
    assert event.metadata == {"entry_id": "logged", "attempt": 0}
    assert event.message == "Outbox notification delivered"


def test_delivery_restores_context_when_adapter_raises(
    tmp_path: Path,
) -> None:
    class RaisingAdapter:
        delivery_id = "raising"

        def send(self, entry: OutboxEntry) -> bool:
            del entry
            raise RuntimeError("adapter crashed")

    notification_outbox(tmp_path).add(
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
        notification_outbox(tmp_path),
        adapters=[RaisingAdapter()],
    )

    with runtime_context(request_id="ambient"):
        with pytest.raises(RuntimeError, match="adapter crashed"):
            loop.run_once()
        assert current_runtime_context() == RuntimeContext(
            request_id="ambient"
        )


def test_delivery_loop_marks_failed_on_adapter_failure(tmp_path: Path) -> None:
    outbox = notification_outbox(tmp_path)
    outbox.add(OutboxEntry(id="e1", title="T1", body="B1", status="pending", idempotency_key="k1"))

    adapter = FakeAdapter(succeed=False)
    loop = NotificationDeliveryLoop(notification_outbox(tmp_path), adapters=[adapter])
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
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        fail_log,
    )
    outbox = notification_outbox(tmp_path)
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
        notification_outbox(tmp_path),
        adapters=[
            EmailNotificationAdapter(tmp_path, dry_run=False)
        ],
    )

    with pytest.warns(
        RuntimeWarning,
        match="runtime/observability_sink_failed",
    ):
        delivered = loop.run_once()

    assert delivered == 0
    [failed] = outbox.list(status="failed")
    assert failed.id == "email-no-config"
    assert failed.attempts == 1
    assert outbox.list(status="pending") == []


def test_delivery_loop_skips_non_pending(tmp_path: Path) -> None:
    outbox = notification_outbox(tmp_path)
    outbox.add(OutboxEntry(id="e1", title="T1", body="B1", status="sent", idempotency_key="k1"))

    adapter = FakeAdapter(succeed=True)
    loop = NotificationDeliveryLoop(notification_outbox(tmp_path), adapters=[adapter])
    delivered = loop.run_once()

    assert delivered == 0
    assert len(adapter.sent_entries) == 0


def test_delivery_loop_all_adapters_must_succeed(tmp_path: Path) -> None:
    outbox = notification_outbox(tmp_path)
    outbox.add(OutboxEntry(id="e1", title="T1", body="B1", status="pending", idempotency_key="k1"))

    good = FakeAdapter(succeed=True, delivery_id="good")
    bad = FakeAdapter(succeed=False, delivery_id="bad")
    loop = NotificationDeliveryLoop(notification_outbox(tmp_path), adapters=[good, bad])
    delivered = loop.run_once()

    assert delivered == 0
    assert len(good.sent_entries) == 1
    assert len(bad.sent_entries) == 1
    [failed] = outbox.list(status="failed")
    assert failed.required_adapters == ("good", "bad")
    assert failed.deliveries["good"].status == "sent"
    assert failed.deliveries["good"].attempts == 1
    assert failed.deliveries["bad"].status == "failed"
    assert failed.deliveries["bad"].attempts == 1


def test_delivery_loop_marks_crash_after_send_uncertain_without_replay(
    tmp_path: Path,
) -> None:
    class RaisingAdapter:
        delivery_id = "second"

        def send(self, entry: OutboxEntry) -> bool:
            del entry
            raise RuntimeError("second adapter crashed")

    outbox = notification_outbox(tmp_path)
    outbox.add(
        OutboxEntry(
            id="resume",
            title="Resume",
            body="Do not repeat external effects.",
            status="pending",
            idempotency_key="resume",
        )
    )
    first = FakeAdapter(delivery_id="first")

    with pytest.raises(RuntimeError, match="second adapter crashed"):
        NotificationDeliveryLoop(
            notification_outbox(tmp_path),
            adapters=[first, RaisingAdapter()],
        ).run_once()

    interrupted = outbox.get("resume")
    assert interrupted.status == "pending"
    assert interrupted.deliveries["first"].status == "sent"
    assert interrupted.deliveries["second"].status == "delivering"
    assert len(first.sent_entries) == 1

    recovered_second = FakeAdapter(delivery_id="second")
    delivered = NotificationDeliveryLoop(
        notification_outbox(tmp_path),
        adapters=[first, recovered_second],
    ).run_once()

    assert delivered == 0
    assert len(first.sent_entries) == 1
    assert recovered_second.sent_entries == []
    completed = outbox.get("resume")
    assert completed.status == "failed"
    assert completed.deliveries["first"].attempts == 1
    assert completed.deliveries["second"].status == "uncertain"
    assert completed.deliveries["second"].attempts == 1


def test_cross_process_delivery_sends_one_external_effect(
    tmp_path: Path,
) -> None:
    outbox = notification_outbox(tmp_path)
    outbox.add(
        OutboxEntry(
            id="one-effect",
            title="One",
            body="Only once.",
            status="pending",
            idempotency_key="one-effect",
        )
    )
    effect_path = tmp_path / "effects.log"
    context = _spawn_context()
    start = context.Event()
    processes = [
        context.Process(
            target=_deliver_in_process,
            args=(
                str(tmp_path),
                "one-effect",
                str(effect_path),
                start,
            ),
        )
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    start.set()
    for process in processes:
        process.join(timeout=10)
        if process.is_alive():
            process.terminate()
            process.join(timeout=10)

    assert [process.exitcode for process in processes] == [0, 0]
    assert effect_path.read_text(encoding="utf-8").splitlines() == [
        "one-effect"
    ]
    assert outbox.get("one-effect").status == "sent"


def test_dismiss_waits_for_delivery_entry_lock(
    tmp_path: Path,
) -> None:
    outbox = notification_outbox(tmp_path)
    outbox.add(
        OutboxEntry(
            id="dismiss-race",
            title="Race",
            body="Serialize state.",
            status="pending",
            idempotency_key="dismiss-race",
        )
    )
    effect_path = tmp_path / "effects.log"
    context = _spawn_context()
    start = context.Event()
    adapter_started = context.Event()
    release_adapter = context.Event()
    dismiss_attempted = context.Event()
    dismiss_done = context.Event()
    delivery = context.Process(
        target=_deliver_in_process,
        args=(
            str(tmp_path),
            "dismiss-race",
            str(effect_path),
            start,
            adapter_started,
            release_adapter,
        ),
    )
    dismiss = context.Process(
        target=_dismiss_in_process,
        args=(
            str(tmp_path),
            "dismiss-race",
            dismiss_attempted,
            dismiss_done,
        ),
    )
    delivery.start()
    start.set()
    assert adapter_started.wait(timeout=10)
    dismiss.start()
    try:
        assert dismiss_attempted.wait(timeout=10)
        assert not dismiss_done.wait(timeout=0.2)
    finally:
        release_adapter.set()
        delivery.join(timeout=10)
        dismiss.join(timeout=10)
        for process in (delivery, dismiss):
            if process.is_alive():
                process.terminate()
                process.join(timeout=10)

    assert delivery.exitcode == 0
    assert dismiss.exitcode == 0
    assert effect_path.read_text(encoding="utf-8").splitlines() == [
        "dismiss-race"
    ]
    assert outbox.get("dismiss-race").status == "dismissed"


def test_delivery_loop_finalizes_without_repeating_failed_adapter(
    tmp_path: Path,
) -> None:
    outbox = notification_outbox(tmp_path)
    outbox.add(
        OutboxEntry(
            id="failed-before-finalize",
            title="Crash recovery",
            body="A recorded failure is terminal.",
            status="pending",
            idempotency_key="failed-before-finalize",
        )
    )
    outbox.prepare_delivery(
        "failed-before-finalize",
        ("failed", "remaining"),
    )
    outbox.begin_adapter_delivery(
        "failed-before-finalize",
        "failed",
    )
    outbox.record_adapter_result(
        "failed-before-finalize",
        "failed",
        success=False,
    )
    failed = FakeAdapter(succeed=True, delivery_id="failed")
    remaining = FakeAdapter(succeed=True, delivery_id="remaining")

    delivered = NotificationDeliveryLoop(
        notification_outbox(tmp_path),
        adapters=[failed, remaining],
    ).run_once()

    assert delivered == 0
    assert failed.sent_entries == []
    assert len(remaining.sent_entries) == 1
    completed = outbox.get("failed-before-finalize")
    assert completed.status == "failed"
    assert completed.deliveries["failed"].status == "failed"
    assert completed.deliveries["failed"].attempts == 1
    assert completed.deliveries["remaining"].status == "sent"


def test_delivery_loop_rejects_duplicate_adapter_ids_before_sending(
    tmp_path: Path,
) -> None:
    outbox = notification_outbox(tmp_path)
    outbox.add(
        OutboxEntry(
            id="duplicate-adapters",
            title="Duplicate",
            body="No adapter should run.",
            status="pending",
            idempotency_key="duplicate-adapters",
        )
    )
    first = FakeAdapter(delivery_id="duplicate")
    second = FakeAdapter(delivery_id="duplicate")

    with pytest.raises(ValueError, match="duplicate"):
        NotificationDeliveryLoop(
            notification_outbox(tmp_path),
            adapters=[first, second],
        ).run_once()

    assert first.sent_entries == []
    assert second.sent_entries == []
    assert outbox.get("duplicate-adapters").required_adapters == ()


def test_outbox_clear_dismissed_older_than_removes_old_entries(tmp_path: Path) -> None:
    outbox = notification_outbox(tmp_path)
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
    backend = auto_backend(tmp_path / "private")
    wire = OutboxEntry(
        id="corrupt-time",
        title="Private title",
        body="Private body",
        status="dismissed",
        idempotency_key="corrupt-time",
    ).to_wire()
    wire[field_name] = value
    backend.collection("notification_outbox").put("corrupt-time", wire)
    outbox = notification_outbox(tmp_path, backend=backend)

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
    backend = auto_backend(tmp_path / "private")
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
    outbox = notification_outbox(tmp_path, backend=backend)

    assert outbox.list() == []
    with pytest.raises(ValueError, match="unknown fields"):
        outbox.get("corrupt-context")


@pytest.mark.parametrize("days", (-1, True, 1.5))
def test_outbox_clear_rejects_invalid_retention_days(
    tmp_path: Path,
    days: object,
) -> None:
    outbox = notification_outbox(tmp_path)

    with pytest.raises(
        ValueError,
        match="retention days must be a non-negative integer",
    ):
        outbox.clear_dismissed_older_than(cast(int, days))


def test_outbox_clear_propagates_delete_failure(tmp_path: Path) -> None:
    backend: StorageBackend = DeleteFailingBackend(tmp_path / "private")
    outbox = notification_outbox(tmp_path, backend=backend)
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
    outbox = notification_outbox(tmp_path)
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
    outbox = notification_outbox(tmp_path)
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
    loop = NotificationDeliveryLoop(notification_outbox(tmp_path), adapters=[adapter])
    loop.run_once()

    assert outbox.list(status="dismissed") == []
