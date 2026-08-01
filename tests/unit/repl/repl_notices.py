from __future__ import annotations

from pathlib import Path

import pytest

from nuself.cli.repl.notices import (
    print_interactive_notices,
    startup_interactive_notices,
    turn_interactive_notices,
)
from nuself.logs import write_log_event
from nuself.runtime.log_event import LogEvent


def _event(component: str, event: str) -> LogEvent:
    return LogEvent(
        time="2026-07-30T00:00:00+00:00",
        level="warning",
        component=component,  # type: ignore[arg-type]
        event=event,
        message="safe diagnostic",
        metadata=(
            {"collection": "memory_entries", "record_id": "mem_bad"}
            if component == "memory" and event == "record_decode_failed"
            else None
        ),
    )


def test_startup_reports_missing_model_and_explicit_scope_mismatch(
    tmp_path: Path,
) -> None:
    user_authority = tmp_path / "user"
    workspace = tmp_path / "workspace"
    user_authority.mkdir()
    (workspace / ".nuself").mkdir(parents=True)

    notices = startup_interactive_notices(
        user_authority,
        cwd=workspace,
    )

    assert [notice.code for notice in notices] == [
        "model-unconfigured",
        "workspace-authority-not-selected",
    ]
    assert "`nuself --local`" in notices[1].message


def test_turn_groups_record_failures_without_payloads() -> None:
    events = [
        _event("memory", "record_decode_failed"),
        _event("memory", "record_decode_failed"),
        _event("chat", "turn_completed"),
    ]

    notices = turn_interactive_notices(events)

    assert len(notices) == 1
    assert notices[0].code == "memory-records-unreadable"
    assert "2 memory record(s)" in notices[0].message
    assert "`nuself data check memory`" in notices[0].message
    assert "safe diagnostic" not in notices[0].message


def test_startup_groups_recent_hidden_failures(tmp_path: Path) -> None:
    authority = tmp_path / "authority"
    authority.mkdir()
    write_log_event(
        "memory",
        "record_decode_failed",
        "payload must stay hidden",
        project_root=authority,
        level="warning",
        metadata={
            "collection": "memory_entries",
            "record_id": "mem_bad",
        },
    )
    write_log_event(
        "daemon",
        "response_delivery_failed",
        "socket details must stay hidden",
        project_root=authority,
        level="warning",
        status="error",
        metadata={"response_status": "ok", "fallback": False},
    )

    notices = startup_interactive_notices(authority, cwd=tmp_path)

    messages = "\n".join(notice.message for notice in notices)
    assert "Recent logs contain 1 memory record decode failure(s)" in messages
    assert "`nuself data check memory`" in messages
    assert "failed to deliver 1 completed response(s)" in messages
    assert "payload must stay hidden" not in messages
    assert "socket details must stay hidden" not in messages


def test_startup_suppresses_failure_resolved_by_later_record_update(
    tmp_path: Path,
) -> None:
    authority = tmp_path / "authority"
    authority.mkdir()
    write_log_event(
        "memory",
        "record_decode_failed",
        "old decode failure",
        project_root=authority,
        level="warning",
        metadata={
            "collection": "memory_entries",
            "record_id": "mem_repaired",
        },
    )
    write_log_event(
        "daemon",
        "data_record_updated",
        "Authoritative data record updated",
        project_root=authority,
        status="completed",
        metadata={
            "collection": "memory_entries",
            "record_id": "mem_repaired",
        },
    )

    notices = startup_interactive_notices(authority, cwd=tmp_path)

    assert all(
        notice.code != "recent-memory-records-unreadable"
        for notice in notices
    )


def test_startup_keeps_unrepaired_and_post_repair_failures(
    tmp_path: Path,
) -> None:
    authority = tmp_path / "authority"
    authority.mkdir()
    for record_id in ("mem_repaired", "mem_unresolved"):
        write_log_event(
            "memory",
            "record_decode_failed",
            "decode failure",
            project_root=authority,
            level="warning",
            metadata={
                "collection": "memory_entries",
                "record_id": record_id,
            },
        )
    write_log_event(
        "daemon",
        "data_record_updated",
        "Authoritative data record updated",
        project_root=authority,
        status="completed",
        metadata={
            "collection": "memory_entries",
            "record_id": "mem_repaired",
        },
    )
    write_log_event(
        "memory",
        "record_decode_failed",
        "failure after repair",
        project_root=authority,
        level="warning",
        metadata={
            "collection": "memory_entries",
            "record_id": "mem_repaired",
        },
    )

    notices = startup_interactive_notices(authority, cwd=tmp_path)

    [notice] = [
        item
        for item in notices
        if item.code == "recent-memory-records-unreadable"
    ]
    assert "2 memory record decode failure(s)" in notice.message


def test_notice_renderer_uses_one_grouped_heading(
    capsys: pytest.CaptureFixture[str],
) -> None:
    notices = (
        turn_interactive_notices(
            [_event("memory", "record_decode_failed")]
        )[0],
        turn_interactive_notices(
            [_event("reasoning", "record_decode_failed")]
        )[0],
    )

    print_interactive_notices(notices)

    output = capsys.readouterr().out
    assert output.count("Attention:") == 1
    assert output.count("  ! ") == 2
