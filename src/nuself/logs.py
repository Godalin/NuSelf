"""Structured local JSONL logs for NuSelf."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from fcntl import LOCK_EX, LOCK_UN, flock
from pathlib import Path
from threading import Lock, RLock
from typing import Literal, cast
from uuid import uuid4

from nuself.config import ensure_runtime_dirs, runtime_paths
from nuself.runtime.context import (
    RuntimeContext,
    current_runtime_context,
    runtime_context,
)
from nuself.runtime.messages import RUNTIME_SCHEMA_VERSION, RuntimeEnvelope

LogLevel = Literal["debug", "info", "warning", "error"]
LogComponent = Literal[
    "daemon", "chat", "memory", "persona", "outbox", "reflection", "reasoning"
]

LOG_COMPONENTS: tuple[LogComponent, ...] = (
    "daemon",
    "chat",
    "memory",
    "persona",
    "outbox",
    "reflection",
    "reasoning",
)
_LOG_LOCKS_GUARD = Lock()
_LOG_WRITE_LOCKS: dict[Path, RLock] = {}


LogContext = RuntimeContext


def _log_write_lock(path: Path) -> RLock:
    normalized = path.absolute()
    with _LOG_LOCKS_GUARD:
        return _LOG_WRITE_LOCKS.setdefault(normalized, RLock())


@dataclass(frozen=True)
class LogEvent:
    """One local NuSelf log event."""

    time: str
    level: LogLevel
    component: LogComponent
    event: str
    message: str
    event_id: str | None = field(default_factory=lambda: uuid4().hex)
    schema_version: int | None = RUNTIME_SCHEMA_VERSION
    thread_id: str | None = None
    request_id: str | None = None
    turn_id: str | None = None
    job_id: str | None = None
    trace_id: str | None = None
    source: str | None = None
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
            ("event_id", self.event_id),
            ("schema_version", self.schema_version),
            ("thread_id", self.thread_id),
            ("request_id", self.request_id),
            ("turn_id", self.turn_id),
            ("job_id", self.job_id),
            ("trace_id", self.trace_id),
            ("source", self.source),
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
    def from_record(cls, record: dict[str, object]) -> LogEvent:
        component = record.get("component")
        level = record.get("level")
        event = record.get("event")
        message = record.get("message")
        timestamp = record.get("time")
        if component not in LOG_COMPONENTS:
            raise ValueError("log component is invalid")
        if level not in {"debug", "info", "warning", "error"}:
            raise ValueError("log level is invalid")
        if (
            not isinstance(event, str)
            or not isinstance(message, str)
            or not isinstance(timestamp, str)
        ):
            raise ValueError("log event fields are invalid")
        metadata = record.get("metadata")
        event_id = record.get("event_id")
        schema_version = record.get("schema_version")
        return cls(
            time=timestamp,
            level=cast(LogLevel, level),
            component=component,
            event=event,
            message=message,
            event_id=event_id if isinstance(event_id, str) else None,
            schema_version=schema_version if isinstance(schema_version, int) else None,
            thread_id=_optional_str(record.get("thread_id")),
            request_id=_optional_str(record.get("request_id")),
            turn_id=_optional_str(record.get("turn_id")),
            job_id=_optional_str(record.get("job_id")),
            trace_id=_optional_str(record.get("trace_id")),
            source=_optional_str(record.get("source")),
            node=_optional_str(record.get("node")),
            duration_ms=_optional_int(record.get("duration_ms")),
            status=_optional_str(record.get("status")),
            error=_optional_str(record.get("error")),
            metadata=cast(dict[str, object], metadata)
            if isinstance(metadata, dict)
            else None,
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
    turn_id: str | None = None,
    job_id: str | None = None,
    trace_id: str | None = None,
    source: str | None = None,
    node: str | None = None,
    duration_ms: int | None = None,
    status: str | None = None,
    error: str | None = None,
    metadata: dict[str, object] | None = None,
) -> LogEvent:
    """Append a structured log event and return it."""

    context = current_log_context()
    envelope = RuntimeEnvelope(
        kind="audit",
        name=event,
        producer=component,
        context=RuntimeContext(
            thread_id=thread_id if thread_id is not None else context.thread_id,
            request_id=request_id if request_id is not None else context.request_id,
            turn_id=turn_id if turn_id is not None else context.turn_id,
            job_id=job_id if job_id is not None else context.job_id,
            trace_id=trace_id if trace_id is not None else context.trace_id,
            source=source if source is not None else context.source,
        ),
    )
    event_record = LogEvent(
        time=envelope.created_at,
        level=level,
        component=component,
        event=event,
        message=message,
        event_id=envelope.message_id,
        schema_version=envelope.schema_version,
        thread_id=envelope.context.thread_id,
        request_id=envelope.context.request_id,
        turn_id=envelope.context.turn_id,
        job_id=envelope.context.job_id,
        trace_id=envelope.context.trace_id,
        source=envelope.context.source,
        node=node,
        duration_ms=duration_ms,
        status=status,
        error=error,
        metadata=metadata,
    )
    paths = runtime_paths(project_root)
    ensure_runtime_dirs(paths)
    path = log_path(component, project_root=paths.project_root)
    line = (
        json.dumps(event_record.to_record(), sort_keys=True, ensure_ascii=True) + "\n"
    )
    with _log_write_lock(path), path.open("a", encoding="utf-8") as log_file:
        flock(log_file.fileno(), LOCK_EX)
        try:
            log_file.write(line)
            log_file.flush()
        finally:
            flock(log_file.fileno(), LOCK_UN)
    return event_record


def current_log_context() -> LogContext:
    """Return the shared runtime correlation context."""

    return current_runtime_context()


log_context = runtime_context


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
    components: Iterable[LogComponent] = (
        (component,) if component is not None else LOG_COMPONENTS
    )
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
            event_id=None,
            schema_version=None,
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


# ============================================================================
# Read-side utilities
# ============================================================================


def log_event_key(event: LogEvent) -> str:
    """Stable event identity with a legacy-record compatibility fallback."""

    if event.event_id is not None:
        return f"id:{event.event_id}"
    record = event.to_record()
    record.pop("event_id", None)
    record.pop("schema_version", None)
    return f"legacy:{json.dumps(record, sort_keys=True, ensure_ascii=True)}"


class InteractiveLogCursor:
    """Incrementally reads complete lines appended after cursor creation."""

    def __init__(
        self,
        seen_event_keys: set[str] | None = None,
        offsets: dict[LogComponent, int] | None = None,
    ) -> None:
        self.seen_event_keys = seen_event_keys or set()
        self.offsets = offsets or {}

    @classmethod
    def from_project(cls, project_root: Path | None) -> InteractiveLogCursor:
        offsets: dict[LogComponent, int] = {}
        for component in LOG_COMPONENTS:
            path = log_path(component, project_root=project_root)
            try:
                offsets[component] = path.stat().st_size
            except FileNotFoundError:
                offsets[component] = 0
        return cls(offsets=offsets)

    def read_new_events(self, project_root: Path | None) -> list[LogEvent]:
        events: list[LogEvent] = []
        for component in LOG_COMPONENTS:
            events.extend(self._read_component(component, project_root))
        events.sort(key=lambda item: item.time)
        new_events: list[LogEvent] = []
        for event in events:
            key = log_event_key(event)
            if key not in self.seen_event_keys:
                new_events.append(event)
            self.seen_event_keys.add(key)
        return new_events

    def _read_component(
        self,
        component: LogComponent,
        project_root: Path | None,
    ) -> list[LogEvent]:
        path = log_path(component, project_root=project_root)
        offset = self.offsets.get(component, 0)
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            self.offsets[component] = 0
            return []
        if size < offset:
            offset = 0
        with path.open("rb") as log_file:
            log_file.seek(offset)
            appended = log_file.read()
        complete_length = _complete_line_length(appended)
        self.offsets[component] = offset + complete_length
        parsed_events: list[LogEvent] = []
        for raw_line in appended[:complete_length].splitlines():
            line = raw_line.decode("utf-8", errors="replace")
            parsed = _parse_log_line(line, component)
            if parsed is not None:
                parsed_events.append(parsed)
        return parsed_events


def _complete_line_length(content: bytes) -> int:
    """Return the byte boundary after the last complete newline."""

    last_newline = content.rfind(b"\n")
    return last_newline + 1 if last_newline >= 0 else 0
