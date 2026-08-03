"""Structured local JSONL logs for NuSelf."""

from __future__ import annotations

import json
import os
from collections import OrderedDict
from collections.abc import Callable, Generator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from fcntl import LOCK_EX, LOCK_UN, flock
from pathlib import Path
from threading import Lock
from typing import IO, BinaryIO, Literal
from uuid import UUID, uuid4
from weakref import WeakValueDictionary

from nuself.config.settings import ensure_runtime_dirs, runtime_paths
from nuself.storage.filesystem import ensure_private_file
from nuself.runtime.context import (
    RuntimeContext,
    current_runtime_context,
)
from nuself.runtime.audit.definition import (
    AuditDefinitionRegistry,
    AuditEventDefinition,
)
from nuself.runtime.audit.types import (
    LOG_COMPONENTS,
    LogComponent,
    LogLevel,
)
from nuself.runtime.diagnostics import (
    diagnostic_exception_message,
    redact_sensitive_text,
    sanitize_diagnostic_metadata,
)
from nuself.runtime.event.payload import RuntimeLogEventPayload
from nuself.runtime.identities import (
    require_audit_event_name,
    require_runtime_event_name,
)
from nuself.log.record import LogEvent as _LogEvent
from nuself.log.warning import (
    LOG_TERMINAL_WARNING_REGISTRY,
)
from nuself.runtime.messages import RuntimeEnvelope
from nuself.runtime.warning import (
    emit_registered_terminal_warning,
)

type LogPersistenceOutcome = Literal[
    "not_persisted",
    "persisted",
    "uncertain",
]
_LOG_LOCKS_GUARD = Lock()
_LOG_WRITE_LOCKS: WeakValueDictionary[Path, Lock] = WeakValueDictionary()
_LOG_DIRECTORY_SYNC_GUARD = Lock()
_LOG_DIRECTORY_SYNC_CACHE_LIMIT = 256
_SYNCED_LOG_IDENTITIES: OrderedDict[Path, tuple[int, int]] = OrderedDict()


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
_LogEventProjection = Callable[["_LogEvent"], None]


@dataclass(frozen=True)
class _LogProjectionBinding:
    binding_id: UUID
    projection: _LogEventProjection


_CURRENT_LOG_EVENT_PROJECTIONS: ContextVar[
    tuple[_LogProjectionBinding, ...]
] = ContextVar(
    "nuself_log_event_projections",
    default=(),
)
_ACTIVE_LOG_EVENT_PROJECTIONS: ContextVar[frozenset[UUID]] = ContextVar(
    "nuself_active_log_event_projections",
    default=frozenset(),
)
_LOG_OBSERVER_FAILURE_MESSAGE = "process-local log observer failed"


def _build_log_infrastructure_audit_registry() -> AuditDefinitionRegistry:
    return (
        AuditDefinitionRegistry()
        .register(
            AuditEventDefinition(
                component="daemon",
                event="log_observer_failed",
                level="warning",
                status="error",
                error_policy="required",
            )
        )
        .seal()
    )


LOG_INFRASTRUCTURE_AUDIT_REGISTRY = (
    _build_log_infrastructure_audit_registry()
)


class LogAppendLifecycleError(RuntimeError):
    """Retain append, rollback, and active-handle close failures."""

    def __init__(
        self,
        *,
        primary_error: BaseException | None,
        rollback_error: BaseException | None,
        close_error: BaseException | None,
        persistence_outcome: LogPersistenceOutcome,
    ) -> None:
        super().__init__(
            "structured log append lifecycle failed; "
            f"persistence={persistence_outcome}"
        )
        self.primary_error = primary_error
        self.rollback_error = rollback_error
        self.close_error = close_error
        self.persistence_outcome = persistence_outcome


def _log_write_lock(path: Path) -> Lock:
    normalized = path.absolute()
    with _LOG_LOCKS_GUARD:
        return _LOG_WRITE_LOCKS.setdefault(normalized, Lock())


def write_log_event(
    component: LogComponent,
    event: str,
    message: str,
    *,
    project_root: Path | None = None,
    level: LogLevel = "info",
    conversation_id: str | None = None,
    reason_id: str | None = None,
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
) -> _LogEvent:
    """Append a structured log event and return it."""

    envelope = create_audit_envelope(
        component,
        event,
        message,
        level=level,
        conversation_id=conversation_id,
        reason_id=reason_id,
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
    conversation_id: str | None = None,
    reason_id: str | None = None,
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

    _require_log_component(component)
    require_audit_event_name(event)
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
            conversation_id=conversation_id if conversation_id is not None else context.conversation_id,
            reason_id=reason_id if reason_id is not None else context.reason_id,
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
) -> _LogEvent:
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
) -> _LogEvent:
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
) -> _LogEvent:
    if envelope.kind != required_kind:
        raise ValueError(
            f"log projection requires an {required_kind} envelope"
        )
    if envelope.producer not in LOG_COMPONENTS:
        raise ValueError("log envelope producer is not a log component")
    if required_kind == "audit":
        require_audit_event_name(envelope.name)
    else:
        require_runtime_event_name(envelope.name)
    payload = RuntimeLogEventPayload.from_mapping(envelope.payload)
    if required_kind == "audit" and payload.message is None:
        raise ValueError("audit envelope requires a message")
    message = (
        payload.message
        if payload.message is not None
        else envelope.name
    )
    event_record = _LogEvent(
        time=envelope.created_at,
        level=payload.level,
        component=envelope.producer,
        event=envelope.name,
        message=redact_sensitive_text(message),
        event_id=envelope.message_id,
        schema_version=envelope.schema_version,
        conversation_id=envelope.context.conversation_id,
        reason_id=envelope.context.reason_id,
        request_id=envelope.context.request_id,
        turn_id=envelope.context.turn_id,
        job_id=envelope.context.job_id,
        trace_id=envelope.context.trace_id,
        source=envelope.context.source,
        node=payload.node,
        duration_ms=payload.duration_ms,
        status=payload.status,
        error=(
            redact_sensitive_text(payload.error)
            if payload.error is not None
            else None
        ),
        metadata=sanitize_diagnostic_metadata(payload.metadata),
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
    projection: Callable[[_LogEvent], None] | None = None,
) -> Callable[[RuntimeEnvelope], None]:
    """Build a bounded synchronous event-to-audit projection."""

    def sink(envelope: RuntimeEnvelope) -> None:
        event = write_runtime_event(
            envelope,
            project_root=project_root,
            retention_policy=retention_policy,
        )
        if projection is not None:
            projection(event)

    return sink


def _append_log_event(
    event_record: _LogEvent,
    *,
    project_root: Path | None,
    retention_policy: LogRetentionPolicy,
) -> _LogEvent:
    paths = runtime_paths(project_root)
    ensure_runtime_dirs(paths)
    path = log_path(event_record.component, project_root=paths.authority_root)
    line = (
        json.dumps(event_record.to_record(), sort_keys=True, ensure_ascii=True) + "\n"
    )
    encoded_size = len(line.encode("utf-8"))
    lock_path = path.with_name(f"{path.name}.lock")
    with _log_write_lock(path), _locked_log_sidecar(
        lock_path,
        component=event_record.component,
    ):
        for existing_path in component_log_paths(path):
            if existing_path.exists():
                ensure_private_file(existing_path)
        try:
            _rotate_log_if_needed(
                path,
                incoming_bytes=encoded_size,
                policy=retention_policy,
            )
        except OSError as exc:
            _report_log_rotation_failure(event_record.component, exc)
        _append_encoded_log_line(
            path,
            line.encode("utf-8"),
            component=event_record.component,
        )
    for binding in _CURRENT_LOG_EVENT_PROJECTIONS.get():
        active = _ACTIVE_LOG_EVENT_PROJECTIONS.get()
        if binding.binding_id in active:
            continue
        token = _ACTIVE_LOG_EVENT_PROJECTIONS.set(
            active | {binding.binding_id}
        )
        try:
            binding.projection(event_record)
        except Exception as exc:
            _report_log_observer_failure(
                exc,
                project_root=paths.authority_root,
            )
            continue
        finally:
            _ACTIVE_LOG_EVENT_PROJECTIONS.reset(token)
    return event_record


@contextmanager
def _locked_log_sidecar(
    lock_path: Path,
    *,
    component: LogComponent,
) -> Generator[None, None, None]:
    ensure_private_file(lock_path)
    lock_file = lock_path.open("a", encoding="utf-8")
    locked = False
    try:
        flock(lock_file.fileno(), LOCK_EX)
        locked = True
        yield
    finally:
        _cleanup_log_sidecar(
            lock_file,
            locked=locked,
            component=component,
        )


def _cleanup_log_sidecar(
    lock_file: IO[str],
    *,
    locked: bool,
    component: LogComponent,
) -> None:
    if locked:
        try:
            flock(lock_file.fileno(), LOCK_UN)
        except OSError as exc:
            _report_log_lock_cleanup_failure(
                component,
                operation="unlock",
                exc=exc,
            )
    try:
        lock_file.close()
    except OSError as exc:
        _report_log_lock_cleanup_failure(
            component,
            operation="close",
            exc=exc,
        )


def _report_log_lock_cleanup_failure(
    component: LogComponent,
    *,
    operation: Literal["unlock", "close"],
    exc: OSError,
) -> None:
    emit_registered_terminal_warning(
        LOG_TERMINAL_WARNING_REGISTRY,
        "logs/lock_cleanup_failed",
        {
            "component": component,
            "operation": operation,
            "error_type": type(exc).__name__,
        },
        stacklevel=4,
    )


def _append_encoded_log_line(
    path: Path,
    encoded_line: bytes,
    *,
    component: LogComponent,
) -> None:
    log_file = _open_log_data_file(path)
    primary_error: BaseException | None = None
    rollback_error: BaseException | None = None
    persistence_outcome: LogPersistenceOutcome = "not_persisted"
    try:
        record_boundary = log_file.seek(0, 2)
        try:
            _write_log_bytes(log_file, encoded_line)
            _sync_log_file(log_file)
            persistence_outcome = "persisted"
        except BaseException as exc:
            primary_error = exc
            rollback_error = _rollback_failed_log_append(
                log_file,
                record_boundary,
                component=component,
            )
            persistence_outcome = (
                "uncertain"
                if rollback_error is not None
                else "not_persisted"
            )
    except BaseException as exc:
        if primary_error is None:
            primary_error = exc

    close_error: BaseException | None = None
    try:
        log_file.close()
    except BaseException as exc:
        close_error = exc

    if rollback_error is not None or close_error is not None:
        lifecycle_error = LogAppendLifecycleError(
            primary_error=primary_error,
            rollback_error=rollback_error,
            close_error=close_error,
            persistence_outcome=persistence_outcome,
        )
        cause = primary_error if primary_error is not None else close_error
        raise lifecycle_error from cause
    if primary_error is not None:
        raise primary_error.with_traceback(primary_error.__traceback__)


def _open_log_data_file(path: Path) -> BinaryIO:
    ensure_private_file(path)
    _sync_log_directory_for_active(path)
    return path.open("a+b", buffering=0)


def _write_log_bytes(log_file: BinaryIO, encoded_line: bytes) -> None:
    written = 0
    while written < len(encoded_line):
        count = log_file.write(encoded_line[written:])
        if count <= 0:
            raise OSError("log append made no progress")
        written += count


def _sync_log_file(log_file: BinaryIO) -> None:
    os.fsync(log_file.fileno())


def _sync_log_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _sync_log_directory_for_active(path: Path) -> None:
    normalized = path.absolute()
    stat_result = path.stat()
    identity = (stat_result.st_dev, stat_result.st_ino)
    with _LOG_DIRECTORY_SYNC_GUARD:
        if _SYNCED_LOG_IDENTITIES.get(normalized) == identity:
            _SYNCED_LOG_IDENTITIES.move_to_end(normalized)
            return
    _sync_log_directory(path.parent)
    with _LOG_DIRECTORY_SYNC_GUARD:
        _SYNCED_LOG_IDENTITIES[normalized] = identity
        _SYNCED_LOG_IDENTITIES.move_to_end(normalized)
        while len(_SYNCED_LOG_IDENTITIES) > _LOG_DIRECTORY_SYNC_CACHE_LIMIT:
            _SYNCED_LOG_IDENTITIES.popitem(last=False)


def _rollback_failed_log_append(
    log_file: BinaryIO,
    record_boundary: int,
    *,
    component: LogComponent,
) -> BaseException | None:
    try:
        log_file.truncate(record_boundary)
        _sync_log_file(log_file)
    except BaseException as exc:
        emit_registered_terminal_warning(
            LOG_TERMINAL_WARNING_REGISTRY,
            "logs/append_rollback_failed",
            {
                "component": component,
                "error_type": type(exc).__name__,
            },
            stacklevel=4,
        )
        return exc
    return None


def _report_log_rotation_failure(
    component: LogComponent,
    exc: OSError,
) -> None:
    emit_registered_terminal_warning(
        LOG_TERMINAL_WARNING_REGISTRY,
        "logs/rotation_failed",
        {
            "component": component,
            "error_type": type(exc).__name__,
        },
        stacklevel=3,
    )


def _report_log_observer_failure(
    exc: Exception,
    *,
    project_root: Path,
) -> None:
    token = _CURRENT_LOG_EVENT_PROJECTIONS.set(())
    try:
        try:
            definition = LOG_INFRASTRUCTURE_AUDIT_REGISTRY.resolve(
                "daemon",
                "log_observer_failed",
            )
            error = diagnostic_exception_message(exc)
            definition.validate(
                level=definition.level,
                status=definition.status,
                error=error,
                metadata={},
            )
            write_log_event(
                definition.component,
                definition.event,
                _LOG_OBSERVER_FAILURE_MESSAGE,
                project_root=project_root,
                level=definition.level,
                status=definition.status,
                error=error,
            )
        except Exception as log_exc:
            observer_error = diagnostic_exception_message(exc)
            log_error = diagnostic_exception_message(log_exc)
            emit_registered_terminal_warning(
                LOG_TERMINAL_WARNING_REGISTRY,
                "daemon/log_observer_failed",
                {
                    "observer_error": observer_error,
                    "log_error": log_error,
                },
                stacklevel=3,
            )
    finally:
        _CURRENT_LOG_EVENT_PROJECTIONS.reset(token)


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
def project_log_events(
    projection: _LogEventProjection,
) -> Generator[None, None, None]:
    """Attach one bounded best-effort projection in this execution context."""

    if not callable(projection):
        raise TypeError("log event projection must be callable")
    current = _CURRENT_LOG_EVENT_PROJECTIONS.get()
    binding = _LogProjectionBinding(uuid4(), projection)
    token: Token[tuple[_LogProjectionBinding, ...]] = (
        _CURRENT_LOG_EVENT_PROJECTIONS.set((*current, binding))
    )
    try:
        yield
    finally:
        _CURRENT_LOG_EVENT_PROJECTIONS.reset(token)


def log_path(component: LogComponent, *, project_root: Path | None = None) -> Path:
    """Return the local log path for a component."""

    paths = runtime_paths(project_root)
    if component == "daemon":
        return paths.daemon_log_path
    if component == "inbox":
        return paths.inbox_log_path
    if component == "delivery":
        return paths.delivery_log_path
    return paths.logs_dir / f"{component}.log"


def component_log_paths(active_path: Path) -> tuple[Path, ...]:
    """Return rotated component logs followed by the active log."""

    backups: list[tuple[int, Path]] = []
    for candidate in active_path.parent.glob(f"{active_path.name}.*"):
        suffix = candidate.name.removeprefix(f"{active_path.name}.")
        if suffix.isdigit():
            backups.append((int(suffix), candidate))
    backups.sort(key=lambda item: item[0], reverse=True)
    return (*(path for _, path in backups), active_path)


def _require_log_component(component: object) -> None:
    if component not in LOG_COMPONENTS:
        raise ValueError("log component is invalid")
