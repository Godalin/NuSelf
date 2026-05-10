"""Compact terminal renderers for NuSelf REPL output."""

from __future__ import annotations

import json
import os
import sys

from nuself.logs import LogEvent
from nuself.notification import OutboxEntry


class TerminalTheme:
    """Small ANSI theme with a no-color fallback."""

    def __init__(self, *, color: bool | None = None) -> None:
        self.color = _should_color() if color is None else color

    def tag(self, text: str, component: str) -> str:
        return self.paint(text, _component_color(component))

    def muted(self, text: str) -> str:
        return self.paint(text, "90")

    def warning(self, text: str) -> str:
        return self.paint(text, "33")

    def error(self, text: str) -> str:
        return self.paint(text, "31")

    def paint(self, text: str, code: str) -> str:
        if not self.color:
            return text
        return f"\033[{code}m{text}\033[0m"


def render_log_event(event: LogEvent, *, color: bool | None = None) -> str:
    """Render one log event as a compact terminal line."""

    theme = TerminalTheme(color=color)
    tag = theme.tag(f"[{_display_component(event.component)}]", event.component)
    pieces = [tag, event.message]
    if event.status:
        pieces.append(theme.muted(f"status={event.status}"))
    if event.duration_ms is not None:
        pieces.append(theme.muted(f"{event.duration_ms}ms"))
    if event.thread_id:
        pieces.append(theme.muted(f"thread={event.thread_id}"))
    if event.request_id:
        pieces.append(theme.muted(f"request={event.request_id}"))
    if event.error:
        pieces.append(theme.error(f"error={event.error}"))
    return " ".join(pieces)


def render_log_event_json(event: LogEvent) -> str:
    """Render one event as a JSON object line."""

    return json.dumps(event.to_record(), sort_keys=True, ensure_ascii=True)


def render_session_header(*, daemon_status: str, thread_id: str) -> str:
    """Render a compact REPL session header."""

    return f"session thread={thread_id} daemon={daemon_status}"


def _should_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _display_component(component: str) -> str:
    if component == "persona":
        return "selves"
    return component


def _component_color(component: str) -> str:
    if component == "daemon":
        return "90"
    if component == "chat":
        return "34"
    if component == "memory":
        return "32"
    if component == "persona":
        return "35"
    if component == "outbox":
        return "36"
    return "0"


def _status_color(status: str) -> str:
    if status == "pending":
        return "33"
    if status == "sent":
        return "32"
    if status == "failed":
        return "31"
    if status == "dismissed":
        return "90"
    return "0"


def render_outbox_summary(entry: OutboxEntry, *, color: bool | None = None) -> str:
    """Render one outbox entry as a compact terminal line."""
    theme = TerminalTheme(color=color)
    status_tag = theme.paint(f"[{entry.status}]", _status_color(entry.status))
    link_indicator = "link" if entry.deep_link else "-"
    created = entry.created_at[:19] if entry.created_at else "-"
    return f"{entry.id} {status_tag} {entry.title}  created={created}  attempts={entry.attempts}  {link_indicator}"


def render_outbox_detail(entry: OutboxEntry, *, color: bool | None = None) -> str:
    """Render one outbox entry as a multi-line detail view."""
    theme = TerminalTheme(color=color)
    status_tag = theme.paint(entry.status, _status_color(entry.status))
    lines: list[str] = [
        f"id:           {entry.id}",
        f"status:       {status_tag}",
        f"title:        {entry.title}",
        f"idempotency:  {entry.idempotency_key}",
        f"attempts:     {entry.attempts}",
        f"created_at:   {entry.created_at}",
    ]
    if entry.sent_at is not None:
        lines.append(f"sent_at:      {entry.sent_at}")
    if entry.deep_link is not None:
        lines.append(f"deep_link:    {entry.deep_link}")
    lines.append("")
    lines.append(entry.body)
    return "\n".join(lines)
