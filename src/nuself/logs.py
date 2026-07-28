"""Structured local JSONL logs for NuSelf."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Generator, Iterable, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import InitVar, dataclass, field
from datetime import UTC, datetime
from fcntl import LOCK_EX, LOCK_UN, flock
from pathlib import Path
from threading import Lock, RLock
from typing import Literal, cast
from uuid import uuid4

from nuself.config import ensure_runtime_dirs, runtime_paths
from nuself.runtime.context import (
    RuntimeContext,
    current_runtime_context,
)
from nuself.runtime.diagnostics import emit_runtime_warning
from nuself.runtime.event_payloads import RuntimeLogEventPayload
from nuself.runtime.messages import (
    RUNTIME_SCHEMA_VERSION,
    RuntimeEnvelope,
    freeze_json_value,
    thaw_json_value,
)

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
_LEGACY_LOG_INSTANT = datetime.min.replace(tzinfo=UTC)


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
    metadata: Mapping[str, object] | None = None
    _allow_empty_time: InitVar[bool] = False
    _instant: datetime | None = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self, _allow_empty_time: bool) -> None:
        if not isinstance(self.time, str):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("log time must be a string")
        if self.level not in {"debug", "info", "warning", "error"}:
            raise ValueError("log level is invalid")
        if self.component not in LOG_COMPONENTS:
            raise ValueError("log component is invalid")
        for field_name in ("event", "message"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"log {field_name} must be a string")
        if (self.event_id is None) != (self.schema_version is None):
            raise ValueError(
                "log event_id and schema_version must both be present or absent"
            )
        if self.event_id is not None and (
            not isinstance(self.event_id, str)  # pyright: ignore[reportUnnecessaryIsInstance]
            or not self.event_id.strip()
        ):
            raise ValueError("log event_id must not be blank")
        if self.schema_version is not None and (
            type(self.schema_version) is not int
            or self.schema_version != RUNTIME_SCHEMA_VERSION
        ):
            raise ValueError("log schema_version is unsupported")
        object.__setattr__(
            self,
            "_instant",
            _parse_log_timestamp(
                self.time,
                allow_empty=(
                    _allow_empty_time
                    and self.event == "legacy"
                    and self.event_id is None
                    and self.schema_version is None
                ),
            ),
        )
        for field_name in (
            "thread_id",
            "request_id",
            "turn_id",
            "job_id",
            "trace_id",
            "source",
            "node",
            "status",
            "error",
        ):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, str):
                raise TypeError(f"log {field_name} must be a string")
        if self.duration_ms is not None and (
            type(self.duration_ms) is not int or self.duration_ms < 0
        ):
            raise TypeError(
                "log duration_ms must be a non-negative integer"
            )
        if self.schema_version is not None:
            _require_log_identity(self.component, self.event)
        if self.metadata is None:
            return
        if not isinstance(self.metadata, Mapping):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("log event metadata must be a mapping")
        object.__setattr__(
            self,
            "metadata",
            cast(
                Mapping[str, object],
                freeze_json_value(self.metadata),
            ),
        )

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
                record[key] = thaw_json_value(value)
        return record

    def chronological_key(self) -> tuple[int, datetime]:
        """Return an instant-aware stable sorting key."""

        if self._instant is None:
            return (0, _LEGACY_LOG_INSTANT)
        return (1, self._instant)

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
        return cls(
            time=timestamp,
            level=cast(LogLevel, level),
            component=component,
            event=event,
            message=message,
            event_id=_record_optional_str(record, "event_id"),
            schema_version=_record_optional_int(
                record,
                "schema_version",
            ),
            thread_id=_record_optional_str(record, "thread_id"),
            request_id=_record_optional_str(record, "request_id"),
            turn_id=_record_optional_str(record, "turn_id"),
            job_id=_record_optional_str(record, "job_id"),
            trace_id=_record_optional_str(record, "trace_id"),
            source=_record_optional_str(record, "source"),
            node=_record_optional_str(record, "node"),
            duration_ms=_record_optional_int(record, "duration_ms"),
            status=_record_optional_str(record, "status"),
            error=_record_optional_str(record, "error"),
            metadata=_record_optional_mapping(record, "metadata"),
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

    envelope = create_audit_envelope(
        component,
        event,
        message,
        level=level,
        thread_id=thread_id,
        request_id=request_id,
        turn_id=turn_id,
        job_id=job_id,
        trace_id=trace_id,
        source=source,
        node=node,
        duration_ms=duration_ms,
        status=status,
        error=error,
        metadata=metadata,
    )
    return write_audit_envelope(
        envelope,
        project_root=project_root,
        retention_policy=retention_policy,
    )


def create_audit_envelope(
    component: LogComponent,
    event: str,
    message: str,
    *,
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
) -> RuntimeEnvelope:
    """Create one complete immutable direct-audit envelope."""

    _require_log_identity(component, event)
    context = current_runtime_context()
    payload = RuntimeLogEventPayload(
        message=message,
        level=level,
        node=node,
        duration_ms=duration_ms,
        status=status,
        error=error,
        metadata=metadata,
    )
    return RuntimeEnvelope(
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
        payload=payload.to_mapping(),
    )


def write_audit_envelope(
    envelope: RuntimeEnvelope,
    *,
    project_root: Path | None = None,
    retention_policy: LogRetentionPolicy = DEFAULT_LOG_RETENTION,
) -> LogEvent:
    """Persist one self-contained direct-audit envelope."""

    return _write_envelope_log_projection(
        envelope,
        required_kind="audit",
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

    return _write_envelope_log_projection(
        envelope,
        required_kind="event",
        project_root=project_root,
        retention_policy=retention_policy,
    )


def _write_envelope_log_projection(
    envelope: RuntimeEnvelope,
    *,
    required_kind: Literal["audit", "event"],
    project_root: Path | None,
    retention_policy: LogRetentionPolicy,
) -> LogEvent:
    if envelope.kind != required_kind:
        raise ValueError(
            f"log projection requires an {required_kind} envelope"
        )
    if envelope.producer not in LOG_COMPONENTS:
        raise ValueError("log envelope producer is not a log component")
    _require_log_identity(
        envelope.producer,
        envelope.name,
    )
    payload = RuntimeLogEventPayload.from_mapping(envelope.payload)
    if required_kind == "audit" and payload.message is None:
        raise ValueError("audit envelope requires a message")
    event_record = LogEvent(
        time=envelope.created_at,
        level=payload.level,
        component=envelope.producer,
        event=envelope.name,
        message=(
            payload.message
            if payload.message is not None
            else envelope.name
        ),
        event_id=envelope.message_id,
        schema_version=envelope.schema_version,
        thread_id=envelope.context.thread_id,
        request_id=envelope.context.request_id,
        turn_id=envelope.context.turn_id,
        job_id=envelope.context.job_id,
        trace_id=envelope.context.trace_id,
        source=envelope.context.source,
        node=payload.node,
        duration_ms=payload.duration_ms,
        status=payload.status,
        error=payload.error,
        metadata=payload.metadata,
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
            try:
                _rotate_log_if_needed(
                    path,
                    incoming_bytes=encoded_size,
                    policy=retention_policy,
                )
            except OSError as exc:
                _report_log_rotation_failure(event_record.component, exc)
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


def _report_log_rotation_failure(
    component: LogComponent,
    exc: OSError,
) -> None:
    emit_runtime_warning(
        "logs/rotation_failed: "
        f"component={component} error_type={type(exc).__name__}; "
        "continuing without guaranteed retention bounds",
        stacklevel=3,
    )


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
        except Exception as log_exc:
            observer_error = str(exc).strip() or type(exc).__name__
            log_error = str(log_exc).strip() or type(log_exc).__name__
            emit_runtime_warning(
                "daemon/log_observer_failed: "
                f"{observer_error}; structured logging failed: {log_error}",
                stacklevel=3,
            )
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
            corruptions: list[Exception] = []
            for line in lines:
                parsed = _parse_log_line(
                    line,
                    current_component,
                    on_corrupt=corruptions.append,
                )
                if parsed is not None:
                    events.append(parsed)
            _report_log_read_corruptions(
                path,
                current_component,
                corruptions,
            )
    events.sort(key=_log_event_chronological_key)
    events, identity_conflicts = _reconcile_log_event_identities(
        events,
        seen_event_keys=set(),
        seen_event_fingerprints={},
    )
    _report_log_identity_conflicts(identity_conflicts)
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


def _parse_log_line(
    line: str,
    component: LogComponent,
    *,
    on_corrupt: Callable[[Exception], None] | None = None,
) -> LogEvent | None:
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
            _allow_empty_time=True,
        )
    if not isinstance(parsed, dict):
        if on_corrupt is not None:
            on_corrupt(
                ValueError("structured log record must be a JSON object")
            )
        return None
    try:
        return LogEvent.from_record(cast(dict[str, object], parsed))
    except (TypeError, ValueError) as exc:
        if on_corrupt is not None:
            on_corrupt(exc)
        return None


def _report_log_read_corruptions(
    path: Path,
    component: LogComponent,
    corruptions: list[Exception],
) -> None:
    if not corruptions:
        return
    first = corruptions[0]
    detail = str(first).strip() or type(first).__name__
    emit_runtime_warning(
        "logs/corrupt_records_skipped: "
        f"component={component} file={path.name} "
        f"count={len(corruptions)} "
        f"first_error={type(first).__name__}: {detail}",
        stacklevel=3,
    )


def _parse_log_timestamp(
    value: str,
    *,
    allow_empty: bool,
) -> datetime | None:
    if value == "":
        if allow_empty:
            return None
        raise ValueError("structured log time must not be empty")
    try:
        instant = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            "log time must be an ISO-8601 timestamp"
        ) from exc
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("log time must include a timezone")
    return instant


def _log_event_chronological_key(
    event: LogEvent,
) -> tuple[int, datetime]:
    return event.chronological_key()


def _record_optional_str(
    record: Mapping[str, object],
    field_name: str,
) -> str | None:
    value = record.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"log {field_name} must be a string")
    return value


def _record_optional_int(
    record: Mapping[str, object],
    field_name: str,
) -> int | None:
    value = record.get(field_name)
    if value is None:
        return None
    if type(value) is not int:
        raise TypeError(f"log {field_name} must be an integer")
    return value


def _record_optional_mapping(
    record: Mapping[str, object],
    field_name: str,
) -> Mapping[str, object] | None:
    value = record.get(field_name)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError(f"log {field_name} must be a mapping")
    return cast(Mapping[str, object], value)


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


def _log_event_fingerprint(event: LogEvent) -> str:
    return json.dumps(
        event.to_record(),
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )


def _reconcile_log_event_identities(
    events: Iterable[LogEvent],
    *,
    seen_event_keys: set[str],
    seen_event_fingerprints: dict[str, str],
) -> tuple[list[LogEvent], list[LogEvent]]:
    canonical: list[LogEvent] = []
    conflicts: list[LogEvent] = []
    for event in events:
        key = log_event_key(event)
        fingerprint = _log_event_fingerprint(event)
        if key not in seen_event_keys:
            seen_event_keys.add(key)
            seen_event_fingerprints[key] = fingerprint
            canonical.append(event)
            continue
        existing = seen_event_fingerprints.get(key)
        if existing is None:
            seen_event_fingerprints[key] = fingerprint
            continue
        if existing != fingerprint:
            conflicts.append(event)
    return canonical, conflicts


def _report_log_identity_conflicts(
    conflicts: list[LogEvent],
) -> None:
    if not conflicts:
        return
    first = conflicts[0]
    emit_runtime_warning(
        "logs/event_identity_conflict: "
        f"count={len(conflicts)} "
        f"first_component={first.component} "
        f"first_event={first.event}",
        stacklevel=3,
    )


class InteractiveLogCursor:
    """Incrementally reads complete lines appended after cursor creation."""

    def __init__(
        self,
        seen_event_keys: set[str] | None = None,
        seen_event_fingerprints: dict[str, str] | None = None,
        offsets: dict[LogComponent, int] | None = None,
        identities: dict[LogComponent, tuple[int, int] | None] | None = None,
    ) -> None:
        self.seen_event_keys: set[str] = (
            seen_event_keys if seen_event_keys is not None else set()
        )
        self.seen_event_fingerprints: dict[str, str] = (
            seen_event_fingerprints
            if seen_event_fingerprints is not None
            else {}
        )
        self.offsets = offsets if offsets is not None else {}
        self.identities = identities if identities is not None else {}

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

    def mark_seen(self, events: Iterable[LogEvent]) -> None:
        """Register events delivered through a non-file transport."""

        _, conflicts = _reconcile_log_event_identities(
            events,
            seen_event_keys=self.seen_event_keys,
            seen_event_fingerprints=self.seen_event_fingerprints,
        )
        _report_log_identity_conflicts(conflicts)

    def read_new_events(self, project_root: Path | None) -> list[LogEvent]:
        events: list[LogEvent] = []
        for component in LOG_COMPONENTS:
            events.extend(self._read_component(component, project_root))
        events.sort(key=_log_event_chronological_key)
        new_events, conflicts = _reconcile_log_event_identities(
            events,
            seen_event_keys=self.seen_event_keys,
            seen_event_fingerprints=self.seen_event_fingerprints,
        )
        _report_log_identity_conflicts(conflicts)
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
    corruptions: list[Exception] = []
    for raw_line in appended[:complete_length].splitlines():
        line = raw_line.decode("utf-8", errors="replace")
        parsed = _parse_log_line(
            line,
            component,
            on_corrupt=corruptions.append,
        )
        if parsed is not None:
            parsed_events.append(parsed)
    _report_log_read_corruptions(path, component, corruptions)
    return parsed_events, offset + complete_length


def _complete_line_length(content: bytes) -> int:
    """Return the byte boundary after the last complete newline."""

    last_newline = content.rfind(b"\n")
    return last_newline + 1 if last_newline >= 0 else 0
