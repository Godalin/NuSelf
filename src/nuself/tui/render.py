"""Compact terminal renderers for NuSelf REPL output."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
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
    if event.event == "persona_discussion_step":
        return _render_persona_discussion_step(event, color=color)
    if _discussion_trace_metadata(event):
        return _render_discussion_log_event(event, color=color)
    if event.event == "service_tool_called" and event.metadata:
        return _render_service_tool_called(event, color=color)

    theme = TerminalTheme(color=color)
    tag = _render_log_tags(event, theme)
    inline_status = event.component != "persona"
    header = _render_log_header(tag, event.event, event, theme, inline_status=inline_status)
    lines = [header]
    if not inline_status:
        lines.extend(_render_status_body(event, theme))
    lines.extend(render_record_body(event.message))
    return "\n".join(lines)


def _render_service_tool_called(event: LogEvent, *, color: bool | None = None) -> str:
    """Render a service_tool_called log event via render_tool_call."""
    service: str | None = None
    args: object = {}
    result: object | None = None
    error: object | None = event.error
    if event.metadata:
        raw_comp = event.metadata.get("service_component")
        if isinstance(raw_comp, str):
            service = raw_comp
        if "args" in event.metadata:
            args = event.metadata["args"]
        if "result" in event.metadata:
            result = event.metadata["result"]
        if "error" in event.metadata:
            error = event.metadata["error"]
    if not _has_structured_tool_io(event):
        legacy_args, legacy_result, legacy_error = _parse_legacy_tool_body(event.message)
        args = legacy_args
        result = legacy_result
        error = legacy_error if legacy_error is not None else error
    extra: dict[str, object] = {}
    if event.thread_id:
        extra["thread"] = event.thread_id
    if event.turn_id:
        extra["turn"] = event.turn_id
    if event.metadata:
        raw_tool = event.metadata.get("tool")
        if isinstance(raw_tool, str):
            extra["tool"] = raw_tool
    return render_tool_call(
        component=event.component,
        service=service or event.component,
        args=args,
        result=result,
        error=error,
        status=event.status or "completed",
        extra_fields=extra or None,
        color=color,
    )


def _has_structured_tool_io(event: LogEvent) -> bool:
    if not event.metadata:
        return False
    return any(key in event.metadata for key in ("args", "result", "error"))


def _parse_legacy_tool_body(message: str) -> tuple[object, object | None, object | None]:
    sections: dict[str, str] = {}
    current: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current, current_lines
        if current is not None:
            sections[current] = "\n".join(current_lines).strip()
        current = None
        current_lines = []

    for line in message.splitlines():
        stripped = line.strip()
        label: str | None = None
        rest = ""
        if stripped == "args:" or stripped.startswith("args: "):
            label = "args"
            rest = stripped.removeprefix("args:").strip()
        elif stripped == "result:" or stripped.startswith("result: "):
            label = "result"
            rest = stripped.removeprefix("result:").strip()
        elif stripped == "error:" or stripped.startswith("error: "):
            label = "error"
            rest = stripped.removeprefix("error:").strip()
        if label is not None:
            flush()
            current = label
            current_lines = [rest] if rest else []
        elif current is not None:
            current_lines.append(line)
    flush()

    args: object = _legacy_tool_value(sections.get("args")) if "args" in sections else cast(dict[str, object], {})
    result: object | None = _legacy_tool_value(sections.get("result")) if "result" in sections else None
    error: object | None = _legacy_tool_value(sections.get("error")) if "error" in sections else None
    return args, result, error


def _legacy_tool_value(raw: str | None) -> object:
    if raw is None:
        return None
    parsed = _parse_json_string(raw)
    if parsed is not None:
        return parsed
    return raw


def _render_persona_summary_event(event: LogEvent, *, color: bool | None = None) -> str:
    """Render internal persona thoughts as an ordered multi-line block."""
    theme = TerminalTheme(color=color)
    tag = _render_log_tags(event, theme)
    lines = [_render_log_header(tag, "persona_summary", event, theme, inline_status=False)]
    lines.extend(_render_status_body(event, theme))
    body_lines = [line for line in event.message.splitlines() if line.strip()]
    if not body_lines:
        body_lines = ["(no persona contributions)"]
    lines.extend(f"  {_color_persona_line(line, theme)}" for line in body_lines)
    return "\n".join(lines)


def _render_discussion_log_event(event: LogEvent, *, color: bool | None = None) -> str:
    theme = TerminalTheme(color=color)
    tag = _render_log_tags(event, theme)
    inline_status = event.component != "persona"
    lines = [_render_log_header(tag, event.event, event, theme, inline_status=inline_status)]
    if not inline_status:
        lines.extend(_render_status_body(event, theme))
    lines.extend(render_record_body(event.message))
    trace = _discussion_trace_metadata(event)
    for line in render_discussion_trace(trace, title="discussion", color=color):
        lines.append(f"  {line}" if line else "")
    return "\n".join(lines)


def _render_persona_discussion_step(event: LogEvent, *, color: bool | None = None) -> str:
    """Compact single-line rendering for streaming discussion steps."""
    trace = _discussion_trace_metadata(event)
    if not trace:
        return ""
    theme = TerminalTheme(color=color)
    lines: list[str] = []
    for entry in trace:
        text = str(entry)
        turn_label, speaker, content = _parse_trace_entry(text)
        if speaker is not None and speaker == turn_label:
            tag = theme.paint(f"[{speaker}]", _persona_color(speaker))
            lines.append(f"  {tag} {content}")
        elif speaker is not None:
            tag = _color_persona_trace_tag(f"[{speaker}]", speaker, theme)
            lines.append(f"    {tag} {content}")
        elif turn_label is not None:
            tag = theme.paint(f"[{turn_label}]", _discussion_group_color(turn_label))
            lines.append(f"  {tag} {content}")
        else:
            lines.append(f"    {text}")
    return "\n".join(lines)


def _render_log_header(
    tag: str,
    event_name: str,
    event: LogEvent,
    theme: TerminalTheme,
    *,
    inline_status: bool = True,
) -> str:
    return render_record_header(f"{tag} {event_name}", _render_log_fields(event, theme, include_status=inline_status))


def render_record_header(label: str, fields: Sequence[str] = ()) -> str:
    """Render one compact record header with key=value metadata."""
    pieces = [label]
    pieces.extend(fields)
    return " ".join(piece for piece in pieces if piece)


def render_record_body(message: str) -> list[str]:
    """Render body text as indented lines under a record header."""
    lines = [line for line in message.splitlines() if line.strip()]
    return [f"  {line}" for line in lines]


def render_record_block(label: str, fields: Sequence[str] = (), *, body: str = "") -> str:
    """Render a header plus optional indented body text."""
    lines = [render_record_header(label, fields)]
    lines.extend(render_record_body(body))
    return "\n".join(lines)


def render_tool_call(
    *,
    component: str,
    service: str,
    args: object,
    result: object | None = None,
    error: object | None = None,
    status: str = "completed",
    extra_fields: dict[str, object] | None = None,
    color: bool | None = None,
) -> str:
    """Render a tool call with colored component and service tags.

    Produces:
      [component] [service] service_tool_called  status=completed  key=value
        args: {json}
        result: ...
    """
    theme = TerminalTheme(color=color)
    comp_tag = theme.tag(f"[{component}]", component)
    srv_tag = theme.tag(f"[{service}]", service)
    header_parts: list[str] = [f"{comp_tag} {srv_tag} service_tool_called"]
    remaining_fields = dict(extra_fields or {})
    tool_name = remaining_fields.pop("tool", None)
    if tool_name is not None:
        header_parts.append(_render_tool_header_field("tool", tool_name, theme))
    header_parts.append(_render_tool_header_field("status", status, theme))
    for k, v in remaining_fields.items():
        if v is not None:
            header_parts.append(theme.muted(_format_log_field(k, v)))
    lines = [" ".join(header_parts)]
    _append_tool_io_section(lines, "args", args, theme)
    if result is not None:
        _append_tool_io_section(lines, "result", result, theme)
    if error is not None:
        _append_tool_io_section(lines, "error", error, theme)
    return "\n".join(lines)


def _render_tool_header_field(key: str, value: object, theme: TerminalTheme) -> str:
    if key == "tool":
        return f"{key}={theme.paint(_format_log_value(value), '36')}"
    if key == "status":
        return f"{key}={theme.paint(_format_log_value(value), _status_color(str(value)))}"
    return theme.muted(_format_log_field(key, value))


def _append_tool_io_section(lines: list[str], label: str, value: object, theme: TerminalTheme) -> None:
    normalized = _normalize_tool_json(value)
    rendered = _render_tool_io_value(normalized, theme=theme)
    if not rendered:
        lines.append(f"  {theme.muted(label + ':')}")
        return
    if isinstance(normalized, dict | list):
        lines.append(f"  {theme.muted(label + ':')} {rendered[0]}")
        for line in rendered[1:]:
            lines.append(f"  {line}")
        return
    lines.append(f"  {theme.muted(label + ':')}")
    for line in rendered:
        lines.append(f"    {line}")


def _render_tool_io_value(value: object, *, theme: TerminalTheme) -> list[str]:
    if isinstance(value, dict):
        return _render_tool_json(cast(dict[object, object], value), theme=theme)
    if isinstance(value, list):
        return _render_tool_json(cast(list[object], value), theme=theme)
    if isinstance(value, str):
        return value.splitlines() or [""]
    return [_render_scalar(value)]


def _normalize_tool_json(value: object) -> object:
    parsed = _parse_json_string(value)
    if parsed is not None:
        return _normalize_tool_json(parsed)
    if isinstance(value, dict):
        value_dict = cast(dict[object, object], value)
        return {str(key): _normalize_tool_json(item) for key, item in value_dict.items()}
    if isinstance(value, list):
        return [_normalize_tool_json(item) for item in cast(list[object], value)]
    return value


def _render_tool_json(value: object, *, theme: TerminalTheme) -> list[str]:
    try:
        text = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return [_render_scalar(value)]
    if not theme.color:
        return text.splitlines()

    from rich.console import Console
    from rich.json import JSON as RichJSON
    import io

    buf = io.StringIO()
    Console(file=buf, force_terminal=True, width=160).print(RichJSON(text, indent=2), end="")
    return buf.getvalue().rstrip().splitlines()


def _parse_json_string(value: object) -> object | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped or stripped[0] not in "[{":
        return None
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None


def _render_scalar(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _discussion_trace_metadata(event: LogEvent) -> list[object]:
    if not event.metadata:
        return []
    raw = event.metadata.get("discussion_trace")
    if not isinstance(raw, list) or not raw:
        return []
    return cast(list[object], raw)


def _render_log_fields(event: LogEvent, theme: TerminalTheme, *, include_status: bool = True) -> list[str]:
    fields: list[str] = []
    if include_status and event.status:
        fields.append(theme.muted(_format_log_field("status", event.status)))
    if event.duration_ms is not None:
        fields.append(theme.muted(_format_log_field("duration_ms", event.duration_ms)))
    if event.thread_id:
        fields.append(theme.muted(_format_log_field("thread", event.thread_id)))
    if event.request_id:
        fields.append(theme.muted(_format_log_field("request", event.request_id)))
    if event.turn_id:
        fields.append(theme.muted(_format_log_field("turn", event.turn_id)))
    if event.job_id:
        fields.append(theme.muted(_format_log_field("job", event.job_id)))
    if event.trace_id:
        fields.append(theme.muted(_format_log_field("trace", event.trace_id)))
    if event.source:
        fields.append(theme.muted(_format_log_field("source", event.source)))
    if event.node:
        fields.append(theme.muted(_format_log_field("node", event.node)))
    if event.error:
        fields.append(theme.error(_format_log_field("error", event.error)))
    if event.metadata:
        for key in sorted(event.metadata):
            if key in {"answer", "reply"}:
                continue
            if key == "discussion_trace":
                continue
            if key == "service_component":
                continue
            if event.component == "persona" and key == "escalation_reason":
                continue
            fields.append(theme.muted(_format_log_field(key, event.metadata[key])))
    return fields


def _render_log_tags(event: LogEvent, theme: TerminalTheme) -> str:
    tags = [theme.tag(f"[{_display_component(event.component)}]", event.component)]
    service_component = _service_component(event)
    if service_component is not None:
        tags.append(theme.tag(f"[{_display_component(service_component)}]", service_component))
    return " ".join(tags)


def _service_component(event: LogEvent) -> str | None:
    if not event.metadata:
        return None
    value = event.metadata.get("service_component")
    if isinstance(value, str) and value:
        return value
    return None


def _render_status_body(event: LogEvent, theme: TerminalTheme) -> list[str]:
    if not event.status:
        return []
    return [f"  {theme.muted(event.status)}"]


def _format_log_field(key: str, value: object) -> str:
    return f"{key}={_format_log_value(value)}"


def render_key_value_field(key: str, value: object) -> str:
    """Render a stable key=value field for human-readable terminal records."""
    if isinstance(value, str) and _is_timestamp_field(key):
        value = format_display_timestamp(value)
    return _format_log_field(key, value)


def _render_key_value_fields(items: Sequence[tuple[str, object]]) -> list[str]:
    return [render_key_value_field(key, value) for key, value in items]


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


def format_display_timestamp(value: str | datetime) -> str:
    """Render a timestamp in the current system timezone for humans."""

    parsed = _parse_display_timestamp(value)
    if parsed is None:
        return value if isinstance(value, str) else value.isoformat()
    return parsed.astimezone().isoformat(timespec="seconds")


def _parse_display_timestamp(value: str | datetime) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _is_timestamp_field(key: str) -> bool:
    return key in {"created", "created_at", "updated_at", "reviewed_at", "sent_at", "connected", "exported", "last_advanced_at"}


def render_session_header(*, daemon_status: str, thread_id: str) -> str:
    """Render a compact REPL session header."""

    theme = TerminalTheme()
    tag = theme.tag("[daemon]", "daemon")
    return render_record_header(
        f"{tag} session",
        [
            render_key_value_field("status", daemon_status),
            render_key_value_field("thread", thread_id),
        ],
    )


def _should_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


_color_depth_256: bool | None = None


def _supports_256_color() -> bool:
    global _color_depth_256
    if _color_depth_256 is not None:
        return _color_depth_256
    colorterm = os.environ.get("COLORTERM")
    if colorterm in ("truecolor", "24bit"):
        _color_depth_256 = True
        return True
    term = os.environ.get("TERM", "")
    if "256color" in term:
        _color_depth_256 = True
        return True
    _color_depth_256 = False
    return False


_COLORS_256: dict[str, str] = {
    "daemon": "90",
    "chat": "34",
    "memory": "32",
    "persona": "35",
    "reasoning": "95",
    "selves": "95",
    "outbox": "36",
    "trace": "96",
    "reflection": "33",
    "workspace": "38;5;208",
    "skill": "31",
}

_COLORS_BASIC: dict[str, str] = {
    "daemon": "90",
    "chat": "34",
    "memory": "32",
    "persona": "35",
    "reasoning": "35",
    "selves": "35",
    "outbox": "36",
    "trace": "36",
    "reflection": "33",
    "workspace": "33",
    "skill": "31",
}


def _display_component(component: str) -> str:
    if component == "persona":
        return "selves"
    return component


def _component_color(component: str) -> str:
    if _supports_256_color():
        return _COLORS_256.get(component, "0")
    return _COLORS_BASIC.get(component, "0")


def _status_color(status: str) -> str:
    normalized = status.lower()
    if normalized in {"completed", "ok", "success", "sent", "active", "approved"}:
        return "32"
    if normalized in {"failed", "error"}:
        return "31"
    if normalized in {"pending", "paused"}:
        return "33"
    if normalized == "dismissed":
        return "90"
    return "0"


def render_outbox_summary(entry: OutboxEntry, *, index: int | None = None, color: bool | None = None) -> str:
    """Render one outbox entry as a compact terminal line."""
    theme = TerminalTheme(color=color)
    status_tag = theme.paint(f"[{entry.status}]", _status_color(entry.status))
    created = format_display_timestamp(entry.created_at) if entry.created_at else "-"
    label = f"[{index}] {entry.id}" if index is not None else entry.id
    return render_record_header(
        f"{label} {status_tag} {entry.title}",
        _render_key_value_fields(
            [
                ("created", created),
                ("attempts", entry.attempts),
                ("link", entry.deep_link is not None),
            ]
        ),
    )


def render_outbox_detail(entry: OutboxEntry, *, color: bool | None = None) -> str:
    """Render one outbox entry as a multi-line detail view."""
    theme = TerminalTheme(color=color)
    status_tag = theme.paint(f"[{entry.status}]", _status_color(entry.status))
    fields = _render_key_value_fields(
        [
            ("idempotency_key", entry.idempotency_key),
            ("attempts", entry.attempts),
            ("created_at", entry.created_at),
        ]
    )
    if entry.sent_at is not None:
        fields.append(render_key_value_field("sent_at", entry.sent_at))
    if entry.deep_link is not None:
        fields.append(render_key_value_field("deep_link", entry.deep_link))
    return render_record_block(
        f"{entry.id} {status_tag} {entry.title}",
        fields,
        body=entry.body,
    )


def render_reflection_entry_summary(entry: ReflectionEntry, *, index: int | None = None, color: bool | None = None) -> str:
    """Render one reflection entry as a compact record plus title body."""
    theme = TerminalTheme(color=color)
    created = format_display_timestamp(entry.created_at) if entry.created_at else "-"
    tag = theme.tag("[reflection]", "reflection")
    label = f"[{index}] {tag}" if index is not None else tag
    fields: list[str] = []
    status_tag = theme.paint(f"[{entry.status}]", _status_color(entry.status))
    fields.extend(
        [
            render_key_value_field("status", status_tag),
            render_key_value_field("created", created),
            render_key_value_field("type", entry.candidate_type),
            render_key_value_field("score", f"{entry.composite_score:.2f}"),
        ]
    )
    return render_record_block(label, fields, body=entry.title)


def render_reflection_entry_detail(entry: ReflectionEntry, *, color: bool | None = None) -> str:
    """Render one reflection entry as a multi-line detail view."""
    theme = TerminalTheme(color=color)
    status_tag = theme.paint(f"[{entry.status}]", _status_color(entry.status))
    discussion = "approved" if entry.discussion_approved is True else ("rejected" if entry.discussion_approved is False else "N/A")
    fields = _render_key_value_fields(
        [
            ("id", entry.id),
            ("type", entry.candidate_type),
            ("score", f"{entry.composite_score:.2f}"),
            ("confidence", f"{entry.confidence:.2f}"),
            ("novelty", f"{entry.novelty:.2f}"),
            ("urgency", f"{entry.urgency:.2f}"),
            ("interruption", f"{entry.interruption_cost:.2f}"),
            ("discussion", discussion),
            ("deep_link", entry.deep_link),
            ("created_at", entry.created_at),
        ]
    )
    if entry.reviewed_at is not None:
        fields.append(render_key_value_field("reviewed_at", entry.reviewed_at))

    lines = [render_record_header(f"{status_tag} {entry.title}", fields)]
    lines.extend(render_record_body(entry.body))
    if entry.discussion_trace:
        for line in render_discussion_trace(list(entry.discussion_trace), title="discussion", color=color):
            lines.append(f"  {line}" if line else "")
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


def render_discussion_trace(trace: list[object], *, title: str = "discussion trace", color: bool | None = None) -> list[str]:
    """Render a discussion trace grouped by turn with per-speaker labels."""
    theme = TerminalTheme(color=color)
    lines: list[str] = [_render_discussion_group_tag(title, theme)]
    current_turn: str | None = None

    for entry in trace:
        text = str(entry)
        turn_label, speaker, content = _parse_trace_entry(text)

        if turn_label is not None and turn_label != current_turn:
            if current_turn is not None:
                lines.append("")
            if speaker == turn_label:
                lines.append(f"  {_render_discussion_group_tag(turn_label, theme)} {content}")
                current_turn = turn_label
                continue
            lines.append(f"  {_render_discussion_group_tag(turn_label, theme)}")
            current_turn = turn_label

        if speaker is not None:
            tag = _color_persona_trace_tag(f"[{speaker}]", speaker, theme)
            lines.append(f"    {tag} {content}")
        elif turn_label is not None:
            lines.append(f"    {'':18} {content}")
        else:
            indent = "    " if current_turn is not None else "  "
            lines.append(f"{indent}{text}")

    return lines


def _render_discussion_group_tag(label: str, theme: TerminalTheme) -> str:
    return theme.paint(f"[{label}]", _discussion_group_color(label))


def _discussion_group_color(label: str) -> str:
    if label == "host":
        return _persona_color("host")
    if label == "candidate":
        return "33"
    if label.startswith("turn-"):
        return "90"
    return "35"


def _color_persona_trace_tag(tag: str, speaker: str, theme: TerminalTheme) -> str:
    padded = f"{tag:<18}"
    if speaker.endswith("_self") or speaker in {"host", "synthesis"}:
        return theme.paint(padded, _persona_color(speaker))
    return padded


def render_host_decision(event: LogEvent, *, color: bool | None = None) -> list[str]:
    """Render a structured host discussion decision event for REPL display."""
    theme = TerminalTheme(color=color)
    header = theme.tag("[host decision]", "persona")
    lines = [_render_log_header(header, event.event, event, theme, inline_status=False)]
    lines.extend(_render_status_body(event, theme))
    lines.extend(render_record_body(event.message))
    return lines


# ---------------------------------------------------------------------------
# Shared Rich utilities — used by reason.py, trace.py, and other renderers
# ---------------------------------------------------------------------------

def _rich_render_to_ansi(renderable: object) -> str:
    """Render a Rich renderable to an ANSI string via StringIO Console."""
    from rich.console import Console
    import io
    buf = io.StringIO()
    Console(file=buf, force_terminal=True, width=160).print(renderable, end="")
    return buf.getvalue().rstrip()


def render_markdown(text: str, theme: TerminalTheme) -> str:
    """Render markdown text to ANSI-formatted string if color is enabled."""
    if not theme.color:
        return text
    from rich.markdown import Markdown
    return _rich_render_to_ansi(Markdown(text))


def render_section(title: str, values: list[str], theme: TerminalTheme) -> list[str]:
    """Render a bulleted section with colored label and markdown items."""
    if not values:
        return []
    label = theme.tag(f"{title}:", "reasoning")
    lines = [f"  {label}"]
    lines.extend(f"    - {render_markdown(value, theme)}" for value in values)
    return lines
