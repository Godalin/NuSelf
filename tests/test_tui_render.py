from __future__ import annotations

from nuself.logs import LogEvent
from nuself.tui.render import render_discussion_trace, render_host_decision


def test_render_discussion_trace_formats_block() -> None:
    lines = render_discussion_trace(["host: start", "turn-1:analyst: considered the idea"], title="discussion trace")

    assert lines == [
        "discussion trace:",
        "  ── host ──",
        "    [host]             start",
        "",
        "  ── turn-1 ──",
        "    [analyst]          considered the idea",
    ]


def test_render_host_decision_formats_block() -> None:
    event = LogEvent(
        time="2026-05-12T10:00:00Z",
        level="info",
        component="persona",
        event="host_discussion_decision",
        message="user asked for multi-perspective discussion",
        thread_id="default",
        status="approved",
        metadata={"should_escalate": True, "escalation_reason": "multi-perspective request"},
    )

    lines = render_host_decision(event)

    assert lines == [
        "[host decision] user asked for multi-perspective discussion  status=approved",
        "  should_escalate: True",
        "  thread: default",
    ]
