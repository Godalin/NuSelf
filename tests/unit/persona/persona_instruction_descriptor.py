"""Tests for persona instruction memory descriptor."""

from __future__ import annotations

# pyright: reportUnusedImport=false

from memory_fixtures import (
    memory_candidate_repository,
    memory_entry_repository,
    source_repository,
)

from collections.abc import Sequence
from pathlib import Path

import pytest
from langchain_core.messages import BaseMessage

from nuself.persona.definition import BUILTIN_PERSONAS
from nuself.persona.graph import AgentBackedActivationPolicy
from nuself.application.projection import load_personas_from_memory
from nuself.persona.definition import (
    PersonaActivationOutput,
    PersonaDefinition,
    PersonaInput,
)
from nuself.memory.model import (
    MemoryObject,
    MemoryValidationError,
    default_memory_type_registry,
)
from nuself.memory.model import MemoryEntry
from nuself.logs import read_log_events
from nuself.memory.repository import MemoryEntryRepository


def test_persona_instruction_descriptor_validates_required_fields() -> None:
    registry = default_memory_type_registry()
    valid = MemoryObject(
        type="persona_instruction",
        payload={"persona_id": "analyst_self", "description": "Test description."},
    )
    registry.validate(valid)  # should not raise


def test_persona_instruction_descriptor_rejects_missing_persona_id() -> None:
    registry = default_memory_type_registry()
    invalid = MemoryObject(
        type="persona_instruction",
        payload={"description": "Test description."},
    )
    try:
        registry.validate(invalid)
        raise AssertionError("expected MemoryValidationError")
    except MemoryValidationError as exc:
        assert any("persona_id" in issue.field for issue in exc.issues)


def test_persona_instruction_descriptor_rejects_empty_description() -> None:
    registry = default_memory_type_registry()
    invalid = MemoryObject(
        type="persona_instruction",
        payload={"persona_id": "analyst_self", "description": ""},
    )
    try:
        registry.validate(invalid)
        raise AssertionError("expected MemoryValidationError")
    except MemoryValidationError as exc:
        assert any("description" in issue.field for issue in exc.issues)


def test_persona_instruction_descriptor_rejects_invalid_routing_markers() -> None:
    registry = default_memory_type_registry()
    invalid = MemoryObject(
        type="persona_instruction",
        payload={
            "persona_id": "analyst_self",
            "description": "Test.",
            "routing_markers": "not-a-list",
        },
    )
    try:
        registry.validate(invalid)
        raise AssertionError("expected MemoryValidationError")
    except MemoryValidationError as exc:
        assert any("routing_markers" in issue.field for issue in exc.issues)


def test_persona_instruction_descriptor_summarizes() -> None:
    registry = default_memory_type_registry()
    memory = MemoryObject(
        type="persona_instruction",
        payload={"persona_id": "analyst_self", "description": "Decomposes questions."},
    )
    summary = registry.summarize(memory)
    assert "analyst_self" in summary
    assert "Decomposes questions." in summary


def test_load_persona_definitions_falls_back_to_defaults(tmp_path: Path) -> None:
    personas = load_personas_from_memory(
        memory_entry_repository(tmp_path),
        project_root=tmp_path,
    )
    ids = {p.id for p in personas}
    assert "analyst_self" in ids
    assert "skeptic_self" in ids
    assert "builder_self" in ids


def test_load_persona_definitions_from_memory(tmp_path: Path) -> None:
    repo = memory_entry_repository(tmp_path)
    repo.save(
        MemoryEntry(
            type="persona_instruction",
            title="custom_self",
            body="A custom persona.",
            payload={
                "persona_id": "custom_self",
                "description": "A custom persona.",
            },
        )
    )

    personas = load_personas_from_memory(
        memory_entry_repository(tmp_path),
        project_root=tmp_path,
    )
    ids = {p.id for p in personas}
    assert "custom_self" in ids
    custom = next(p for p in personas if p.id == "custom_self")
    assert custom.description == "A custom persona."


def test_load_persona_definitions_observes_storage_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_search(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("persona memory unavailable")

    monkeypatch.setattr(MemoryEntryRepository, "search", fail_search)

    personas = load_personas_from_memory(
        memory_entry_repository(tmp_path),
        project_root=tmp_path,
    )

    assert personas == BUILTIN_PERSONAS
    [event] = read_log_events(
        project_root=tmp_path,
        component="persona",
    )
    assert event.event == "persona_definition_load_failed"
    assert event.level == "warning"
    assert event.status == "degraded"
    assert event.error == "persona memory unavailable"
    assert event.metadata == {}


def test_persona_definition_diagnostic_failure_preserves_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_search(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("persona memory unavailable")

    def fail_log(*_args: object, **_kwargs: object) -> object:
        raise OSError("audit store unavailable")

    monkeypatch.setattr(MemoryEntryRepository, "search", fail_search)
    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )

    with pytest.warns(
        RuntimeWarning,
        match="runtime/observability_sink_failed",
    ):
        personas = load_personas_from_memory(
        memory_entry_repository(tmp_path),
        project_root=tmp_path,
    )

    assert personas == BUILTIN_PERSONAS


class _FakeActivationAgent:
    def __init__(self, response: dict[str, object]) -> None:
        self._response = response

    def invoke(
        self,
        messages: Sequence[BaseMessage],
    ) -> PersonaActivationOutput:
        return PersonaActivationOutput.model_validate(self._response)


def test_activation_policy_uses_custom_personas() -> None:
    custom = PersonaDefinition(id="custom_self", description="Custom.")
    policy = AgentBackedActivationPolicy(
        personas=(custom,),
        agent=_FakeActivationAgent({
            "activated": False,
            "selected_persona_ids": [],
            "trigger": "not relevant",
            "should_escalate": False,
            "escalation_reason": "no escalation needed",
        }),
    )
    activation = policy.decide(PersonaInput(user_message="What are the risks?"))
    assert not activation.activated


def test_activation_policy_skips_missing_builtin_personas() -> None:
    policy = AgentBackedActivationPolicy(
        personas=(),
        agent=_FakeActivationAgent({
            "activated": True,
            "selected_persona_ids": ["ghost_self"],
            "trigger": "test",
            "should_escalate": False,
            "escalation_reason": "no escalation needed",
        }),
    )
    activation = policy.decide(PersonaInput(user_message="What are the risks?"))
    # ghost_self is not in the available personas, so no activation
    assert not activation.activated


def test_activation_policy_explicit_request_with_partial_personas() -> None:
    analyst = PersonaDefinition(id="analyst_self", description="Analyst.")
    policy = AgentBackedActivationPolicy(
        personas=(analyst,),
        agent=_FakeActivationAgent({
            "activated": True,
            "selected_persona_ids": ["analyst_self"],
            "trigger": "explicit request",
            "should_escalate": False,
            "escalation_reason": "no escalation needed",
        }),
    )
    activation = policy.decide(PersonaInput(user_message="Discuss this from multiple perspectives"))
    assert activation.activated
    assert activation.selected_personas == (analyst,)
