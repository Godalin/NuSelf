from __future__ import annotations

from typing import cast

from nuself.cli.repl.activity import (
    captured_interactive_activity_events,
    visible_interactive_activity_events,
)
from nuself.logs import LogComponent, LogEvent


def _event(
    component: str,
    event: str,
    *,
    status: str | None = None,
) -> LogEvent:
    return LogEvent(
        time="2026-07-28T00:00:00+00:00",
        level="info",
        component=cast(LogComponent, component),
        event=event,
        message=event,
        status=status,
    )


def test_activity_projection_keeps_capture_and_visibility_distinct() -> None:
    tool = _event("chat", "service_tool_called")
    background_chat = _event("chat", "one_shot_chat_completed")
    approval = _event("reasoning", "approval_prompted")
    background_reason = _event("reasoning", "advance_completed")

    events = [tool, background_chat, approval, background_reason]

    assert visible_interactive_activity_events(events) == [tool, approval]
    assert captured_interactive_activity_events(events) == [
        tool,
        background_chat,
        approval,
    ]


def test_daemon_failures_are_visible_without_capturing_other_domains() -> None:
    daemon_failure = _event("daemon", "socket_failed", status="error")
    memory_failure = _event("memory", "curator_failed", status="error")

    events = [daemon_failure, memory_failure]

    assert visible_interactive_activity_events(events) == [daemon_failure]
    assert captured_interactive_activity_events(events) == [daemon_failure]
