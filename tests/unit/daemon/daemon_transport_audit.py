from pathlib import Path

import pytest

from nuself.daemon.transport_audit import (
    DAEMON_TRANSPORT_AUDIT,
    report_daemon_transport_failure,
)
from nuself.logs import read_log_events
from nuself.runtime.audit_definitions import (
    AuditDefinitionRegistrySealedError,
    AuditEventDefinition,
    AuditSchemaError,
)


def test_daemon_transport_registry_is_complete_and_sealed() -> None:
    assert len(DAEMON_TRANSPORT_AUDIT.registry.definitions) == 4
    with pytest.raises(AuditDefinitionRegistrySealedError):
        DAEMON_TRANSPORT_AUDIT.registry.register(
            AuditEventDefinition(
                component="daemon",
                event="transport_extra",
                level="warning",
                status="error",
            )
        )


def test_response_delivery_contract_is_exact() -> None:
    definition = DAEMON_TRANSPORT_AUDIT.registry.resolve(
        "daemon",
        "response_delivery_failed",
    )
    with pytest.raises(AuditSchemaError, match="missing"):
        definition.validate(
            level="warning",
            status="error",
            error="client disconnected",
            metadata={"response_status": "error"},
        )
    with pytest.raises(AuditSchemaError, match="boolean"):
        definition.validate(
            level="warning",
            status="error",
            error="client disconnected",
            metadata={
                "response_status": "error",
                "fallback": 1,
            },
        )


def test_unknown_request_identity_is_not_persisted(
    tmp_path: Path,
) -> None:
    report_daemon_transport_failure(
        TimeoutError("request read timed out"),
        event="request_transport_failed",
        project_root=tmp_path,
        request_id=None,
    )

    [event] = read_log_events(
        project_root=tmp_path,
        component="daemon",
    )
    assert event.message == "Daemon request transport failed"
    assert event.request_id is None
    assert event.error == "request read timed out"
    assert event.metadata == {}


def test_response_encode_projection_is_fixed(
    tmp_path: Path,
) -> None:
    report_daemon_transport_failure(
        ValueError("invalid response"),
        event="response_encode_failed",
        project_root=tmp_path,
        request_id="request-1",
        metadata={"response_status": "ok"},
    )

    [event] = read_log_events(
        project_root=tmp_path,
        component="daemon",
    )
    assert event.message == "Daemon response could not be encoded"
    assert event.level == "warning"
    assert event.status == "error"
    assert event.request_id == "request-1"
    assert event.metadata == {"response_status": "ok"}
