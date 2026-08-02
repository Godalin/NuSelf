from pathlib import Path

import pytest

from nuself.daemon.request_audit import (
    DAEMON_REQUEST_AUDIT,
    report_daemon_request_failure,
    write_daemon_request_audit,
)
from nuself.logs import read_log_events
from nuself.runtime.audit.definition import (
    AuditDefinitionRegistrySealedError,
    AuditEventDefinition,
    AuditSchemaError,
)


def test_daemon_request_audit_registry_is_complete_and_sealed() -> None:
    assert len(DAEMON_REQUEST_AUDIT.registry.definitions) == 4
    with pytest.raises(AuditDefinitionRegistrySealedError):
        DAEMON_REQUEST_AUDIT.registry.register(
            AuditEventDefinition(
                component="daemon",
                event="request_extra",
                level="info",
                status=None,
            )
        )


def test_chat_completion_contract_is_exact() -> None:
    with pytest.raises(AuditSchemaError, match="missing"):
        write_daemon_request_audit(
            "chat_turn_completed",
            project_root=Path("."),
            request_id="request-1",
            duration_ms=1,
            metadata={},
        )
    with pytest.raises(AuditSchemaError, match="non-negative"):
        write_daemon_request_audit(
            "chat_turn_completed",
            project_root=Path("."),
            request_id="request-1",
            duration_ms=1,
            metadata={
                "evidence_references": -1,
            },
        )


def test_request_failure_projection_owns_message_and_correlation(
    tmp_path: Path,
) -> None:
    report_daemon_request_failure(
        ValueError("unexpected payload field"),
        event="request_rejected",
        project_root=tmp_path,
        request_id="request-1",
        metadata={"request_type": "chat"},
    )

    [event] = read_log_events(
        project_root=tmp_path,
        component="daemon",
    )
    assert event.event == "request_rejected"
    assert event.message == "Daemon request payload rejected"
    assert event.level == "warning"
    assert event.status == "error"
    assert event.error == "unexpected payload field"
    assert event.request_id == "request-1"
    assert event.metadata == {"request_type": "chat"}


def test_shutdown_projection_has_explicit_accepted_status(
    tmp_path: Path,
) -> None:
    write_daemon_request_audit(
        "shutdown_requested",
        project_root=tmp_path,
        request_id="request-2",
    )

    [event] = read_log_events(
        project_root=tmp_path,
        component="daemon",
    )
    assert event.message == "Daemon shutdown requested"
    assert event.status == "accepted"
    assert event.request_id == "request-2"
    assert event.metadata == {}
