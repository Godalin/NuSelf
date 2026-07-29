"""Closed audit contracts for shared storage cleanup failures."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import cast

from nuself.runtime.audit_definitions import (
    AuditDefinitionRegistry,
    AuditEventDefinition,
    AuditSchemaError,
)
from nuself.runtime.cleanup import (
    CleanupFailure,
    cleanup_failure_records,
)
from nuself.runtime.diagnostics import diagnostic_exception_chain
from nuself.runtime.observability import report_observed_failure


def _require_exact(
    metadata: Mapping[str, object],
    expected: frozenset[str],
) -> None:
    actual = frozenset(metadata)
    if actual != expected:
        raise AuditSchemaError(
            "storage operations audit metadata fields differ "
            f"(missing={sorted(expected - actual)!r}, "
            f"extra={sorted(actual - expected)!r})"
        )


def _backend_close(metadata: Mapping[str, object]) -> None:
    _require_exact(metadata, frozenset({"backend_type"}))
    backend_type = metadata["backend_type"]
    if not isinstance(backend_type, str) or not backend_type.strip():
        raise AuditSchemaError(
            "storage operations backend_type must be non-blank"
        )


def _cleanup_failure_records(metadata: Mapping[str, object]) -> None:
    _require_exact(metadata, frozenset({"failures", "primary_failed"}))
    if type(metadata["primary_failed"]) is not bool:
        raise AuditSchemaError(
            "storage operations primary_failed must be a boolean"
        )
    failures = metadata["failures"]
    if not isinstance(failures, list) or not failures:
        raise AuditSchemaError(
            "storage operations failures must be a non-empty list"
        )
    for raw_failure in cast(list[object], failures):
        if not isinstance(raw_failure, Mapping):
            raise AuditSchemaError(
                "storage operations failure must be a mapping"
            )
        failure = cast(Mapping[str, object], raw_failure)
        _require_exact(failure, frozenset({"step", "error"}))
        for field in ("step", "error"):
            value = failure[field]
            if not isinstance(value, str) or not value.strip():
                raise AuditSchemaError(
                    f"storage operations failure {field} must be non-blank"
                )


def _build_registry() -> AuditDefinitionRegistry:
    registry = AuditDefinitionRegistry()
    registry.register(
        AuditEventDefinition(
            component="storage",
            event="backend_close_failed",
            level="warning",
            status="degraded",
            error_policy="required",
            metadata_validator=_backend_close,
        )
    )
    registry.register(
        AuditEventDefinition(
            component="storage",
            event="cli_cleanup_failed",
            level="error",
            status="error",
            error_policy="required",
            metadata_validator=_cleanup_failure_records,
        )
    )
    return registry.seal()


STORAGE_OPERATIONS_AUDIT_REGISTRY = _build_registry()


def report_backend_close_failure(
    exc: Exception,
    *,
    project_root: Path,
    backend_type: str,
) -> None:
    """Report one default backend close failure."""

    metadata: dict[str, object] = {"backend_type": backend_type}
    definition = STORAGE_OPERATIONS_AUDIT_REGISTRY.resolve(
        "storage",
        "backend_close_failed",
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
        message="Default storage backend could not be closed",
        project_root=project_root,
        metadata=metadata,
        level=definition.level,
        status=definition.status or "degraded",
    )


def report_cli_cleanup_failure(
    exc: Exception,
    *,
    project_root: Path | None,
    failures: tuple[CleanupFailure, ...],
    primary_failed: bool,
) -> None:
    """Report every retained outer CLI cleanup failure."""

    metadata: dict[str, object] = {
        "failures": cleanup_failure_records(failures),
        "primary_failed": primary_failed,
    }
    definition = STORAGE_OPERATIONS_AUDIT_REGISTRY.resolve(
        "storage",
        "cli_cleanup_failed",
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
        message="CLI storage cleanup failed",
        project_root=project_root,
        metadata=metadata,
        level=definition.level,
        status=definition.status or "error",
    )
