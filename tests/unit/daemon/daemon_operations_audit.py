from pathlib import Path

import pytest

from nuself.daemon.operations_audit import (
    DAEMON_OPERATIONS_AUDIT,
    report_shutdown_cleanup_failure,
)
from nuself.logs import read_log_events
from nuself.runtime.audit.definition import (
    AuditDefinitionRegistrySealedError,
    AuditEventDefinition,
)
from nuself.runtime.cleanup import CleanupFailure


def test_daemon_operations_registry_is_complete_and_sealed() -> None:
    assert len(DAEMON_OPERATIONS_AUDIT.registry.definitions) == 1
    with pytest.raises(AuditDefinitionRegistrySealedError):
        DAEMON_OPERATIONS_AUDIT.registry.register(
            AuditEventDefinition(
                component="daemon",
                event="operation_extra",
                level="warning",
                status="error",
            )
        )


def test_cleanup_projection_preserves_ordered_error_chains(
    tmp_path: Path,
) -> None:
    try:
        try:
            raise OSError("socket close failed")
        except OSError as exc:
            raise RuntimeError("server close failed") from exc
    except RuntimeError as chained:
        failures = (
            CleanupFailure("server.close", chained),
            CleanupFailure("lock.release", ValueError("unlock failed")),
        )

    report_shutdown_cleanup_failure(
        RuntimeError("daemon lifecycle cleanup failed in 2 step(s)"),
        project_root=tmp_path,
        failures=failures,
        primary_failed=True,
    )

    [event] = read_log_events(
        project_root=tmp_path,
        component="daemon",
    )
    assert event.status == "error"
    assert event.to_record()["metadata"] == {
        "failures": [
            {
                "step": "server.close",
                "error": "server close failed <- socket close failed",
            },
            {
                "step": "lock.release",
                "error": "unlock failed",
            },
        ],
        "primary_failed": True,
    }
