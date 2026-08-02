from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from nuself.memory import audit
from nuself.runtime.audit_definitions import (
    AuditSchemaError,
    UnknownAuditDefinitionError,
)

_CANONICAL: tuple[tuple[str, dict[str, object]], ...] = (
    ("curator_contended", {"observation_id": "obs_1"}),
    (
        "curator_deferred",
        {
            "observation_id": "obs_1",
            "source_ref": "interaction:opaque",
            "processed_messages": 0,
        },
    ),
    (
        "curator_completed",
        {
            "observation_id": "obs_1",
            "source_ref": "interaction:opaque",
            "processed_messages": 3,
            "created": 1,
            "updated": 1,
            "ignored": 0,
        },
    ),
    (
        "candidate_merged",
        {
            "candidate_id": "candidate-1",
            "target_entry_id": "memory-1",
            "memory_type": "episode",
        },
    ),
    (
        "candidate_created",
        {"candidate_id": "candidate-1", "memory_type": "episode"},
    ),
    (
        "candidate_updated",
        {
            "candidate_id": "candidate-1",
            "target_entry_id": "memory-1",
            "memory_type": "episode",
        },
    ),
    ("optimizer_deferred", {"reviewed": 0}),
    (
        "optimizer_completed",
        {"reviewed": 3, "updated": 1, "deleted": 1, "ignored": 1},
    ),
    (
        "optimizer_candidate_staged",
        {
            "action": "update",
            "candidate_id": "candidate-1",
            "target_entry_id": "memory-1",
        },
    ),
    (
        "auto_accept_failed",
        {
            "candidate_id": "candidate-1",
            "action": "create",
            "memory_type": "episode",
            "target_entry_id": None,
        },
    ),
    (
        "trace_recording_failed",
        {"memory_id": "memory-1", "action": "add"},
    ),
    ("curator_failed", {}),
    ("post_chat_curation_failed", {}),
    ("chat_trace_recording_failed", {}),
)


def test_memory_registry_owns_complete_taxonomy() -> None:
    assert {
        definition.event
        for definition in audit.MEMORY_AUDIT.registry.definitions
    } == {event for event, _ in _CANONICAL}


@pytest.mark.parametrize(("event", "metadata"), _CANONICAL)
def test_memory_definitions_accept_canonical_payloads(
    event: str,
    metadata: dict[str, object],
) -> None:
    definition = audit.MEMORY_AUDIT.registry.resolve(
        "memory",
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


@pytest.mark.parametrize(("event", "metadata"), _CANONICAL)
def test_memory_definitions_reject_unknown_metadata(
    event: str,
    metadata: dict[str, object],
) -> None:
    definition = audit.MEMORY_AUDIT.registry.resolve(
        "memory",
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
            metadata={**metadata, "title": "private title"},
        )


def test_memory_audit_rejects_unknown_event_before_sink(
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

    with pytest.raises(UnknownAuditDefinitionError):
        audit.MEMORY_AUDIT.write(
            cast(audit.MemoryAuditEvent, "candidate_saved"),
            "invalid",
            project_root=tmp_path,
        )

    assert sink_calls == 0
