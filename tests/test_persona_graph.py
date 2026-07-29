from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Generic, Never, TypeVar

import pytest
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, ValidationError

from nuself.logs import read_log_events
from nuself.persona import (
    AgentBackedActivationPolicy,
    AgentBackedPersonaNode,
    AgentBackedSynthesizerNode,
    PersonaGraphDriver,
)
from nuself.persona.definition import (
    ANALYST_PERSONA,
    BUILDER_PERSONA,
    CARE_PERSONA,
    HISTORIAN_PERSONA,
    SKEPTIC_PERSONA,
    PersonaContribution,
    PersonaContributionOutput,
    PersonaDefinition,
    PersonaInput,
    PersonaActivationOutput,
    PersonaSynthesis,
    PersonaSynthesisOutput,
    PersonaTurnState,
)


OutputT = TypeVar("OutputT", bound=BaseModel)


class _StaticAgent(Generic[OutputT]):
    def __init__(self, output: OutputT) -> None:
        self.output = output
        self.calls: list[Sequence[BaseMessage]] = []

    def invoke(self, messages: Sequence[BaseMessage]) -> OutputT:
        self.calls.append(messages)
        return self.output


class _FakeActivationAgent:
    """Deterministic typed activation agent."""

    def __init__(self, response: dict[str, object] | None = None) -> None:
        self._response = response or {
            "activated": True,
            "selected_persona_ids": ["skeptic_self"],
            "trigger": "risk detected",
            "should_escalate": False,
            "escalation_reason": "no escalation needed",
        }

    def invoke(
        self,
        messages: Sequence[BaseMessage],
    ) -> PersonaActivationOutput:
        return PersonaActivationOutput.model_validate(self._response)


@pytest.mark.parametrize(
    ("schema", "payload"),
    [
        (
            PersonaContributionOutput,
            {"note": "Perspective", "confidence": 1.1},
        ),
        (
            PersonaContributionOutput,
            {"note": 3},
        ),
        (
            PersonaSynthesisOutput,
            {"summary": "Synthesis", "unexpected": True},
        ),
        (
            PersonaActivationOutput,
            {"activated": 1},
        ),
    ],
)
def test_persona_output_models_reject_coercion_bounds_and_extra_fields(
    schema: type[BaseModel],
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        schema.model_validate(payload)


class _BrokenAgent:
    def invoke(self, messages: Sequence[BaseMessage]) -> Never:
        raise RuntimeError("simulated LLM failure")


class _ImplementationFailingAgent:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def invoke(self, messages: Sequence[BaseMessage]) -> Never:
        del messages
        raise self._error


def test_persona_graph_runs_minimal_internal_persona() -> None:
    driver = PersonaGraphDriver()
    state = PersonaTurnState(
        input=PersonaInput(user_message="Should I split this project?"),
        selected_personas=(ANALYST_PERSONA,),
    )

    result = driver.run(state)

    assert result.node_trace == ("run_personas", "run_synthesizer")
    assert result.contributions == (
        PersonaContribution(
            persona_id="analyst_self",
            notes=("analyst_self considered: Should I split this project?",),
            confidence=0.0,
        ),
    )
    assert result.synthesis == PersonaSynthesis(
        summary="analyst_self considered: Should I split this project?",
        source_personas=("analyst_self",),
        confidence=0.0,
    )


def test_persona_graph_accepts_custom_persona_node() -> None:
    class CustomPersonaNode:
        def __call__(self, persona: PersonaDefinition, persona_input: PersonaInput) -> PersonaContribution:
            return PersonaContribution(
                persona_id=persona.id,
                notes=(f"memory={persona_input.memory_context}",),
                questions=("What is the next constraint?",),
                confidence=0.6,
            )

    driver = PersonaGraphDriver(persona_node=CustomPersonaNode())
    state = PersonaTurnState(
        input=PersonaInput(user_message="Plan", memory_context="Keep it narrow."),
        selected_personas=(ANALYST_PERSONA,),
    )

    result = driver.run(state)

    assert result.contributions == (
        PersonaContribution(
            persona_id="analyst_self",
            notes=("memory=Keep it narrow.",),
            questions=("What is the next constraint?",),
            confidence=0.6,
        ),
    )
    assert result.synthesis == PersonaSynthesis(
        summary="memory=Keep it narrow.",
        source_personas=("analyst_self",),
        confidence=0.0,
    )


def test_persona_graph_runs_builder_persona_notes() -> None:
    driver = PersonaGraphDriver()
    state = PersonaTurnState(
        input=PersonaInput(user_message="Please plan concrete execution steps."),
        selected_personas=(BUILDER_PERSONA,),
    )

    result = driver.run(state)

    assert result.contributions == (
        PersonaContribution(
            persona_id="builder_self",
            notes=("builder_self proposed concrete steps for: Please plan concrete execution steps.",),
            confidence=0.0,
        ),
    )


def test_persona_graph_runs_historian_persona_notes() -> None:
    driver = PersonaGraphDriver()
    state = PersonaTurnState(
        input=PersonaInput(user_message="Let's review what happened earlier before deciding."),
        selected_personas=(HISTORIAN_PERSONA,),
    )

    result = driver.run(state)

    assert result.contributions == (
        PersonaContribution(
            persona_id="historian_self",
            notes=("historian_self connected prior context to: Let's review what happened earlier before deciding.",),
            confidence=0.0,
        ),
    )


def test_persona_graph_runs_care_persona_notes() -> None:
    driver = PersonaGraphDriver()
    state = PersonaTurnState(
        input=PersonaInput(user_message="I'm stressed and need support with this plan."),
        selected_personas=(CARE_PERSONA,),
    )

    result = driver.run(state)

    assert result.contributions == (
        PersonaContribution(
            persona_id="care_self",
            notes=("care_self highlighted emotional and human impact in: I'm stressed and need support with this plan.",),
            confidence=0.0,
        ),
    )


def test_persona_graph_runs_analyst_and_skeptic_together() -> None:
    driver = PersonaGraphDriver()
    state = PersonaTurnState(
        input=PersonaInput(user_message="Should I split this project?"),
        selected_personas=(ANALYST_PERSONA, SKEPTIC_PERSONA),
    )

    result = driver.run(state)

    assert result.node_trace == ("run_personas", "run_synthesizer")
    assert len(result.contributions) == 2
    assert result.contributions[0].persona_id == "analyst_self"
    assert result.contributions[1].persona_id == "skeptic_self"
    assert result.synthesis is not None
    assert result.synthesis.source_personas == ("analyst_self", "skeptic_self")


def test_persona_graph_with_llm_backed_nodes() -> None:
    driver = PersonaGraphDriver(
        persona_node=AgentBackedPersonaNode(
            _StaticAgent(
                PersonaContributionOutput(
                    note="fake note",
                    questions=[],
                    confidence=0.5,
                )
            )
        ),
        synthesizer_node=AgentBackedSynthesizerNode(
            _StaticAgent(
                PersonaSynthesisOutput(
                    summary="fake note",
                    confidence=0.5,
                )
            )
        ),
    )
    state = PersonaTurnState(
        input=PersonaInput(user_message="What is consciousness?"),
        selected_personas=(ANALYST_PERSONA,),
    )

    result = driver.run(state)

    assert result.contributions[0].notes == ("fake note",)
    assert result.synthesis is not None
    assert result.synthesis.summary == "fake note"


# --- AgentBackedActivationPolicy tests ---


def test_llm_backed_activation_selects_personas() -> None:
    policy = AgentBackedActivationPolicy(agent=_FakeActivationAgent())

    activation = policy.decide(PersonaInput(user_message="What are the biggest risks?"))

    assert activation.activated is True
    assert activation.selected_personas == (SKEPTIC_PERSONA,)
    assert activation.trigger == "risk detected"


def test_llm_backed_activation_escalates() -> None:
    policy = AgentBackedActivationPolicy(
        agent=_FakeActivationAgent({
            "activated": True,
            "selected_persona_ids": ["analyst_self", "skeptic_self"],
            "trigger": "deep tradeoff",
            "should_escalate": True,
            "escalation_reason": "complex decision needs competitive discussion",
        })
    )

    activation = policy.decide(PersonaInput(user_message="Should I take this job or start a company?"))

    assert activation.activated is True
    assert activation.selected_personas == (ANALYST_PERSONA, SKEPTIC_PERSONA)
    assert activation.should_escalate is True
    assert activation.escalation_reason == "complex decision needs competitive discussion"


def test_llm_backed_activation_no_match_returns_empty() -> None:
    policy = AgentBackedActivationPolicy(
        agent=_FakeActivationAgent({
            "activated": False,
            "selected_persona_ids": [],
            "trigger": "not relevant",
            "should_escalate": False,
            "escalation_reason": "no escalation needed",
        })
    )

    activation = policy.decide(PersonaInput(user_message="Hello"))

    assert activation.activated is False
    assert activation.selected_personas == ()
    assert activation.should_escalate is False


def test_llm_backed_activation_fallback_on_failure(tmp_path: Path) -> None:
    policy = AgentBackedActivationPolicy(
        agent=_BrokenAgent(),
        project_root=tmp_path,
    )

    activation = policy.decide(PersonaInput(user_message="What are the risks?"))

    assert activation.activated is False
    assert activation.trigger == "agent_fallback"
    assert activation.should_escalate is False
    [event] = read_log_events(
        project_root=tmp_path,
        component="persona",
    )
    assert event.event == "persona_activation_failed"
    assert event.error == "simulated LLM failure"
    assert event.metadata == {}


def test_llm_backed_activation_ignores_unknown_persona_ids() -> None:
    policy = AgentBackedActivationPolicy(
        agent=_FakeActivationAgent({
            "activated": True,
            "selected_persona_ids": ["unknown_self", "skeptic_self"],
            "trigger": "mixed",
            "should_escalate": False,
            "escalation_reason": "no escalation needed",
        })
    )

    activation = policy.decide(PersonaInput(user_message="Test"))

    assert activation.selected_personas == (SKEPTIC_PERSONA,)


def test_llm_backed_activation_rejects_string_bool() -> None:
    policy = AgentBackedActivationPolicy(
        agent=_FakeActivationAgent({
            "activated": "true",
            "selected_persona_ids": ["builder_self"],
            "trigger": "planning",
            "should_escalate": "yes",
            "escalation_reason": "needs roadmap",
        })
    )

    activation = policy.decide(PersonaInput(user_message="Plan this"))

    assert activation.activated is False
    assert activation.trigger == "agent_fallback"
    assert activation.should_escalate is False
    assert activation.selected_personas == ()


def test_llm_backed_activation_no_llm_returns_safe_fallback() -> None:
    policy = AgentBackedActivationPolicy(agent=None)

    activation = policy.decide(PersonaInput(user_message="Anything"))

    assert activation.activated is False
    assert activation.trigger == "no_agent"


def test_llm_backed_persona_failure_is_observed_before_fallback(
    tmp_path: Path,
) -> None:
    node = AgentBackedPersonaNode(
        agent=_BrokenAgent(),
        project_root=tmp_path,
    )

    result = node(
        ANALYST_PERSONA,
        PersonaInput(user_message="Review this"),
    )

    assert result.notes == ("analyst_self considered the topic.",)
    [event] = read_log_events(
        project_root=tmp_path,
        component="persona",
    )
    assert event.event == "persona_completion_failed"
    assert event.error == "simulated LLM failure"
    assert event.metadata == {"stage": "contribution"}


def test_llm_backed_synthesis_failure_is_observed_before_fallback(
    tmp_path: Path,
) -> None:
    node = AgentBackedSynthesizerNode(
        agent=_BrokenAgent(),
        project_root=tmp_path,
    )
    state = PersonaTurnState(
        input=PersonaInput(user_message="Review this"),
        selected_personas=(),
        contributions=(
            PersonaContribution(
                persona_id="analyst_self",
                notes=("Analyze the boundary.",),
            ),
        ),
    )

    result = node(state)

    assert result is not None
    assert result.summary == "- analyst_self: Analyze the boundary."
    [event] = read_log_events(
        project_root=tmp_path,
        component="persona",
    )
    assert event.event == "persona_completion_failed"
    assert event.error == "simulated LLM failure"
    assert event.metadata == {"stage": "synthesis"}


@pytest.mark.parametrize(
    "error",
    [
        AssertionError("broken persona invariant"),
        AttributeError("missing persona dependency"),
        KeyError("missing persona registry entry"),
        NotImplementedError("persona path is not implemented"),
        TypeError("invalid internal persona call"),
    ],
    ids=["assertion", "attribute", "lookup", "not-implemented", "type"],
)
@pytest.mark.parametrize(
    "stage",
    ["activation", "contribution", "synthesis"],
)
def test_persona_implementation_errors_propagate_without_fallback(
    tmp_path: Path,
    stage: str,
    error: Exception,
) -> None:
    agent = _ImplementationFailingAgent(error)

    with pytest.raises(type(error)) as caught:
        if stage == "activation":
            AgentBackedActivationPolicy(
                agent=agent,
                project_root=tmp_path,
            ).decide(PersonaInput(user_message="Review this"))
        elif stage == "contribution":
            AgentBackedPersonaNode(
                agent=agent,
                project_root=tmp_path,
            )(
                ANALYST_PERSONA,
                PersonaInput(user_message="Review this"),
            )
        else:
            AgentBackedSynthesizerNode(
                agent=agent,
                project_root=tmp_path,
            )(
                PersonaTurnState(
                    input=PersonaInput(user_message="Review this"),
                    selected_personas=(),
                    contributions=(
                        PersonaContribution(
                            persona_id="analyst_self",
                            notes=("Analyze the boundary.",),
                        ),
                    ),
                )
            )

    assert caught.value is error
    assert read_log_events(
        project_root=tmp_path,
        component="persona",
    ) == []


def test_completion_diagnostic_failure_does_not_replace_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("diagnostic store unavailable")

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    node = AgentBackedPersonaNode(
        agent=_BrokenAgent(),
        project_root=tmp_path,
    )

    with pytest.warns(
        RuntimeWarning,
        match="runtime/observability_sink_failed",
    ):
        result = node(
            ANALYST_PERSONA,
            PersonaInput(user_message="Review this"),
        )

    assert result.notes == ("analyst_self considered the topic.",)
