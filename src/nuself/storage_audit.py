"""Closed audit contracts for shared storage cleanup failures."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import cast

from nuself.runtime.audit_definitions import (
    AuditDefinitionRegistry,
    AuditEventDefinition,
    AuditSchemaError,
    require_exact_metadata,
)
from nuself.runtime.cleanup import (
    CleanupFailure,
    cleanup_failure_records,
)
from nuself.runtime.observability import report_defined_failure


def _backend_close(metadata: Mapping[str, object]) -> None:
    require_exact_metadata(
        metadata,
        frozenset({"backend_type"}),
        context="storage operations audit metadata",
    )
    backend_type = metadata["backend_type"]
    if not isinstance(backend_type, str) or not backend_type.strip():
        raise AuditSchemaError(
            "storage operations backend_type must be non-blank"
        )


def _cleanup_failure_records(metadata: Mapping[str, object]) -> None:
    require_exact_metadata(
        metadata,
        frozenset({"failures", "primary_failed"}),
        context="storage operations audit metadata",
    )
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
        require_exact_metadata(
            failure,
            frozenset({"step", "error"}),
            context="storage operations failure",
        )
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
    """Report one application-owned backend close failure."""

    metadata: dict[str, object] = {"backend_type": backend_type}
    definition = STORAGE_OPERATIONS_AUDIT_REGISTRY.resolve(
        "storage",
        "backend_close_failed",
    )
    report_defined_failure(
        exc,
        definition=definition,
        message="Application storage backend could not be closed",
        project_root=project_root,
        metadata=metadata,
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
    report_defined_failure(
        exc,
        definition=definition,
        message="CLI storage cleanup failed",
        project_root=project_root,
        metadata=metadata,
    )
