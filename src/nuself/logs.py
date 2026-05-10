"""Structured local JSONL logs for NuSelf."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Literal, cast

from nuself.config import ensure_runtime_dirs, runtime_paths
from nuself.domain.memory import now_iso

LogLevel = Literal["debug", "info", "warning", "error"]
LogComponent = Literal["daemon", "chat", "memory", "persona", "outbox", "reflection"]

LOG_COMPONENTS: tuple[LogComponent, ...] = ("daemon", "chat", "memory", "persona", "outbox", "reflection")


@dataclass(frozen=True)
class LogEvent:
    """One local NuSelf log event."""

    time: str
    level: LogLevel
    component: LogComponent
    event: str
    message: str
    thread_id: str | None = None
    request_id: str | None = None
    node: str | None = None
    duration_ms: int | None = None
    status: str | None = None
    error: str | None = None
    metadata: dict[str, object] | None = None

    def to_record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "time": self.time,
            "level": self.level,
            "component": self.component,
            "event": self.event,
            "message": self.message,
        }
        for key, value in (
            ("thread_id", self.thread_id),
            ("request_id", self.request_id),
            ("node", self.node),
            ("duration_ms", self.duration_ms),
            ("status", self.status),
            ("error", self.error),
            ("metadata", self.metadata),
        ):
            if value is not None:
                record[key] = _safe_json_value(value)
        return record

    @classmethod
    def from_record(cls, record: dict[str, object]) -> "LogEvent":
        component = record.get("component")
        level = record.get("level")
        event = record.get("event")
        message = record.get("message")
        timestamp = record.get("time")
        if component not in LOG_COMPONENTS:
            raise ValueError("log component is invalid")
        if level not in {"debug", "info", "warning", "error"}:
            raise ValueError("log level is invalid")
        if not isinstance(event, str) or not isinstance(message, str) or not isinstance(timestamp, str):
            raise ValueError("log event fields are invalid")
        metadata = record.get("metadata")
        return cls(
            time=timestamp,
            level=cast(LogLevel, level),
            component=component,
            event=event,
            message=message,
            thread_id=_optional_str(record.get("thread_id")),
            request_id=_optional_str(record.get("request_id")),
            node=_optional_str(record.get("node")),
            duration_ms=_optional_int(record.get("duration_ms")),
            status=_optional_str(record.get("status")),
            error=_optional_str(record.get("error")),
            metadata=cast(dict[str, object], metadata) if isinstance(metadata, dict) else None,
        )


def write_log_event(
    component: LogComponent,
    event: str,
    message: str,
    *,
    project_root: Path | None = None,
    level: LogLevel = "info",
    thread_id: str | None = None,
    request_id: str | None = None,
    node: str | None = None,
    duration_ms: int | None = None,
    status: str | None = None,
    error: str | None = None,
    metadata: dict[str, object] | None = None,
) -> LogEvent:
    """Append a structured log event and return it."""

    event_record = LogEvent(
        time=now_iso(),
        level=level,
        component=component,
        event=event,
        message=message,
        thread_id=thread_id,
        request_id=request_id,
        node=node,
        duration_ms=duration_ms,
        status=status,
        error=error,
        metadata=metadata,
    )
    paths = runtime_paths(project_root)
    ensure_runtime_dirs(paths)
    with log_path(component, project_root=paths.project_root).open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(event_record.to_record(), sort_keys=True, ensure_ascii=True))
        log_file.write("\n")
    return event_record


def log_path(component: LogComponent, *, project_root: Path | None = None) -> Path:
    """Return the local log path for a component."""

    paths = runtime_paths(project_root)
    if component == "daemon":
        return paths.daemon_log_path
    if component == "outbox":
        return paths.outbox_log_path
    return paths.logs_dir / f"{component}.log"


def read_log_events(
    *,
    project_root: Path | None = None,
    component: LogComponent | None = None,
    tail: int | None = None,
) -> list[LogEvent]:
    """Read structured events from local logs, tolerating legacy plain lines."""

    events: list[LogEvent] = []
    components: Iterable[LogComponent] = (component,) if component is not None else LOG_COMPONENTS
    for current_component in components:
        path = log_path(current_component, project_root=project_root)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            continue
        for line in lines:
            parsed = _parse_log_line(line, current_component)
            if parsed is not None:
                events.append(parsed)
    events.sort(key=lambda item: item.time)
    if tail is not None and tail > 0:
        return events[-tail:]
    return events


def _parse_log_line(line: str, component: LogComponent) -> LogEvent | None:
    stripped = line.strip()
    if stripped == "":
        return None
    try:
        parsed: object = json.loads(stripped)
    except json.JSONDecodeError:
        return LogEvent(
            time="",
            level="info",
            component=component,
            event="legacy",
            message=stripped,
        )
    if not isinstance(parsed, dict):
        return None
    try:
        return LogEvent.from_record(cast(dict[str, object], parsed))
    except ValueError:
        return None


def _safe_json_value(value: object) -> object:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list | tuple):
        sequence = cast(Iterable[object], value)
        return [_safe_json_value(item) for item in sequence]
    if isinstance(value, dict):
        mapping = cast(dict[object, object], value)
        return {str(key): _safe_json_value(item) for key, item in mapping.items()}
    return str(value)


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None
