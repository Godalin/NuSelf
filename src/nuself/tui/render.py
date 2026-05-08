"""Compact terminal renderers for NuSelf REPL output."""

from __future__ import annotations

import json
import os
import sys

from nuself.logs import LogEvent


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
