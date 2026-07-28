from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from nuself.persona import audit
from nuself.runtime.audit_definitions import (
    AuditSchemaError,
    UnknownAuditDefinitionError,
)

_CANONICAL: tuple[tuple[str, dict[str, object]], ...] = (
    (
        "persona_summary",
        {"persona_count": 2, "has_synthesis": True},
    ),
    ("host_discussion_decision", {"should_escalate": False}),
    ("persona_discussion_step", {"step_number": 1}),
    (
        "persona_discussion",
        {
            "candidate_id": "candidate-1",
            "approved": True,
            "winner_count": 2,
            "emergent_count": 0,
            "blocking_veto_count": 0,
            "score_count": 3,
            "discussion_steps": 8,
        },
    ),
    ("persona_discussion_failure", {}),
    ("persona_discussion_degraded", {"stage": "scoring"}),
    ("persona_completion_failed", {"stage": "contribution"}),
    ("persona_activation_failed", {}),
    (
        "trace_recording_failed",
        {"persona_prompt_id": "persona-1", "action": "create"},
    ),
    ("interactive_command_failed", {"action": "create"}),
)


def test_persona_registry_owns_complete_taxonomy() -> None:
    assert {
        definition.event
        for definition in audit.PERSONA_AUDIT_REGISTRY.definitions
    } == {event for event, _ in _CANONICAL}


@pytest.mark.parametrize(("event", "metadata"), _CANONICAL)
def test_persona_definitions_accept_canonical_payloads(
    event: str,
    metadata: dict[str, object],
) -> None:
    definition = audit.PERSONA_AUDIT_REGISTRY.resolve("persona", event)

    definition.validate(
        level=definition.level,
        status=definition.status,
        error=(
            "caught failure"
            if definition.error_policy == "required"
            else None
        ),
        metadata=metadata,
    )


@pytest.mark.parametrize(("event", "metadata"), _CANONICAL)
def test_persona_definitions_reject_private_or_unknown_metadata(
    event: str,
    metadata: dict[str, object],
) -> None:
    definition = audit.PERSONA_AUDIT_REGISTRY.resolve("persona", event)

    with pytest.raises(AuditSchemaError, match="metadata"):
        definition.validate(
            level=definition.level,
            status=definition.status,
            error=(
                "caught failure"
                if definition.error_policy == "required"
                else None
            ),
            metadata={**metadata, "discussion_trace": ["private utterance"]},
        )


def test_persona_audit_rejects_unknown_event_before_sink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sink_calls = 0

    def unexpected_sink(*args: object, **kwargs: object) -> None:
        nonlocal sink_calls
        sink_calls += 1

    monkeypatch.setattr(audit, "write_observed_log_event", unexpected_sink)

    with pytest.raises(UnknownAuditDefinitionError):
        audit.write_persona_audit(
            cast(audit.PersonaAuditEvent, "persona_summmary"),
            project_root=tmp_path,
        )

    assert sink_calls == 0


def test_persona_audit_rejects_sensitive_metadata_before_sink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sink_calls = 0

    def unexpected_sink(*args: object, **kwargs: object) -> None:
        nonlocal sink_calls
        sink_calls += 1

    monkeypatch.setattr(audit, "write_observed_log_event", unexpected_sink)

    with pytest.raises(AuditSchemaError, match="metadata"):
        audit.write_persona_audit(
            "persona_summary",
            project_root=tmp_path,
            metadata={
                "persona_count": 1,
                "has_synthesis": True,
                "summary": "private synthesis",
            },
        )

    assert sink_calls == 0
