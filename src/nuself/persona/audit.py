"""Closed audit schemas owned by the Persona subsystem."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from nuself.runtime.audit.definition import (
    AuditEventDefinition,
    AuditSchemaError,
    require_exact_metadata as _exact,
)
from nuself.runtime.audit.catalog import AuditCatalog

type PersonaAuditEvent = Literal[
    "persona_summary",
    "host_discussion_decision",
    "persona_discussion_step",
    "persona_discussion",
    "persona_discussion_failure",
    "persona_discussion_degraded",
    "persona_completion_failed",
    "persona_activation_failed",
    "persona_definition_load_failed",
    "trace_recording_failed",
    "interactive_command_failed",
]

def _string(metadata: Mapping[str, object], field: str) -> str:
    value = metadata[field]
    if not isinstance(value, str) or not value:
        raise AuditSchemaError(f"audit metadata {field!r} must be non-empty")
    return value


def _boolean(metadata: Mapping[str, object], field: str) -> None:
    if type(metadata[field]) is not bool:
        raise AuditSchemaError(f"audit metadata {field!r} must be a boolean")


def _integer(
    metadata: Mapping[str, object],
    field: str,
    *,
    minimum: int = 0,
) -> None:
    value = metadata[field]
    if type(value) is not int or value < minimum:
        raise AuditSchemaError(
            f"audit metadata {field!r} must be an integer >= {minimum}"
        )


def _summary(metadata: Mapping[str, object]) -> None:
    _exact(metadata, frozenset({"persona_count", "has_synthesis"}))
    _integer(metadata, "persona_count")
    _boolean(metadata, "has_synthesis")


def _host_decision(metadata: Mapping[str, object]) -> None:
    _exact(metadata, frozenset({"should_escalate"}))
    _boolean(metadata, "should_escalate")


def _discussion_step(metadata: Mapping[str, object]) -> None:
    _exact(metadata, frozenset({"step_number"}))
    _integer(metadata, "step_number", minimum=1)


def _discussion(metadata: Mapping[str, object]) -> None:
    _exact(
        metadata,
        frozenset(
            {
                "candidate_id",
                "approved",
                "winner_count",
                "emergent_count",
                "blocking_veto_count",
                "score_count",
                "discussion_steps",
            }
        ),
    )
    _string(metadata, "candidate_id")
    _boolean(metadata, "approved")
    for field in (
        "winner_count",
        "emergent_count",
        "blocking_veto_count",
        "score_count",
        "discussion_steps",
    ):
        _integer(metadata, field)


def _discussion_degraded(metadata: Mapping[str, object]) -> None:
    _exact(metadata, frozenset({"stage"}))
    if _string(metadata, "stage") not in {
        "scoring",
        "selection",
        "moderator",
    }:
        raise AuditSchemaError("audit metadata 'stage' is invalid")


def _completion_failed(metadata: Mapping[str, object]) -> None:
    _exact(metadata, frozenset({"stage"}))
    if _string(metadata, "stage") not in {"contribution", "synthesis"}:
        raise AuditSchemaError("audit metadata 'stage' is invalid")


def _trace_failed(metadata: Mapping[str, object]) -> None:
    _exact(metadata, frozenset({"persona_prompt_id", "action"}))
    _string(metadata, "persona_prompt_id")
    if _string(metadata, "action") not in {
        "create",
        "enable",
        "disable",
        "prompt_created",
        "enabled",
        "disabled",
    }:
        raise AuditSchemaError("audit metadata 'action' is invalid")


def _interactive_command_failed(metadata: Mapping[str, object]) -> None:
    _exact(metadata, frozenset({"action"}))
    _string(metadata, "action")


def _definitions() -> tuple[AuditEventDefinition, ...]:
    definitions = (
        AuditEventDefinition(
            "persona", "persona_summary", "info", "completed",
            metadata_validator=_summary,
        ),
        AuditEventDefinition(
            "persona", "host_discussion_decision", "info", "completed",
            metadata_validator=_host_decision,
        ),
        AuditEventDefinition(
            "persona", "persona_discussion_step", "debug", "running",
            metadata_validator=_discussion_step,
        ),
        AuditEventDefinition(
            "persona", "persona_discussion", "info", "completed",
            metadata_validator=_discussion,
        ),
        AuditEventDefinition(
            "persona", "persona_discussion_failure", "error", "failed",
            error_policy="required",
        ),
        AuditEventDefinition(
            "persona", "persona_discussion_degraded", "warning", "degraded",
            error_policy="required",
            metadata_validator=_discussion_degraded,
        ),
        AuditEventDefinition(
            "persona", "persona_completion_failed", "warning", "degraded",
            error_policy="required",
            metadata_validator=_completion_failed,
        ),
        AuditEventDefinition(
            "persona", "persona_activation_failed", "warning", "degraded",
            error_policy="required",
        ),
        AuditEventDefinition(
            "persona",
            "persona_definition_load_failed",
            "warning",
            "degraded",
            error_policy="required",
        ),
        AuditEventDefinition(
            "persona", "trace_recording_failed", "warning", "degraded",
            error_policy="required",
            metadata_validator=_trace_failed,
        ),
        AuditEventDefinition(
            "persona", "interactive_command_failed", "error", "error",
            error_policy="required",
            metadata_validator=_interactive_command_failed,
        ),
    )
    return definitions

_MESSAGES: dict[PersonaAuditEvent, str] = {
    "persona_summary": "Persona consultation completed",
    "host_discussion_decision": "Persona discussion decision completed",
    "persona_discussion_step": "Persona discussion step completed",
    "persona_discussion": "Persona discussion completed",
    "persona_discussion_failure": "Persona discussion failed",
    "persona_discussion_degraded": "Persona discussion used fallback",
    "persona_completion_failed": "Persona completion used fallback",
    "persona_activation_failed": "Persona activation used fallback",
    "persona_definition_load_failed": (
        "Persona definitions used builtin fallback"
    ),
    "trace_recording_failed": "Persona lifecycle trace recording failed",
    "interactive_command_failed": "Interactive persona command failed",
}


PERSONA_AUDIT = AuditCatalog[PersonaAuditEvent](_definitions(), _MESSAGES)
