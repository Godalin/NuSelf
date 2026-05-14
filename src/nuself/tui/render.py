"""Compact terminal renderers for NuSelf REPL output."""

from __future__ import annotations

import json
import os
import sys
from typing import cast

from nuself.logs import LogEvent
from nuself.notification import OutboxEntry
from nuself.reflection.repository import ReflectionEntry


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

    if event.component == "persona" and event.event == "persona_summary":
        return _render_persona_summary_event(event, color=color)
    if _discussion_trace_metadata(event):
        return _render_discussion_log_event(event, color=color)

    theme = TerminalTheme(color=color)
    tag = theme.tag(f"[{_display_component(event.component)}]", event.component)
    pieces = [tag, event.event, event.message]
    pieces.extend(_render_log_fields(event, theme))
    return " ".join(pieces)


def _render_persona_summary_event(event: LogEvent, *, color: bool | None = None) -> str:
    """Render internal persona thoughts as an ordered multi-line block."""
    theme = TerminalTheme(color=color)
    tag = theme.tag(f"[{_display_component(event.component)}]", event.component)
    header = [tag, "persona_summary"]
    header.extend(_render_log_fields(event, theme))
    lines = [" ".join(header)]
    body_lines = [line for line in event.message.splitlines() if line.strip()]
    if not body_lines:
        body_lines = ["(no persona contributions)"]
    lines.extend(f"  {_color_persona_line(line, theme)}" for line in body_lines)
    return "\n".join(lines)


def _render_discussion_log_event(event: LogEvent, *, color: bool | None = None) -> str:
    theme = TerminalTheme(color=color)
    tag = theme.tag(f"[{_display_component(event.component)}]", event.component)
    header = [tag, event.event, event.message]
    header.extend(_render_log_fields(event, theme))
    lines = [" ".join(header)]
    trace = _discussion_trace_metadata(event)
    for line in render_discussion_trace(trace, title="discussion"):
        lines.append(f"  {line}" if line else "")
    return "\n".join(lines)


def _discussion_trace_metadata(event: LogEvent) -> list[object]:
    if not event.metadata:
        return []
    raw = event.metadata.get("discussion_trace")
    if not isinstance(raw, list) or not raw:
        return []
    return cast(list[object], raw)


def _render_log_fields(event: LogEvent, theme: TerminalTheme) -> list[str]:
    fields: list[str] = []
    if event.status:
        fields.append(theme.muted(_format_log_field("status", event.status)))
    if event.duration_ms is not None:
        fields.append(theme.muted(_format_log_field("duration_ms", event.duration_ms)))
    if event.thread_id:
        fields.append(theme.muted(_format_log_field("thread", event.thread_id)))
    if event.request_id:
        fields.append(theme.muted(_format_log_field("request", event.request_id)))
    if event.node:
        fields.append(theme.muted(_format_log_field("node", event.node)))
    if event.error:
        fields.append(theme.error(_format_log_field("error", event.error)))
    if event.metadata:
        for key in sorted(event.metadata):
            if key in {"message_body", "answer", "reply"}:
                continue
            if key == "discussion_trace":
                continue
            fields.append(theme.muted(_format_log_field(key, event.metadata[key])))
    return fields


def _format_log_field(key: str, value: object) -> str:
    return f"{key}={_format_log_value(value)}"


def _format_log_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, str):
        return _quote_log_value(value)
    if isinstance(value, list | tuple):
        items = cast(list[object] | tuple[object, ...], value)
        return "[" + ", ".join(_format_log_value(item) for item in items) + "]"
    if value is None:
        return "null"
    return _quote_log_value(json.dumps(value, sort_keys=True, ensure_ascii=True))


def _quote_log_value(value: str) -> str:
    if value == "":
        return '""'
    if any(character.isspace() for character in value):
        return json.dumps(value, ensure_ascii=False)
    return value


def _color_persona_line(line: str, theme: TerminalTheme) -> str:
    speaker, separator, text = line.partition(":")
    if not separator:
        return line
    label = theme.paint(speaker, _persona_color(speaker))
    return f"{label}:{text}"


def _persona_color(persona_id: str) -> str:
    colors = {
        "analyst_self": "36",
        "skeptic_self": "31",
        "builder_self": "32",
        "historian_self": "34",
        "care_self": "35",
        "synthesizer_self": "33",
        "moderator_self": "90",
        "bridge_self": "96",
        "urgency_self": "91",
    }
    if persona_id in colors:
        return colors[persona_id]
    palette = ("36", "31", "32", "34", "35", "33")
    return palette[sum(ord(ch) for ch in persona_id) % len(palette)]


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


def render_reflection_entry_summary(entry: ReflectionEntry, *, color: bool | None = None) -> str:
    """Render one reflection entry as a compact terminal line."""
    theme = TerminalTheme(color=color)
    status_tag = theme.paint(f"[{entry.status}]", _status_color(entry.status))
    created = entry.created_at[:19] if entry.created_at else "-"
    return f"{status_tag} {entry.title}  created={created}  type={entry.candidate_type}  score={entry.composite_score:.2f}"


def render_reflection_entry_detail(entry: ReflectionEntry, *, color: bool | None = None) -> str:
    """Render one reflection entry as a multi-line detail view."""
    theme = TerminalTheme(color=color)
    status_tag = theme.paint(entry.status, _status_color(entry.status))
    discussion = "approved" if entry.discussion_approved is True else ("rejected" if entry.discussion_approved is False else "N/A")
    lines: list[str] = [
        f"id:             {entry.id}",
        f"title:          {entry.title}",
        f"type:           {entry.candidate_type}",
        f"score:          {entry.composite_score:.2f} (confidence={entry.confidence:.2f} novelty={entry.novelty:.2f} urgency={entry.urgency:.2f} interruption={entry.interruption_cost:.2f})",
        f"status:         {status_tag}",
        f"discussion:     {discussion}",
        f"deep_link:      {entry.deep_link}",
        f"created_at:     {entry.created_at}",
    ]
    if entry.reviewed_at is not None:
        lines.append(f"reviewed_at:    {entry.reviewed_at}")
    if entry.discussion_trace:
        lines.append("")
        lines.append("discussion_trace:")
        for line in entry.discussion_trace:
            lines.append(f"  {line}")
    lines.append("")
    lines.append(entry.body)
    return "\n".join(lines)



def _parse_trace_entry(text: str) -> tuple[str | None, str | None, str]:
    """Parse a discussion trace string into (turn_label, speaker, content)."""
    if text.startswith("host:"):
        return "host", "host", text[5:].strip()
    if text.startswith("candidate:"):
        return "candidate", "candidate", text[10:].strip()
    if text.startswith("turn-"):
        parts = text.split(":", 2)
        if len(parts) >= 3:
            return parts[0], parts[1].strip(), parts[2].strip()
        if len(parts) == 2:
            return parts[0], None, parts[1].strip()
    return None, None, text


def render_discussion_trace(trace: list[object], *, title: str = "discussion trace") -> list[str]:
    """Render a discussion trace grouped by turn with per-speaker labels."""
    lines: list[str] = [f"{title}:"]
    current_turn: str | None = None

    for entry in trace:
        text = str(entry)
        turn_label, speaker, content = _parse_trace_entry(text)

        if turn_label is not None and turn_label != current_turn:
            if current_turn is not None:
                lines.append("")
            lines.append(f"  ── {turn_label} ──")
            current_turn = turn_label

        if speaker is not None:
            tag = f"[{speaker}]"
            lines.append(f"    {tag:<18} {content}")
        elif turn_label is not None:
            lines.append(f"    {'':18} {content}")
        else:
            indent = "    " if current_turn is not None else "  "
            lines.append(f"{indent}{text}")

    return lines


def render_host_decision(event: LogEvent, *, color: bool | None = None) -> list[str]:
    """Render a structured host discussion decision event for REPL display."""
    theme = TerminalTheme(color=color)
    header = theme.tag("[host decision]", "persona")
    pieces = [header, event.event, event.message]
    pieces.extend(_render_log_fields(event, theme))
    return [" ".join(pieces)]
