from __future__ import annotations

import json
import threading
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import cast

import pytest

from nuself.logs import (
    InteractiveLogCursor,
    LogComponent,
    LogEvent,
    LogRetentionPolicy,
    log_path,
    observe_log_events,
    read_log_events,
    write_log_event,
)
from nuself.runtime import RUNTIME_SCHEMA_VERSION


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
