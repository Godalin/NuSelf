from __future__ import annotations

import json
import threading
import warnings
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import cast

import pytest

import nuself.logs as logs
from nuself.logs import (
    InteractiveLogCursor,
    LogComponent,
    LogEvent,
    LogRetentionPolicy,
    create_audit_envelope,
    log_path,
    observe_log_events,
    read_log_events,
    write_audit_envelope,
    write_log_event,
)
from nuself.runtime import (
    RUNTIME_SCHEMA_VERSION,
    RuntimeEnvelope,
)


def test_new_log_events_have_stable_envelope_identity(tmp_path: Path) -> None:
    written = write_log_event(
        "chat",
        "turn_started",
        "turn started",
        project_root=tmp_path,
    )
    [read] = read_log_events(project_root=tmp_path, component="chat")

    assert read.event_id == written.event_id
    assert read.schema_version == RUNTIME_SCHEMA_VERSION


def test_audit_envelope_round_trip_retains_complete_projection(
    tmp_path: Path,
) -> None:
    envelope = create_audit_envelope(
        "chat",
        "turn_completed",
        "turn completed",
        level="warning",
        thread_id="thread-1",
        request_id="request-1",
        turn_id="turn-1",
        job_id="job-1",
        trace_id="trace-1",
        source="test",
        node="respond",
        duration_ms=12,
        status="completed",
        error="degraded",
        metadata={"tool_count": 2},
    )

    decoded = RuntimeEnvelope.from_record(envelope.to_record())
    written = write_audit_envelope(decoded, project_root=tmp_path)

    assert written == LogEvent(
        time=envelope.created_at,
        level="warning",
        component="chat",
        event="turn_completed",
        message="turn completed",
        event_id=envelope.message_id,
        schema_version=envelope.schema_version,
        thread_id="thread-1",
        request_id="request-1",
        turn_id="turn-1",
        job_id="job-1",
        trace_id="trace-1",
        source="test",
        node="respond",
        duration_ms=12,
        status="completed",
        error="degraded",
        metadata={"tool_count": 2},
    )


def test_audit_writer_rejects_wrong_kind_or_missing_message(
    tmp_path: Path,
) -> None:
    event_envelope = RuntimeEnvelope(
        kind="event",
        name="turn.completed",
        producer="chat",
        payload={"message": "completed"},
    )
    with pytest.raises(ValueError, match="requires an audit envelope"):
        write_audit_envelope(event_envelope, project_root=tmp_path)

    empty_audit = RuntimeEnvelope(
        kind="audit",
        name="turn_completed",
        producer="chat",
    )
    with pytest.raises(ValueError, match="requires a message"):
        write_audit_envelope(empty_audit, project_root=tmp_path)

    assert read_log_events(project_root=tmp_path) == []


def test_log_event_metadata_is_detached_and_recursively_immutable(
    tmp_path: Path,
) -> None:
    metadata: dict[str, object] = {
        "nested": {"items": ["original"]},
    }
    observed: list[LogEvent] = []

    with observe_log_events(observed.append):
        written = write_log_event(
            "chat",
            "metadata_test",
            "immutable",
            project_root=tmp_path,
            metadata=metadata,
        )

    nested_input = cast(dict[str, object], metadata["nested"])
    items_input = cast(list[str], nested_input["items"])
    items_input.append("caller mutation")

    assert observed == [written]
    assert observed[0] is written
    assert written.metadata is not None
    nested = written.metadata["nested"]
    assert isinstance(nested, Mapping)
    items = cast(tuple[str, ...], nested["items"])
    assert items == ("original",)
    with pytest.raises(TypeError):
        nested["extra"] = True  # type: ignore[index]

    record = written.to_record()
    record_metadata = cast(dict[str, object], record["metadata"])
    record_nested = cast(dict[str, object], record_metadata["nested"])
    record_items = cast(list[str], record_nested["items"])
    record_items.append("record mutation")
    assert nested["items"] == ("original",)


@pytest.mark.parametrize(
    "metadata",
    (
        {1: "non-string key"},
        {"value": float("nan")},
        {"value": object()},
    ),
)
def test_log_event_metadata_rejects_non_json_values_before_write(
    tmp_path: Path,
    metadata: object,
) -> None:
    with pytest.raises(TypeError):
        write_log_event(
            "chat",
            "metadata_test",
            "invalid",
            project_root=tmp_path,
            metadata=cast(dict[str, object], metadata),
        )

    assert not log_path("chat", project_root=tmp_path).exists()


def test_nested_log_observers_compose_in_order_and_restore(
    tmp_path: Path,
) -> None:
    deliveries: list[tuple[str, str]] = []

    def outer(event: LogEvent) -> None:
        deliveries.append(("outer", event.message))

    def inner(event: LogEvent) -> None:
        deliveries.append(("inner", event.message))

    with observe_log_events(outer):
        write_log_event("chat", "observer_test", "outer-1", project_root=tmp_path)
        with observe_log_events(inner):
            write_log_event(
                "chat",
                "observer_test",
                "nested",
                project_root=tmp_path,
            )
        write_log_event("chat", "observer_test", "outer-2", project_root=tmp_path)

    write_log_event("chat", "observer_test", "outside", project_root=tmp_path)

    assert deliveries == [
        ("outer", "outer-1"),
        ("outer", "nested"),
        ("inner", "nested"),
        ("outer", "outer-2"),
    ]


def test_log_observer_failure_is_isolated_from_later_observers(
    tmp_path: Path,
) -> None:
    delivered: list[LogEvent] = []

    def fail(_event: LogEvent) -> None:
        raise RuntimeError("projection failed")

    with observe_log_events(fail), observe_log_events(delivered.append):
        written = write_log_event(
            "chat",
            "observer_test",
            "persisted",
            project_root=tmp_path,
        )

    assert delivered == [written]
    assert read_log_events(project_root=tmp_path, component="chat") == [written]
    [diagnostic] = read_log_events(
        project_root=tmp_path,
        component="daemon",
    )
    assert diagnostic.event == "log_observer_failed"
    assert diagnostic.error == "projection failed"


def test_log_observer_diagnostic_failure_warns_without_affecting_delivery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    delivered: list[LogEvent] = []
    append_log_event = logs._append_log_event  # pyright: ignore[reportPrivateUsage]

    def fail_daemon_diagnostic(
        event_record: LogEvent,
        **kwargs: object,
    ) -> LogEvent:
        if event_record.component == "daemon":
            raise OSError("diagnostic store unavailable")
        return append_log_event(
            event_record,
            **kwargs,  # type: ignore[arg-type]
        )

    def fail_observer(_event: LogEvent) -> None:
        raise RuntimeError("projection failed")

    monkeypatch.setattr(logs, "_append_log_event", fail_daemon_diagnostic)

    with pytest.warns(
        RuntimeWarning,
        match=(
            "daemon/log_observer_failed: projection failed; "
            "structured logging failed: diagnostic store unavailable"
        ),
    ) as captured:
        with observe_log_events(fail_observer), observe_log_events(
            delivered.append
        ):
            written = write_log_event(
                "chat",
                "observer_test",
                "persisted",
                project_root=tmp_path,
            )

    assert len(captured) == 1
    assert delivered == [written]
    assert read_log_events(project_root=tmp_path, component="chat") == [written]
    assert read_log_events(project_root=tmp_path, component="daemon") == []


def test_log_observers_are_not_inherited_by_new_threads(tmp_path: Path) -> None:
    delivered: list[LogEvent] = []

    with observe_log_events(delivered.append):
        worker = threading.Thread(
            target=lambda: write_log_event(
                "chat",
                "observer_test",
                "thread",
                project_root=tmp_path,
            )
        )
        worker.start()
        worker.join()

    assert delivered == []
    assert len(read_log_events(project_root=tmp_path, component="chat")) == 1


@pytest.mark.parametrize(
    "event",
    ("", "TurnStarted", "turn-started", "turn..started", "1turn"),
)
def test_new_log_writes_reject_invalid_event_names(
    tmp_path: Path,
    event: str,
) -> None:
    with pytest.raises(ValueError, match="event name"):
        write_log_event(
            "chat",
            event,
            "invalid event",
            project_root=tmp_path,
        )


def test_new_log_writes_reject_invalid_components(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="component"):
        write_log_event(
            cast(LogComponent, "../escaped"),
            "turn_started",
            "invalid component",
            project_root=tmp_path,
        )

    assert not (tmp_path / "escaped.log").exists()


def test_storage_component_is_read_with_all_logs(tmp_path: Path) -> None:
    written = write_log_event(
        "storage",
        "backend_close_failed",
        "backend close failed",
        project_root=tmp_path,
    )

    assert read_log_events(
        project_root=tmp_path,
        component="storage",
    ) == [written]
    assert written in read_log_events(project_root=tmp_path)


def test_legacy_log_records_remain_readable_without_identity() -> None:
    event = LogEvent.from_record(
        {
            "time": "2026-01-01T00:00:00Z",
            "level": "info",
            "component": "chat",
            "event": "Legacy event with old syntax",
            "message": "legacy",
        }
    )

    assert event.event_id is None
    assert event.schema_version is None


@pytest.mark.parametrize(
    ("field_name", "value", "error_type"),
    [
        ("event_id", 42, TypeError),
        ("event_id", " ", ValueError),
        ("schema_version", True, TypeError),
        ("schema_version", 2, ValueError),
        ("thread_id", 42, TypeError),
        ("duration_ms", True, TypeError),
        ("duration_ms", -1, TypeError),
        ("metadata", [], TypeError),
    ],
)
def test_log_event_rejects_present_corrupt_optional_fields(
    field_name: str,
    value: object,
    error_type: type[Exception],
) -> None:
    record = LogEvent(
        time="2026-01-01T00:00:00Z",
        level="info",
        component="chat",
        event="healthy_event",
        message="healthy",
    ).to_record()
    record[field_name] = value

    with pytest.raises(error_type):
        LogEvent.from_record(record)


@pytest.mark.parametrize("missing_field", ("event_id", "schema_version"))
def test_log_event_rejects_partial_envelope_identity(
    missing_field: str,
) -> None:
    record = LogEvent(
        time="2026-01-01T00:00:00Z",
        level="info",
        component="chat",
        event="healthy_event",
        message="healthy",
    ).to_record()
    del record[missing_field]

    with pytest.raises(ValueError, match="both be present or absent"):
        LogEvent.from_record(record)


@pytest.mark.parametrize(
    ("timestamp", "message"),
    [
        ("", "must not be empty"),
        ("2026-01-01T00:00:00", "include a timezone"),
        ("not-a-time", "ISO-8601"),
    ],
)
def test_log_event_rejects_invalid_structured_timestamp(
    timestamp: str,
    message: str,
) -> None:
    record = LogEvent(
        time="2026-01-01T00:00:00Z",
        level="info",
        component="chat",
        event="healthy_event",
        message="healthy",
    ).to_record()
    record["time"] = timestamp

    with pytest.raises(ValueError, match=message):
        LogEvent.from_record(record)


def test_log_reader_orders_offset_timestamps_by_instant(
    tmp_path: Path,
) -> None:
    path = log_path("chat", project_root=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    later = LogEvent(
        time="2026-01-01T03:00:00+00:00",
        level="info",
        component="chat",
        event="later_event",
        message="later",
    )
    earlier = LogEvent(
        time="2026-01-01T10:00:00+08:00",
        level="info",
        component="chat",
        event="earlier_event",
        message="earlier",
    )
    equal_first = LogEvent(
        time="2026-01-01T11:00:00+08:00",
        level="info",
        component="chat",
        event="equal_first",
        message="equal-first",
    )
    equal_second = LogEvent(
        time="2026-01-01T03:00:00Z",
        level="info",
        component="chat",
        event="equal_second",
        message="equal-second",
    )
    path.write_text(
        "\n".join(
            json.dumps(event.to_record())
            for event in (
                later,
                earlier,
                equal_first,
                equal_second,
            )
        )
        + "\n",
        encoding="utf-8",
    )

    events = read_log_events(project_root=tmp_path, component="chat")

    assert [event.message for event in events] == [
        "earlier",
        "later",
        "equal-first",
        "equal-second",
    ]


def test_incremental_cursor_orders_components_by_instant(
    tmp_path: Path,
) -> None:
    cursor = InteractiveLogCursor.from_project(tmp_path)
    daemon_path = log_path("daemon", project_root=tmp_path)
    chat_path = log_path("chat", project_root=tmp_path)
    daemon_path.parent.mkdir(parents=True, exist_ok=True)
    daemon_path.write_text(
        json.dumps(
            LogEvent(
                time="2026-01-01T03:00:00Z",
                level="info",
                component="daemon",
                event="later_event",
                message="later",
            ).to_record()
        )
        + "\n",
        encoding="utf-8",
    )
    chat_path.write_text(
        json.dumps(
            LogEvent(
                time="2026-01-01T10:00:00+08:00",
                level="info",
                component="chat",
                event="earlier_event",
                message="earlier",
            ).to_record()
        )
        + "\n",
        encoding="utf-8",
    )

    assert [
        event.message for event in cursor.read_new_events(tmp_path)
    ] == ["earlier", "later"]


def test_log_reader_isolates_corrupt_record_without_hiding_legacy(
    tmp_path: Path,
) -> None:
    path = log_path("chat", project_root=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    healthy = LogEvent(
        time="2026-01-01T00:00:02Z",
        level="info",
        component="chat",
        event="healthy_event",
        message="healthy",
    ).to_record()
    legacy = {
        "time": "2026-01-01T00:00:01Z",
        "level": "info",
        "component": "chat",
        "event": "Legacy event with old syntax",
        "message": "legacy",
    }
    corrupt = dict(healthy)
    corrupt["time"] = "2026-01-01T00:00:00Z"
    corrupt["duration_ms"] = True
    corrupt["message"] = "PRIVATE CORRUPT CONTENT"
    corrupt_identity = dict(healthy)
    corrupt_identity["schema_version"] = True
    corrupt_identity["message"] = "ANOTHER PRIVATE VALUE"
    path.write_text(
        "\n".join(
            json.dumps(record)
            for record in (
                corrupt,
                corrupt_identity,
                legacy,
                healthy,
            )
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.warns(RuntimeWarning) as captured:
        events = read_log_events(
            project_root=tmp_path,
            component="chat",
        )

    assert [event.message for event in events] == ["legacy", "healthy"]
    assert events[0].event_id is None
    assert events[1].event_id == healthy["event_id"]
    assert len(captured) == 1
    warning = str(captured[0].message)
    assert "component=chat" in warning
    assert "file=chat.log" in warning
    assert "count=2" in warning
    assert "log duration_ms must be an integer" in warning
    assert "PRIVATE" not in warning
    assert str(tmp_path) not in warning


def test_incremental_cursor_reports_corruption_once_per_consumed_batch(
    tmp_path: Path,
) -> None:
    cursor = InteractiveLogCursor.from_project(tmp_path)
    path = log_path("chat", project_root=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    healthy = LogEvent(
        time="2026-01-01T00:00:00Z",
        level="info",
        component="chat",
        event="healthy_event",
        message="healthy",
    ).to_record()
    corrupt = dict(healthy)
    corrupt["metadata"] = []
    corrupt["message"] = "DO NOT DISCLOSE"
    path.write_text(
        json.dumps(corrupt)
        + "\nplain legacy line\n"
        + json.dumps(healthy)
        + "\n",
        encoding="utf-8",
    )

    with pytest.warns(RuntimeWarning) as captured:
        events = cursor.read_new_events(tmp_path)

    assert [event.message for event in events] == [
        "plain legacy line",
        "healthy",
    ]
    assert len(captured) == 1
    assert "count=1" in str(captured[0].message)
    assert "DO NOT DISCLOSE" not in str(captured[0].message)

    with warnings.catch_warnings(record=True) as repeated:
        warnings.simplefilter("always")
        assert cursor.read_new_events(tmp_path) == []
    assert repeated == []


def test_log_corruption_warning_policy_cannot_fail_read(
    tmp_path: Path,
) -> None:
    path = log_path("chat", project_root=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "time": "2026-01-01T00:00:00Z",
                "level": "info",
                "component": "chat",
                "event": "corrupt_event",
                "message": "private",
                "event_id": "event-1",
                "schema_version": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        assert read_log_events(
            project_root=tmp_path,
            component="chat",
        ) == []


def test_log_writes_are_complete_under_thread_contention(tmp_path: Path) -> None:
    def write(index: int) -> None:
        write_log_event(
            "daemon",
            "worker_tick",
            f"tick {index}",
            project_root=tmp_path,
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(write, range(50)))

    path = log_path("daemon", project_root=tmp_path)
    records = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
    ]

    assert len(records) == 50
    assert len({record["event_id"] for record in records}) == 50


def test_incremental_cursor_waits_for_complete_lines(tmp_path: Path) -> None:
    cursor = InteractiveLogCursor.from_project(tmp_path)
    path = log_path("chat", project_root=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "time": "2026-01-01T00:00:00Z",
        "level": "info",
        "component": "chat",
        "event": "legacy_event",
        "message": "legacy",
    }
    serialized = json.dumps(record)
    path.write_text(serialized, encoding="utf-8")

    assert cursor.read_new_events(tmp_path) == []

    with path.open("a", encoding="utf-8") as log_file:
        log_file.write("\n")

    assert [event.event for event in cursor.read_new_events(tmp_path)] == [
        "legacy_event"
    ]


def test_incremental_cursor_deduplicates_stable_event_ids(tmp_path: Path) -> None:
    cursor = InteractiveLogCursor.from_project(tmp_path)
    event = write_log_event(
        "chat",
        "turn_completed",
        "turn completed",
        project_root=tmp_path,
    )
    path = log_path("chat", project_root=tmp_path)
    with path.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(event.to_record()) + "\n")

    assert cursor.read_new_events(tmp_path) == [event]
    assert cursor.read_new_events(tmp_path) == []


def test_full_reader_deduplicates_exact_rotated_overlap(
    tmp_path: Path,
) -> None:
    path = log_path("chat", project_root=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    event = LogEvent(
        time="2026-01-01T00:00:00Z",
        level="info",
        component="chat",
        event="overlap_event",
        message="same",
        event_id="shared-event",
        schema_version=RUNTIME_SCHEMA_VERSION,
    )
    serialized = json.dumps(event.to_record()) + "\n"
    path.with_name("chat.log.1").write_text(
        serialized,
        encoding="utf-8",
    )
    path.write_text(serialized, encoding="utf-8")

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        events = read_log_events(
            project_root=tmp_path,
            component="chat",
        )

    assert events == [event]
    assert captured == []


def test_full_reader_reports_conflicting_event_identity_safely(
    tmp_path: Path,
) -> None:
    path = log_path("chat", project_root=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    canonical = LogEvent(
        time="2026-01-01T00:00:00Z",
        level="info",
        component="chat",
        event="identity_event",
        message="canonical private value",
        event_id="private-event-id",
        schema_version=RUNTIME_SCHEMA_VERSION,
    )
    conflict = LogEvent(
        time="2026-01-01T00:00:01Z",
        level="error",
        component="chat",
        event="identity_event",
        message="conflicting private value",
        event_id="private-event-id",
        schema_version=RUNTIME_SCHEMA_VERSION,
    )
    path.write_text(
        json.dumps(canonical.to_record())
        + "\n"
        + json.dumps(conflict.to_record())
        + "\n",
        encoding="utf-8",
    )

    with pytest.warns(RuntimeWarning) as captured:
        events = read_log_events(
            project_root=tmp_path,
            component="chat",
        )

    assert events == [canonical]
    assert len(captured) == 1
    warning = str(captured[0].message)
    assert "logs/event_identity_conflict" in warning
    assert "count=1" in warning
    assert "first_component=chat" in warning
    assert "first_event=identity_event" in warning
    assert "private-event-id" not in warning
    assert "private value" not in warning
    assert str(tmp_path) not in warning


def test_cursor_reconciles_mark_seen_across_file_batches(
    tmp_path: Path,
) -> None:
    cursor = InteractiveLogCursor.from_project(tmp_path)
    canonical = LogEvent(
        time="2026-01-01T00:00:00Z",
        level="info",
        component="chat",
        event="activity_event",
        message="canonical",
        event_id="activity-event-id",
        schema_version=RUNTIME_SCHEMA_VERSION,
    )
    cursor.mark_seen([canonical])
    path = log_path("chat", project_root=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(canonical.to_record()) + "\n",
        encoding="utf-8",
    )

    with warnings.catch_warnings(record=True) as exact_warnings:
        warnings.simplefilter("always")
        assert cursor.read_new_events(tmp_path) == []
    assert exact_warnings == []

    conflict = LogEvent(
        time="2026-01-01T00:00:01Z",
        level="warning",
        component="chat",
        event="activity_event",
        message="private conflict",
        event_id="activity-event-id",
        schema_version=RUNTIME_SCHEMA_VERSION,
    )
    with path.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(conflict.to_record()) + "\n")

    with pytest.warns(RuntimeWarning) as captured:
        assert cursor.read_new_events(tmp_path) == []

    assert len(captured) == 1
    warning = str(captured[0].message)
    assert "event_identity_conflict" in warning
    assert "activity-event-id" not in warning
    assert "private conflict" not in warning


def test_log_rotation_bounds_backups_and_readers_include_them(
    tmp_path: Path,
) -> None:
    policy = LogRetentionPolicy(max_bytes=300, backup_count=2)

    for index in range(6):
        write_log_event(
            "daemon",
            "worker_tick",
            f"tick {index}",
            project_root=tmp_path,
            retention_policy=policy,
        )

    path = log_path("daemon", project_root=tmp_path)
    assert path.is_file()
    assert path.with_name("daemon.log.1").is_file()
    assert path.with_name("daemon.log.2").is_file()
    assert not path.with_name("daemon.log.3").exists()
    events = read_log_events(project_root=tmp_path, component="daemon")
    assert [event.message for event in events] == [
        "tick 3",
        "tick 4",
        "tick 5",
    ]


def test_incremental_cursor_finishes_rotated_inode_before_active_file(
    tmp_path: Path,
) -> None:
    write_log_event("chat", "turn_started", "seen", project_root=tmp_path)
    cursor = InteractiveLogCursor.from_project(tmp_path)
    write_log_event("chat", "tool_activity", "before rotation", project_root=tmp_path)
    path = log_path("chat", project_root=tmp_path)
    policy = LogRetentionPolicy(
        max_bytes=path.stat().st_size + 1,
        backup_count=2,
    )
    write_log_event(
        "chat",
        "turn_completed",
        "after rotation",
        project_root=tmp_path,
        retention_policy=policy,
    )

    assert [event.message for event in cursor.read_new_events(tmp_path)] == [
        "before rotation",
        "after rotation",
    ]


def test_log_retention_policy_rejects_unbounded_values() -> None:
    with pytest.raises(ValueError, match="max_bytes"):
        LogRetentionPolicy(max_bytes=0)
    with pytest.raises(ValueError, match="backup_count"):
        LogRetentionPolicy(backup_count=0)
