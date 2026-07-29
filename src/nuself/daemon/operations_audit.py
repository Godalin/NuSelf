"""Closed audit contracts for daemon process and supervisor failures."""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from pathlib import Path
from typing import cast

from nuself.runtime.audit_definitions import (
    AuditDefinitionRegistry,
    AuditEventDefinition,
    AuditSchemaError,
)
from nuself.runtime.cleanup import CleanupFailure
from nuself.runtime.diagnostics import diagnostic_exception_chain
from nuself.runtime.observability import report_observed_failure


def _require_exact(
    metadata: Mapping[str, object],
    expected: frozenset[str],
) -> None:
    actual = frozenset(metadata)
    if actual != expected:
        raise AuditSchemaError(
            "daemon operations audit metadata fields differ "
            f"(missing={sorted(expected - actual)!r}, "
            f"extra={sorted(actual - expected)!r})"
        )


def _thread_timeout(metadata: Mapping[str, object]) -> None:
    _require_exact(metadata, frozenset({"worker", "timeout_seconds"}))
    worker = metadata["worker"]
    if not isinstance(worker, str) or not worker.strip():
        raise AuditSchemaError(
            "daemon operations worker must be a non-blank string"
        )
    timeout = metadata["timeout_seconds"]
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, int | float)
        or not isfinite(timeout)
        or timeout < 0
    ):
        raise AuditSchemaError(
            "daemon operations timeout_seconds must be finite and non-negative"
        )


def _shutdown_cleanup(metadata: Mapping[str, object]) -> None:
    _require_exact(metadata, frozenset({"failures", "primary_failed"}))
    if type(metadata["primary_failed"]) is not bool:
        raise AuditSchemaError(
            "daemon operations primary_failed must be a boolean"
        )
    failures = metadata["failures"]
    if not isinstance(failures, list) or not failures:
        raise AuditSchemaError(
            "daemon operations failures must be a non-empty list"
        )
    for raw_failure in cast(list[object], failures):
        if not isinstance(raw_failure, Mapping):
            raise AuditSchemaError(
                "daemon operations failure must be a mapping"
            )
        failure = cast(Mapping[str, object], raw_failure)
        _require_exact(failure, frozenset({"step", "error"}))
        for field in ("step", "error"):
            value = failure[field]
            if not isinstance(value, str) or not value.strip():
                raise AuditSchemaError(
                    f"daemon operations failure {field} must be non-blank"
                )


def _build_registry() -> AuditDefinitionRegistry:
    registry = AuditDefinitionRegistry()
    registry.register(
        AuditEventDefinition(
            component="daemon",
            event="thread_timeout",
            level="warning",
            status="timed_out",
            error_policy="required",
            metadata_validator=_thread_timeout,
        )
    )
    registry.register(
        AuditEventDefinition(
            component="daemon",
            event="shutdown_cleanup_failed",
            level="error",
            status="error",
            error_policy="required",
            metadata_validator=_shutdown_cleanup,
        )
    )
    return registry.seal()


DAEMON_OPERATIONS_AUDIT_REGISTRY = _build_registry()


def report_worker_join_timeout(
    exc: Exception,
    *,
    project_root: Path,
    worker: str,
    timeout_seconds: float,
) -> None:
    """Report one owned worker that remained alive after join."""

    metadata: dict[str, object] = {
        "worker": worker,
        "timeout_seconds": timeout_seconds,
    }
    definition = DAEMON_OPERATIONS_AUDIT_REGISTRY.resolve(
        "daemon",
        "thread_timeout",
    )
    error = diagnostic_exception_chain(exc)
    definition.validate(
        level=definition.level,
        status=definition.status,
        error=error,
        metadata=metadata,
    )
    report_observed_failure(
        exc,
        component=definition.component,
        event=definition.event,
        message="Daemon worker join timed out",
        project_root=project_root,
        metadata=metadata,
        level=definition.level,
        status=definition.status or "timed_out",
    )


def report_shutdown_cleanup_failure(
    exc: Exception,
    *,
    project_root: Path,
    failures: tuple[CleanupFailure, ...],
    primary_failed: bool,
) -> None:
    """Report every retained daemon cleanup failure in execution order."""

    metadata: dict[str, object] = {
        "failures": [
            {
                "step": failure.step,
                "error": diagnostic_exception_chain(failure.error),
            }
            for failure in failures
        ],
        "primary_failed": primary_failed,
    }
    definition = DAEMON_OPERATIONS_AUDIT_REGISTRY.resolve(
        "daemon",
        "shutdown_cleanup_failed",
    )
    error = diagnostic_exception_chain(exc)
    definition.validate(
        level=definition.level,
        status=definition.status,
        error=error,
        metadata=metadata,
    )
    report_observed_failure(
        exc,
        component=definition.component,
        event=definition.event,
        message="Daemon lifecycle cleanup failed",
        project_root=project_root,
        metadata=metadata,
        level=definition.level,
        status=definition.status or "error",
    )
