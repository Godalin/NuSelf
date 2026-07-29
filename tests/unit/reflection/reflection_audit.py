from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from nuself.reflection import audit
from nuself.runtime.audit_definitions import (
    AuditSchemaError,
    UnknownAuditDefinitionError,
)


def test_reflection_audit_registry_owns_complete_taxonomy() -> None:
    assert {
        definition.event
        for definition in audit.REFLECTION_AUDIT_REGISTRY.definitions
    } == {
        "schedule_blocked",
        "cycle_started",
        "cycle_filtered",
        "cycle_discussion_rejected",
        "cycle_completed",
        "relevance_gate_fallback",
        "candidate_generation_skipped",
        "cycle_no_candidates",
        "candidate_generation_failed",
        "schedule_state_corrupt",
        "trace_recording_failed",
        "organizer_failed",
        "organizer_completed",
    }


@pytest.mark.parametrize(
    ("event", "metadata"),
    [
        ("schedule_blocked", {"reason": "quiet_hours"}),
        ("cycle_started", {}),
        (
            "cycle_filtered",
            {"reason": "filtered_by_gate", "score": 0.4},
        ),
        (
            "cycle_discussion_rejected",
            {"reason": "discussion_rejected"},
        ),
        (
            "cycle_completed",
            {
                "reason": "published",
                "score": 0.8,
                "idea_type": "connection",
            },
        ),
        ("relevance_gate_fallback", {}),
        (
            "candidate_generation_skipped",
            {"reason": "empty_context"},
        ),
        ("cycle_no_candidates", {"reason": "no_candidates"}),
        ("candidate_generation_failed", {}),
        ("schedule_state_corrupt", {"record": "last_reflection.json"}),
        ("trace_recording_failed", {"reflection_id": "reflection-1"}),
        ("organizer_failed", {}),
        (
            "organizer_completed",
            {"merged_groups": 1, "archived_entries": 2},
        ),
    ],
)
def test_reflection_audit_definitions_accept_canonical_payloads(
    event: str,
    metadata: dict[str, object],
) -> None:
    definition = audit.REFLECTION_AUDIT_REGISTRY.resolve(
        "reflection",
        event,
    )

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


@pytest.mark.parametrize(
    "event",
    [
        definition.event
        for definition in audit.REFLECTION_AUDIT_REGISTRY.definitions
    ],
)
def test_reflection_audit_definitions_reject_unknown_metadata(
    event: str,
) -> None:
    definition = audit.REFLECTION_AUDIT_REGISTRY.resolve(
        "reflection",
        event,
    )

    with pytest.raises(AuditSchemaError, match="metadata"):
        definition.validate(
            level=definition.level,
            status=definition.status,
            error=(
                "caught failure"
                if definition.error_policy == "required"
                else None
            ),
            metadata={"unexpected": True},
        )


def test_reflection_audit_rejects_unknown_event_before_sink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sink_calls = 0

    def unexpected_sink(*args: object, **kwargs: object) -> None:
        nonlocal sink_calls
        sink_calls += 1

    monkeypatch.setattr(audit, "write_observed_log_event", unexpected_sink)

    with pytest.raises(UnknownAuditDefinitionError):
        audit.write_reflection_audit(
            cast(audit.ReflectionAuditEvent, "cycle_compeleted"),
            "invalid",
            project_root=tmp_path,
        )

    assert sink_calls == 0


def test_reflection_audit_rejects_invalid_metadata_before_sink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sink_calls = 0

    def unexpected_sink(*args: object, **kwargs: object) -> None:
        nonlocal sink_calls
        sink_calls += 1

    monkeypatch.setattr(audit, "write_observed_log_event", unexpected_sink)

    with pytest.raises(AuditSchemaError, match="score"):
        audit.write_reflection_audit(
            "cycle_filtered",
            "invalid",
            project_root=tmp_path,
            metadata={"reason": "filtered_by_gate", "score": 2.0},
        )

    assert sink_calls == 0
