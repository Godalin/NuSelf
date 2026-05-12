"""Compact terminal renderers for NuSelf REPL output."""

from __future__ import annotations

import json
import os
import sys
from typing import cast

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
    if component == "reflection":
        return "33"
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


def render_reflection_summary(event: LogEvent, *, color: bool | None = None) -> str:
    """Render one reflection log event as a compact terminal line."""
    theme = TerminalTheme(color=color)
    status = event.status or "unknown"
    status_tag = theme.paint(f"[{status}]", "32" if status == "approved" else "31")
    time_str = event.time[:19] if event.time else "-"
    composite = ""
    if event.metadata and isinstance(event.metadata.get("composite"), (int, float)):
        composite = f"  score={event.metadata['composite']:.2f}"
    return f"{time_str} {status_tag} {event.message}{composite}"


def render_reflection_detail(event: LogEvent, *, color: bool | None = None) -> str:
    """Render one reflection log event with full discussion trace."""
    theme = TerminalTheme(color=color)
    meta = event.metadata if event.metadata else {}
    status = event.status or "unknown"
    status_tag = theme.paint(status, "32" if status == "approved" else "31")

    lines: list[str] = [
        f"time:         {event.time}",
        f"status:       {status_tag}",
        f"message:      {event.message}",
    ]
    if meta.get("candidate_id"):
        lines.append(f"candidate_id: {meta['candidate_id']}")
    if meta.get("candidate_type"):
        lines.append(f"type:         {meta['candidate_type']}")
    if meta.get("composite") is not None:
        lines.append(f"composite:    {meta['composite']:.3f}")

    scores = meta.get("scores")
    if isinstance(scores, dict) and scores:
        score_dict = cast(dict[str, object], scores)
        lines.append("")
        lines.append("persona scores:")
        for pid, score_val in sorted(score_dict.items()):
            score = float(score_val) if isinstance(score_val, (int, float)) else 0.0
            bar = "#" * int(score * 20)
            lines.append(f"  {pid:20s}  {score:.2f}  {bar}")

    blocking = meta.get("blocking_vetos")
    if isinstance(blocking, list) and blocking:
        blocking_list = cast(list[object], blocking)
        lines.append("")
        lines.append(f"blocking vetos: {', '.join(str(x) for x in blocking_list)}")

    winners = meta.get("winner_persona_ids")
    if isinstance(winners, list) and winners:
        winners_list = cast(list[object], winners)
        lines.append(f"winners:        {', '.join(str(x) for x in winners_list)}")

    emergent = meta.get("emergent_persona_ids")
    if isinstance(emergent, list) and emergent:
        emergent_list = cast(list[object], emergent)
        lines.append(f"emergent:       {', '.join(str(x) for x in emergent_list)}")

    if meta.get("revised_title"):
        lines.append("")
        lines.append(f"revised title:  {meta['revised_title']}")
    if meta.get("revised_body"):
        lines.append(f"revised body:   {meta['revised_body']}")

    trace = meta.get("discussion_trace")
    if isinstance(trace, list) and trace:
        lines.append("")
        lines.extend(render_discussion_trace(cast(list[object], trace), title="discussion trace"))

    return "\n".join(lines)


def render_discussion_trace(trace: list[object], *, title: str = "discussion trace") -> list[str]:
    """Render a discussion trace as an indented block for terminal display."""
    lines = [f"{title}:"]
    for trace_line in trace:
        lines.append(f"  {trace_line}")
    return lines
