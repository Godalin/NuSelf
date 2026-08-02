"""Closed audit contracts for daemon process and supervisor failures."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import cast

from nuself.runtime.audit.definition import (
    AuditEventDefinition,
    AuditSchemaError,
    require_exact_metadata,
)
from nuself.runtime.audit.catalog import AuditCatalog
from nuself.runtime.cleanup import (
    CleanupFailure,
    cleanup_failure_records,
)


def _shutdown_cleanup(metadata: Mapping[str, object]) -> None:
    require_exact_metadata(
        metadata,
        frozenset({"failures", "primary_failed"}),
        context="daemon operations audit metadata",
    )
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
        require_exact_metadata(
            failure,
            frozenset({"step", "error"}),
            context="daemon operations failure",
        )
        for field in ("step", "error"):
            value = failure[field]
            if not isinstance(value, str) or not value.strip():
                raise AuditSchemaError(
                    f"daemon operations failure {field} must be non-blank"
                )


def _definitions() -> tuple[AuditEventDefinition, ...]:
    return (
        AuditEventDefinition(
            component="daemon",
            event="shutdown_cleanup_failed",
            level="error",
            status="error",
            error_policy="required",
            metadata_validator=_shutdown_cleanup,
        ),
    )


DAEMON_OPERATIONS_AUDIT = AuditCatalog[str](
    _definitions(),
    {"shutdown_cleanup_failed": "Daemon lifecycle cleanup failed"},
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
        "failures": cleanup_failure_records(failures),
        "primary_failed": primary_failed,
    }
    DAEMON_OPERATIONS_AUDIT.failure(
        exc,
        event="shutdown_cleanup_failed",
        project_root=project_root,
        metadata=metadata,
    )
