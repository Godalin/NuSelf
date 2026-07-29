from pathlib import Path

import pytest

from nuself.daemon.operations_audit import (
    DAEMON_OPERATIONS_AUDIT_REGISTRY,
    report_shutdown_cleanup_failure,
    report_worker_join_timeout,
)
from nuself.logs import read_log_events
from nuself.runtime.audit_definitions import (
    AuditDefinitionRegistrySealedError,
    AuditEventDefinition,
    AuditSchemaError,
)
from nuself.runtime.cleanup import CleanupFailure


def test_daemon_operations_registry_is_complete_and_sealed() -> None:
    assert len(DAEMON_OPERATIONS_AUDIT_REGISTRY.definitions) == 2
    with pytest.raises(AuditDefinitionRegistrySealedError):
        DAEMON_OPERATIONS_AUDIT_REGISTRY.register(
            AuditEventDefinition(
                component="daemon",
                event="operation_extra",
                level="warning",
                status="error",
            )
        )


@pytest.mark.parametrize("timeout", [-1.0, float("inf"), float("nan")])
def test_worker_timeout_contract_rejects_invalid_duration(
    timeout: float,
) -> None:
    with pytest.raises(AuditSchemaError, match="finite"):
        report_worker_join_timeout(
            RuntimeError("still alive"),
            project_root=Path("."),
            worker="memory",
            timeout_seconds=timeout,
        )


def test_worker_timeout_projection_is_fixed(tmp_path: Path) -> None:
    report_worker_join_timeout(
        RuntimeError("memory did not stop within 0s"),
        project_root=tmp_path,
        worker="memory",
        timeout_seconds=0,
    )

    [event] = read_log_events(
        project_root=tmp_path,
        component="daemon",
    )
    assert event.message == "Daemon worker join timed out"
    assert event.status == "timed_out"
    assert event.metadata == {
        "worker": "memory",
        "timeout_seconds": 0,
    }


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
