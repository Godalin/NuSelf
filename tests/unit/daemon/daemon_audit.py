from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from nuself.daemon import audit
from nuself.logs import read_log_events
from nuself.runtime.audit_definitions import (
    AuditDefinitionRegistrySealedError,
    AuditEventDefinition,
    AuditSchemaError,
    UnknownAuditDefinitionError,
)


def _start_completed_metadata() -> dict[str, object]:
    return {
        "outcome": "started",
        "changed": True,
        "from_phase": "stopped",
        "to_phase": "ready",
        "pid": 42,
        "socket": "/private/runtime/nuself.sock",
    }


def test_lifecycle_audit_registry_is_closed_and_immutable() -> None:
    assert {
        definition.event
        for definition in audit.DAEMON_LIFECYCLE_AUDIT.registry.definitions
    } == {
        "instance_lock_contended",
        "started",
        "stopped",
        "runtime_metadata_recovered",
        "start_requested",
        "start_completed",
        "start_failed",
        "stop_requested",
        "stop_completed",
        "stop_failed",
        "restart_requested",
        "restart_completed",
        "restart_failed",
    }

    with pytest.raises(AuditDefinitionRegistrySealedError):
        audit.DAEMON_LIFECYCLE_AUDIT.registry.register(
            AuditEventDefinition(
                component="daemon",
                event="started",
                level="info",
                status=None,
            ),
        )


@pytest.mark.parametrize(
    "event",
    ("", "StartRequested", "start-requested", "start.requested", "1started"),
)
def test_lifecycle_audit_definition_rejects_invalid_event_slug(
    event: str,
) -> None:
    with pytest.raises(ValueError, match="audit event name"):
        AuditEventDefinition(
            component="daemon",
            event=cast(audit.DaemonLifecycleAuditEvent, event),
            level="info",
            status=None,
        )


def test_lifecycle_audit_rejects_unknown_event_before_sink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sink_calls = 0

    def unexpected_sink(*args: object, **kwargs: object) -> None:
        nonlocal sink_calls
        sink_calls += 1

    monkeypatch.setattr(
        "nuself.runtime.auditing.write_observed_log_event",
        unexpected_sink,
    )

    with pytest.raises(
        UnknownAuditDefinitionError,
        match="direct audit is not registered",
    ):
        audit.write_lifecycle_audit(
            cast(audit.DaemonLifecycleAuditEvent, "start_compeleted"),
            project_root=tmp_path,
        )

    assert sink_calls == 0


@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        ({}, "metadata fields differ"),
        (
            {
                **_start_completed_metadata(),
                "unexpected": True,
            },
            "extra=\\['unexpected'\\]",
        ),
        (
            {
                **_start_completed_metadata(),
                "changed": 1,
            },
            "changed must be a boolean",
        ),
        (
            {
                **_start_completed_metadata(),
                "outcome": "already_ready",
            },
            "changed does not match",
        ),
        (
            {
                **_start_completed_metadata(),
                "pid": True,
            },
            "pid must be an integer or null",
        ),
    ],
)
def test_lifecycle_audit_rejects_invalid_transition_metadata_before_sink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    metadata: dict[str, object],
    message: str,
) -> None:
    sink_calls = 0

    def unexpected_sink(*args: object, **kwargs: object) -> None:
        nonlocal sink_calls
        sink_calls += 1

    monkeypatch.setattr(
        "nuself.runtime.auditing.write_observed_log_event",
        unexpected_sink,
    )

    with pytest.raises(
        AuditSchemaError,
        match=message,
    ):
        audit.write_lifecycle_audit(
            "start_completed",
            project_root=tmp_path,
            metadata=metadata,
        )

    assert sink_calls == 0


def test_lifecycle_audit_enforces_error_policy_before_sink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sink_calls = 0

    def unexpected_sink(*args: object, **kwargs: object) -> None:
        nonlocal sink_calls
        sink_calls += 1

    monkeypatch.setattr(
        "nuself.runtime.auditing.write_observed_log_event",
        unexpected_sink,
    )

    with pytest.raises(
        AuditSchemaError,
        match="requires an error",
    ):
        audit.write_lifecycle_audit(
            "start_failed",
            project_root=tmp_path,
            metadata={
                "reason": "spawn_failed",
                "phase": "stopped",
                "pid": None,
                "socket": "/private/runtime/nuself.sock",
                "exit_code": None,
            },
        )
    with pytest.raises(
        AuditSchemaError,
        match="forbids an error",
    ):
        audit.write_lifecycle_audit(
            "started",
            project_root=tmp_path,
            error="not allowed",
        )

    assert sink_calls == 0


@pytest.mark.parametrize(
    "metadata",
    [
        {
            "stage": "start",
            "reason": "timeout",
            "phase": "stopped",
            "pid": None,
            "socket": "/private/runtime/nuself.sock",
            "exit_code": None,
            "owner_active": True,
        },
        {
            "stage": "finish",
            "reason": "timeout",
            "phase": "stopped",
            "pid": None,
            "socket": "/private/runtime/nuself.sock",
            "exit_code": None,
        },
    ],
)
def test_restart_failure_rejects_mixed_or_unknown_stage_schema(
    tmp_path: Path,
    metadata: dict[str, object],
) -> None:
    with pytest.raises(AuditSchemaError):
        audit.write_lifecycle_audit(
            "restart_failed",
            project_root=tmp_path,
            error="failure",
            metadata=metadata,
        )


def test_lifecycle_audit_definition_projects_registered_defaults(
    tmp_path: Path,
) -> None:
    metadata = _start_completed_metadata()

    audit.write_lifecycle_audit(
        "start_completed",
        project_root=tmp_path,
        metadata=metadata,
    )

    events = read_log_events(project_root=tmp_path, component="daemon")
    assert len(events) == 1
    event = events[0]
    assert event.event == "start_completed"
    assert event.message == "daemon start completed"
    assert event.level == "info"
    assert event.status == "ready"
    assert event.error is None
    assert event.metadata == metadata
