from __future__ import annotations

from pathlib import Path

import pytest

from nuself.agent import endpoint_audit
from nuself.agent.endpoint_audit import (
    AGENT_ENDPOINT_AUDIT_REGISTRY,
    report_agent_endpoint_failure,
)
from nuself.runtime.audit_definitions import (
    AuditDefinitionRegistrySealedError,
    AuditSchemaError,
    UnknownAuditDefinitionError,
)


def test_agent_endpoint_audit_registry_is_complete_and_sealed() -> None:
    identities = {
        (definition.component, definition.event)
        for definition in AGENT_ENDPOINT_AUDIT_REGISTRY.definitions
    }

    assert len(identities) == 10
    assert identities == {
        (component, event)
        for component in endpoint_audit.AGENT_ENDPOINT_COMPONENTS
        for event in (
            "llm_endpoint_failed_over",
            "llm_endpoint_unavailable",
        )
    }
    with pytest.raises(AuditDefinitionRegistrySealedError):
        AGENT_ENDPOINT_AUDIT_REGISTRY.register(
            AGENT_ENDPOINT_AUDIT_REGISTRY.definitions[0]
        )


def test_agent_endpoint_audit_rejects_unowned_component() -> None:
    with pytest.raises(UnknownAuditDefinitionError):
        AGENT_ENDPOINT_AUDIT_REGISTRY.resolve(
            "daemon",
            "llm_endpoint_failed_over",
        )


@pytest.mark.parametrize(
    "metadata",
    [
        {"endpoint_index": True, "model": "model"},
        {"endpoint_index": -1, "model": "model"},
        {"endpoint_index": 0, "model": " "},
        {
            "endpoint_index": 0,
            "model": "model",
            "base_url": "https://secret.invalid",
        },
    ],
)
def test_agent_endpoint_audit_rejects_unsafe_metadata(
    metadata: dict[str, object],
) -> None:
    definition = AGENT_ENDPOINT_AUDIT_REGISTRY.resolve(
        "memory",
        "llm_endpoint_failed_over",
    )

    with pytest.raises(AuditSchemaError):
        definition.validate(
            level="warning",
            status="failed_over",
            error="provider unavailable",
            metadata=metadata,
        )


@pytest.mark.parametrize(
    ("has_next", "event", "message", "status"),
    [
        (
            True,
            "llm_endpoint_failed_over",
            "LLM endpoint failed; trying next configured endpoint",
            "failed_over",
        ),
        (
            False,
            "llm_endpoint_unavailable",
            "LLM endpoint failed and no fallback endpoint remains",
            "exhausted",
        ),
    ],
)
def test_agent_endpoint_failure_uses_fixed_safe_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    has_next: bool,
    event: str,
    message: str,
    status: str,
) -> None:
    calls: list[tuple[Exception, dict[str, object]]] = []

    def report_failure(
        exc: Exception,
        **kwargs: object,
    ) -> None:
        calls.append((exc, kwargs))

    monkeypatch.setattr(
        endpoint_audit,
        "report_observed_failure",
        report_failure,
    )

    report_agent_endpoint_failure(
        RuntimeError(
            "HTTP 429 at https://secret.invalid/v1?api_key=secret"
        ),
        component="reflection",
        has_next=has_next,
        endpoint_index=3,
        model="safe-model",
        project_root=tmp_path,
    )

    assert len(calls) == 1
    diagnostic, kwargs = calls[0]
    assert "api_key=secret" not in str(diagnostic)
    assert "api_key=***" in str(diagnostic)
    assert kwargs == {
        "component": "reflection",
        "event": event,
        "message": message,
        "project_root": tmp_path,
        "level": "warning",
        "status": status,
        "metadata": {
            "endpoint_index": 3,
            "model": "safe-model",
        },
    }
