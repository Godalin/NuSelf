from pathlib import Path

import pytest

from nuself.logs import read_log_events
from nuself.runtime.audit_definitions import (
    AuditDefinitionRegistrySealedError,
    AuditEventDefinition,
    AuditSchemaError,
)
from nuself.runtime.cleanup import (
    CleanupFailure,
    cleanup_failure_records,
)
from nuself.storage_audit import (
    STORAGE_OPERATIONS_AUDIT_REGISTRY,
    report_backend_close_failure,
    report_cli_cleanup_failure,
)


def test_storage_operations_registry_is_complete_and_sealed() -> None:
    assert len(STORAGE_OPERATIONS_AUDIT_REGISTRY.definitions) == 2
    with pytest.raises(AuditDefinitionRegistrySealedError):
        STORAGE_OPERATIONS_AUDIT_REGISTRY.register(
            AuditEventDefinition(
                component="storage",
                event="storage_extra",
                level="warning",
                status="degraded",
            )
        )


def test_cleanup_failure_records_preserve_safe_ordered_chains() -> None:
    try:
        try:
            raise OSError("close failed")
        except OSError as exc:
            raise RuntimeError("reset failed") from exc
    except RuntimeError as chained:
        failures = (
            CleanupFailure("backend.reset", chained),
            CleanupFailure("cache.close", ValueError("cache failed")),
        )

    assert cleanup_failure_records(failures) == [
        {
            "step": "backend.reset",
            "error": "reset failed <- close failed",
        },
        {
            "step": "cache.close",
            "error": "cache failed",
        },
    ]


def test_backend_close_projection_is_fixed(tmp_path: Path) -> None:
    report_backend_close_failure(
        OSError("close failed"),
        project_root=tmp_path,
        backend_type="SqliteStorageBackend",
    )

    [event] = read_log_events(
        project_root=tmp_path,
        component="storage",
    )
    assert event.message == "Default storage backend could not be closed"
    assert event.level == "warning"
    assert event.status == "degraded"
    assert event.metadata == {"backend_type": "SqliteStorageBackend"}


def test_cli_cleanup_projection_preserves_nested_failure(
    tmp_path: Path,
) -> None:
    failures = (
        CleanupFailure(
            "storage.default_backend.reset",
            RuntimeError("failed to close 2 default storage backends"),
        ),
    )
    report_cli_cleanup_failure(
        RuntimeError("CLI cleanup failed in 1 step"),
        project_root=tmp_path,
        failures=failures,
        primary_failed=True,
    )

    [event] = read_log_events(
        project_root=tmp_path,
        component="storage",
    )
    assert event.status == "error"
    assert event.to_record()["metadata"] == {
        "failures": [
            {
                "step": "storage.default_backend.reset",
                "error": "failed to close 2 default storage backends",
            }
        ],
        "primary_failed": True,
    }


def test_cli_cleanup_contract_rejects_empty_failures() -> None:
    with pytest.raises(AuditSchemaError, match="non-empty"):
        report_cli_cleanup_failure(
            RuntimeError("cleanup failed"),
            project_root=Path("."),
            failures=(),
            primary_failed=False,
        )
