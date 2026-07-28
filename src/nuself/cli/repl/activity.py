"""Incremental activity projection for interactive CLI sessions."""

from __future__ import annotations

from pathlib import Path

from nuself.cli.commands.output import print_ansi
from nuself.logs import InteractiveLogCursor, LogEvent
from nuself.tui.render import render_log_event


def read_interactive_activity_events(
    project_root: Path | None,
    log_cursor: InteractiveLogCursor,
    *,
    turn_id: str | None = None,
) -> list[LogEvent]:
    """Read unseen activity, optionally scoped to one logical chat turn."""

    events = log_cursor.read_new_events(project_root)
    if turn_id is None:
        return events
    return [event for event in events if event.turn_id == turn_id]


def print_interactive_activity_events(events: list[LogEvent]) -> None:
    """Render activity events in their existing delivery order."""

    for event in events:
        print_ansi(render_log_event(event))


def visible_interactive_activity_events(
    events: list[LogEvent],
) -> list[LogEvent]:
    """Return events that belong in the live user-facing activity stream."""

    return [event for event in events if is_interactive_activity_log(event)]


def captured_interactive_activity_events(
    events: list[LogEvent],
) -> list[LogEvent]:
    """Return events retained for the current session transcript."""

    return [
        event
        for event in events
        if event.component in {"chat", "daemon", "persona"}
        or event.event == "approval_prompted"
    ]


def is_interactive_activity_log(event: LogEvent) -> bool:
    """Return whether one event is visible while an interactive turn runs."""

    if event.event == "approval_prompted":
        return True
    if event.component == "persona":
        return event.event in {
            "persona_summary",
            "host_discussion_decision",
            "persona_discussion",
            "persona_discussion_step",
            "persona_crafted",
            "persona_listed",
            "persona_think",
            "persona_think_failed",
        }
    if event.component == "chat":
        if event.event == "service_tool_called":
            return True
        if event.event in {
            "turn_started",
            "turn_completed",
            "turn_reused",
            "turn_retry",
            "final_response_retry",
            "final_response_completed",
        }:
            return True
        return is_failure_activity_log(event)
    if event.component == "daemon":
        return is_failure_activity_log(event)
    return False


def is_failure_activity_log(event: LogEvent) -> bool:
    """Return whether an event represents a user-relevant turn failure."""

    if event.status in {"error", "failed", "failed_over", "exhausted"}:
        return True
    return event.event in {
        "chat_turn_failed",
        "daemon_chat_failed",
        "final_response_failed",
        "llm_endpoint_failed_over",
        "llm_endpoint_unavailable",
        "turn_failed",
    }
