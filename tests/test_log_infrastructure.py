from __future__ import annotations

import json
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
