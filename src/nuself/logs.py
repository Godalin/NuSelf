"""Structured local JSONL logs for NuSelf."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Generator, Iterable, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
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
    "daemon",
    "chat",
    "memory",
    "persona",
    "outbox",
    "reflection",
    "reasoning",
    "storage",
]

LOG_COMPONENTS: tuple[LogComponent, ...] = (
    "daemon",
    "chat",
    "memory",
    "persona",
    "outbox",
    "reflection",
    "reasoning",
    "storage",
)
_AUDIT_EVENT_NAME = re.compile(
    r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$"
)
_LOG_LOCKS_GUARD = Lock()
_LOG_WRITE_LOCKS: dict[Path, RLock] = {}


@dataclass(frozen=True)
class LogRetentionPolicy:
    """Bounded size and backup count for one component log."""

    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 3

    def __post_init__(self) -> None:
        if self.max_bytes < 1:
            raise ValueError("log max_bytes must be positive")
        if self.backup_count < 1:
            raise ValueError("log backup_count must be positive")


DEFAULT_LOG_RETENTION = LogRetentionPolicy()
LogEventObserver = Callable[["LogEvent"], None]
_CURRENT_LOG_EVENT_OBSERVERS: ContextVar[tuple[LogEventObserver, ...]] = ContextVar(
    "nuself_log_event_observers",
    default=(),
)


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
    retention_policy: LogRetentionPolicy = DEFAULT_LOG_RETENTION,
) -> LogEvent:
    """Append a structured log event and return it."""

    _require_log_identity(component, event)
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
    return _append_log_event(
        event_record,
        project_root=project_root,
        retention_policy=retention_policy,
    )


def write_runtime_event(
    envelope: RuntimeEnvelope,
    *,
    project_root: Path | None = None,
    retention_policy: LogRetentionPolicy = DEFAULT_LOG_RETENTION,
) -> LogEvent:
    """Persist an event envelope as an audit projection with the same identity."""

    if envelope.kind != "event":
        raise ValueError("log event sink requires an event envelope")
    if envelope.producer not in LOG_COMPONENTS:
        raise ValueError("runtime event producer is not a log component")
    _require_log_identity(
        envelope.producer,
        envelope.name,
    )
    payload = envelope.payload
    level = payload.get("level", "info")
    if level not in {"debug", "info", "warning", "error"}:
        raise ValueError("runtime event log level is invalid")
    message = payload.get("message", envelope.name)
    if not isinstance(message, str):
        raise TypeError("runtime event log message must be a string")
    metadata_value = payload.get("metadata")
    metadata: dict[str, object] | None = None
    if isinstance(metadata_value, Mapping):
        metadata_mapping = cast(Mapping[object, object], metadata_value)
        metadata = cast(dict[str, object], _safe_json_value(metadata_mapping))
    event_record = LogEvent(
        time=envelope.created_at,
        level=cast(LogLevel, level),
        component=envelope.producer,
        event=envelope.name,
        message=message,
        event_id=envelope.message_id,
        schema_version=envelope.schema_version,
        thread_id=envelope.context.thread_id,
        request_id=envelope.context.request_id,
        turn_id=envelope.context.turn_id,
        job_id=envelope.context.job_id,
        trace_id=envelope.context.trace_id,
        source=envelope.context.source,
        node=_optional_str(payload.get("node")),
        duration_ms=_optional_int(payload.get("duration_ms")),
        status=_optional_str(payload.get("status")),
        error=_optional_str(payload.get("error")),
        metadata=metadata,
    )
    return _append_log_event(
        event_record,
        project_root=project_root,
        retention_policy=retention_policy,
    )


def runtime_event_log_sink(
    project_root: Path | None = None,
    *,
    retention_policy: LogRetentionPolicy = DEFAULT_LOG_RETENTION,
) -> Callable[[RuntimeEnvelope], None]:
    """Build an event subscriber that persists audit projections."""

    def sink(envelope: RuntimeEnvelope) -> None:
        write_runtime_event(
            envelope,
            project_root=project_root,
            retention_policy=retention_policy,
        )

    return sink


def _append_log_event(
    event_record: LogEvent,
    *,
    project_root: Path | None,
    retention_policy: LogRetentionPolicy,
) -> LogEvent:
    paths = runtime_paths(project_root)
    ensure_runtime_dirs(paths)
    path = log_path(event_record.component, project_root=paths.project_root)
    line = (
        json.dumps(event_record.to_record(), sort_keys=True, ensure_ascii=True) + "\n"
    )
    encoded_size = len(line.encode("utf-8"))
    lock_path = path.with_name(f"{path.name}.lock")
    with _log_write_lock(path), lock_path.open("a", encoding="utf-8") as lock_file:
        flock(lock_file.fileno(), LOCK_EX)
        try:
            _rotate_log_if_needed(
                path,
                incoming_bytes=encoded_size,
                policy=retention_policy,
            )
            with path.open("a", encoding="utf-8") as log_file:
                log_file.write(line)
                log_file.flush()
        finally:
            flock(lock_file.fileno(), LOCK_UN)
    for observer in _CURRENT_LOG_EVENT_OBSERVERS.get():
        try:
            observer(event_record)
        except Exception as exc:
            _report_log_observer_failure(
                observer,
                exc,
                project_root=paths.project_root,
            )
            continue
    return event_record


def _report_log_observer_failure(
    observer: LogEventObserver,
    exc: Exception,
    *,
    project_root: Path,
) -> None:
    token = _CURRENT_LOG_EVENT_OBSERVERS.set(())
    try:
        try:
            write_log_event(
                "daemon",
                "log_observer_failed",
                "process-local log observer failed",
                project_root=project_root,
                level="warning",
                status="error",
                error=str(exc),
                metadata={
                    "error_type": type(exc).__name__,
                    "observer_type": type(observer).__name__,
                },
            )
        except Exception:
            pass
    finally:
        _CURRENT_LOG_EVENT_OBSERVERS.reset(token)


def _rotate_log_if_needed(
    path: Path,
    *,
    incoming_bytes: int,
    policy: LogRetentionPolicy,
) -> None:
    try:
        current_size = path.stat().st_size
    except FileNotFoundError:
        return
    if current_size == 0 or current_size + incoming_bytes <= policy.max_bytes:
        return
    oldest = _rotated_log_path(path, policy.backup_count)
    oldest.unlink(missing_ok=True)
    for index in range(policy.backup_count - 1, 0, -1):
        source = _rotated_log_path(path, index)
        if source.exists():
            source.replace(_rotated_log_path(path, index + 1))
    path.replace(_rotated_log_path(path, 1))


def _rotated_log_path(path: Path, index: int) -> Path:
    return path.with_name(f"{path.name}.{index}")


def current_log_context() -> LogContext:
    """Return the shared runtime correlation context."""

    return current_runtime_context()


log_context = runtime_context


@contextmanager
def observe_log_events(
    observer: LogEventObserver,
) -> Generator[None, None, None]:
    """Add one best-effort projection in this execution context."""

    current = _CURRENT_LOG_EVENT_OBSERVERS.get()
    token: Token[tuple[LogEventObserver, ...]] = (
        _CURRENT_LOG_EVENT_OBSERVERS.set((*current, observer))
    )
    try:
        yield
    finally:
        _CURRENT_LOG_EVENT_OBSERVERS.reset(token)


def log_path(component: LogComponent, *, project_root: Path | None = None) -> Path:
    """Return the local log path for a component."""

    paths = runtime_paths(project_root)
    if component == "daemon":
        return paths.daemon_log_path
    if component == "outbox":
        return paths.outbox_log_path
    return paths.logs_dir / f"{component}.log"


def _require_log_identity(
    component: object,
    event: object,
) -> None:
    if component not in LOG_COMPONENTS:
        raise ValueError("log component is invalid")
    if not isinstance(event, str) or _AUDIT_EVENT_NAME.fullmatch(event) is None:
        raise ValueError("log event name is invalid")


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
        active_path = log_path(current_component, project_root=project_root)
        for path in _component_log_paths(active_path):
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


def _component_log_paths(active_path: Path) -> tuple[Path, ...]:
    backups: list[tuple[int, Path]] = []
    for candidate in active_path.parent.glob(f"{active_path.name}.*"):
        suffix = candidate.name.removeprefix(f"{active_path.name}.")
        if suffix.isdigit():
            backups.append((int(suffix), candidate))
    backups.sort(key=lambda item: item[0], reverse=True)
    return (*(path for _, path in backups), active_path)


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
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
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
        identities: dict[LogComponent, tuple[int, int] | None] | None = None,
    ) -> None:
        self.seen_event_keys = seen_event_keys or set()
        self.offsets = offsets or {}
        self.identities = identities or {}

    @classmethod
    def from_project(cls, project_root: Path | None) -> InteractiveLogCursor:
        offsets: dict[LogComponent, int] = {}
        identities: dict[LogComponent, tuple[int, int] | None] = {}
        for component in LOG_COMPONENTS:
            path = log_path(component, project_root=project_root)
            try:
                stat = path.stat()
                offsets[component] = stat.st_size
                identities[component] = (stat.st_dev, stat.st_ino)
            except FileNotFoundError:
                offsets[component] = 0
                identities[component] = None
        return cls(offsets=offsets, identities=identities)

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
        previous_identity = self.identities.get(component)
        try:
            stat = path.stat()
        except FileNotFoundError:
            self.offsets[component] = 0
            self.identities[component] = None
            return []
        current_identity = (stat.st_dev, stat.st_ino)
        parsed_events: list[LogEvent] = []
        if previous_identity is not None and previous_identity != current_identity:
            rotated_path = _find_log_with_identity(
                path,
                previous_identity,
            )
            if rotated_path is not None:
                rotated_events, _ = _read_log_path(
                    rotated_path,
                    component=component,
                    offset=offset,
                )
                parsed_events.extend(rotated_events)
            offset = 0
        elif stat.st_size < offset:
            offset = 0
        current_events, next_offset = _read_log_path(
            path,
            component=component,
            offset=offset,
        )
        parsed_events.extend(current_events)
        self.offsets[component] = next_offset
        self.identities[component] = current_identity
        return parsed_events


def _find_log_with_identity(
    active_path: Path,
    identity: tuple[int, int],
) -> Path | None:
    for candidate in _component_log_paths(active_path):
        if candidate == active_path:
            continue
        try:
            stat = candidate.stat()
        except FileNotFoundError:
            continue
        if (stat.st_dev, stat.st_ino) == identity:
            return candidate
    return None


def _read_log_path(
    path: Path,
    *,
    component: LogComponent,
    offset: int,
) -> tuple[list[LogEvent], int]:
    with path.open("rb") as log_file:
        log_file.seek(offset)
        appended = log_file.read()
    complete_length = _complete_line_length(appended)
    parsed_events: list[LogEvent] = []
    for raw_line in appended[:complete_length].splitlines():
        line = raw_line.decode("utf-8", errors="replace")
        parsed = _parse_log_line(line, component)
        if parsed is not None:
            parsed_events.append(parsed)
    return parsed_events, offset + complete_length


def _complete_line_length(content: bytes) -> int:
    """Return the byte boundary after the last complete newline."""

    last_newline = content.rfind(b"\n")
    return last_newline + 1 if last_newline >= 0 else 0
