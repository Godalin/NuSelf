"""Tests for persona instruction memory descriptor."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from langchain_core.messages import BaseMessage

from nuself.persona import (
    AgentBackedActivationPolicy,
    load_persona_definitions,
)
from nuself.persona.definition import (
    PersonaActivationOutput,
    PersonaDefinition,
    PersonaInput,
)
from nuself.domain.memory import (
    MemoryObject,
    MemoryValidationError,
    default_memory_type_registry,
)
from nuself.domain.memory import MemoryEntry
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
    personas = load_persona_definitions(tmp_path)
    ids = {p.id for p in personas}
    assert "analyst_self" in ids
    assert "skeptic_self" in ids
    assert "builder_self" in ids


def test_load_persona_definitions_from_memory(tmp_path: Path) -> None:
    repo = MemoryEntryRepository(tmp_path)
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

    personas = load_persona_definitions(tmp_path)
    ids = {p.id for p in personas}
    assert "custom_self" in ids
    custom = next(p for p in personas if p.id == "custom_self")
    assert custom.description == "A custom persona."


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
