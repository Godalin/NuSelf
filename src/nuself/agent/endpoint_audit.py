"""Closed audit contracts for shared agent endpoint availability."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from nuself.llm import redacted_llm_diagnostic
from nuself.runtime.audit_definitions import (
    AuditDefinitionRegistry,
    AuditEventDefinition,
    AuditSchemaError,
    require_exact_metadata,
)
from nuself.runtime.diagnostics import diagnostic_exception_chain
from nuself.runtime.observability import report_observed_failure

AgentEndpointComponent = Literal[
    "chat",
    "memory",
    "persona",
    "reasoning",
    "reflection",
]
AgentEndpointAuditEvent = Literal[
    "llm_endpoint_failed_over",
    "llm_endpoint_unavailable",
]

AGENT_ENDPOINT_COMPONENTS: tuple[AgentEndpointComponent, ...] = (
    "chat",
    "memory",
    "persona",
    "reasoning",
    "reflection",
)
_MESSAGES: dict[AgentEndpointAuditEvent, str] = {
    "llm_endpoint_failed_over": (
        "LLM endpoint failed; trying next configured endpoint"
    ),
    "llm_endpoint_unavailable": (
        "LLM endpoint failed and no fallback endpoint remains"
    ),
}


def _validate_endpoint_metadata(metadata: Mapping[str, object]) -> None:
    expected = frozenset({"endpoint_index", "model"})
    require_exact_metadata(
        metadata,
        expected,
        context="agent endpoint audit metadata",
    )
    endpoint_index = metadata["endpoint_index"]
    if type(endpoint_index) is not int or endpoint_index < 0:
        raise AuditSchemaError(
            "agent endpoint audit endpoint_index must be a "
            "non-negative integer"
        )
    model = metadata["model"]
    if not isinstance(model, str) or not model.strip():
        raise AuditSchemaError(
            "agent endpoint audit model must be a non-blank string"
        )


def _build_registry() -> AuditDefinitionRegistry:
    registry = AuditDefinitionRegistry()
    for component in AGENT_ENDPOINT_COMPONENTS:
        registry.register(
            AuditEventDefinition(
                component=component,
                event="llm_endpoint_failed_over",
                level="warning",
                status="failed_over",
                error_policy="required",
                metadata_validator=_validate_endpoint_metadata,
            )
        )
        registry.register(
            AuditEventDefinition(
                component=component,
                event="llm_endpoint_unavailable",
                level="warning",
                status="exhausted",
                error_policy="required",
                metadata_validator=_validate_endpoint_metadata,
            )
        )
    return registry.seal()


AGENT_ENDPOINT_AUDIT_REGISTRY = _build_registry()


def report_agent_endpoint_failure(
    exc: Exception,
    *,
    component: AgentEndpointComponent,
    has_next: bool,
    endpoint_index: int,
    model: str,
    project_root: Path | None,
) -> None:
    """Report one already-decided endpoint failover observation."""

    event: AgentEndpointAuditEvent = (
        "llm_endpoint_failed_over"
        if has_next
        else "llm_endpoint_unavailable"
    )
    definition = AGENT_ENDPOINT_AUDIT_REGISTRY.resolve(component, event)
    metadata: dict[str, object] = {
        "endpoint_index": endpoint_index,
        "model": model,
    }
    diagnostic = redacted_llm_diagnostic(exc)
    definition.validate(
        level=definition.level,
        status=definition.status,
        error=diagnostic_exception_chain(diagnostic),
        metadata=metadata,
    )
    report_observed_failure(
        diagnostic,
        component=definition.component,
        event=definition.event,
        message=_MESSAGES[event],
        project_root=project_root,
        level=definition.level,
        status=definition.status or "exhausted",
        metadata=metadata,
    )
