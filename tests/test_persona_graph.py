from __future__ import annotations

import json
from typing import cast

from nuself.agent.persona import (
    ANALYST_PERSONA,
    BUILDER_PERSONA,
    CARE_PERSONA,
    HISTORIAN_PERSONA,
    SKEPTIC_PERSONA,
    PersonaContribution,
    PersonaDefinition,
    LLMBackedActivationPolicy,
    LLMBackedPersonaNode,
    LLMBackedSynthesizerNode,
    PersonaActivationOutput,
    PersonaContributionOutput,
    PersonaGraphDriver,
    PersonaInput,
    PersonaSynthesisOutput,
    PersonaSynthesis,
    PersonaTurnState,
)


class _FakeActivationLLM:
    """Deterministic LLM that returns activation JSON responses."""

    def __init__(self, response: dict[str, object] | None = None) -> None:
        self._response = response or {
            "activated": True,
            "selected_persona_ids": ["skeptic_self"],
            "trigger": "risk detected",
            "should_escalate": False,
            "escalation_reason": "",
        }

    def complete(self, messages: object) -> str:
        return json.dumps(self._response)


class _BrokenLLM:
    def complete(self, messages: object) -> str:
        raise RuntimeError("simulated LLM failure")


class _FailingTextLLM:
    def complete(self, messages: object) -> str:
        raise AssertionError("structured persona path should not use text LLM fallback")


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
    from nuself.llm import ChatLLM, ChatMessage

    class FakeLLM(ChatLLM):
        def complete(self, messages: list[ChatMessage]) -> str:
            return "fake note"

    driver = PersonaGraphDriver(
        persona_node=LLMBackedPersonaNode(llm=FakeLLM()),
        synthesizer_node=LLMBackedSynthesizerNode(llm=FakeLLM()),
    )
    state = PersonaTurnState(
        input=PersonaInput(user_message="What is consciousness?"),
        selected_personas=(ANALYST_PERSONA,),
    )

    result = driver.run(state)

    assert result.contributions[0].notes == ("fake note",)
    assert result.synthesis is not None
    assert result.synthesis.summary == "fake note"


# --- LLMBackedActivationPolicy tests ---


def test_llm_backed_activation_selects_personas() -> None:
    policy = LLMBackedActivationPolicy(llm=_FakeActivationLLM())

    activation = policy.decide(PersonaInput(user_message="What are the biggest risks?"))

    assert activation.activated is True
    assert activation.selected_personas == (SKEPTIC_PERSONA,)
    assert activation.trigger == "risk detected"


def test_llm_backed_activation_escalates() -> None:
    policy = LLMBackedActivationPolicy(
        llm=_FakeActivationLLM({
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
    policy = LLMBackedActivationPolicy(
        llm=_FakeActivationLLM({
            "activated": False,
            "selected_persona_ids": [],
            "trigger": "not relevant",
            "should_escalate": False,
            "escalation_reason": "",
        })
    )

    activation = policy.decide(PersonaInput(user_message="Hello"))

    assert activation.activated is False
    assert activation.selected_personas == ()
    assert activation.should_escalate is False


def test_llm_backed_activation_fallback_on_failure() -> None:
    policy = LLMBackedActivationPolicy(llm=_BrokenLLM())

    activation = policy.decide(PersonaInput(user_message="What are the risks?"))

    assert activation.activated is False
    assert activation.trigger == "llm_fallback"
    assert activation.should_escalate is False


def test_llm_backed_activation_ignores_unknown_persona_ids() -> None:
    policy = LLMBackedActivationPolicy(
        llm=_FakeActivationLLM({
            "activated": True,
            "selected_persona_ids": ["unknown_self", "skeptic_self"],
            "trigger": "mixed",
            "should_escalate": False,
            "escalation_reason": "",
        })
    )

    activation = policy.decide(PersonaInput(user_message="Test"))

    assert activation.selected_personas == (SKEPTIC_PERSONA,)


def test_llm_backed_activation_parses_string_bool() -> None:
    policy = LLMBackedActivationPolicy(
        llm=_FakeActivationLLM({
            "activated": "true",
            "selected_persona_ids": ["builder_self"],
            "trigger": "planning",
            "should_escalate": "yes",
            "escalation_reason": "needs roadmap",
        })
    )

    activation = policy.decide(PersonaInput(user_message="Plan this"))

    assert activation.activated is True
    assert activation.should_escalate is True
    assert activation.selected_personas == (BUILDER_PERSONA,)


def test_llm_backed_activation_no_llm_returns_safe_fallback() -> None:
    policy = LLMBackedActivationPolicy(llm=None)

    activation = policy.decide(PersonaInput(user_message="Anything"))

    assert activation.activated is False
    assert activation.trigger == "no_llm"
