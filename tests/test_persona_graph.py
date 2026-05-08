from __future__ import annotations

from nuself.agent.persona import (
    ANALYST_PERSONA,
    SKEPTIC_PERSONA,
    PersonaContribution,
    PersonaDefinition,
    PersonaActivationPolicy,
    PersonaGraphDriver,
    PersonaInput,
    PersonaTurnState,
)


def test_persona_graph_runs_minimal_internal_persona() -> None:
    driver = PersonaGraphDriver()
    state = PersonaTurnState(
        input=PersonaInput(user_message="Should I split this project?"),
        selected_personas=(ANALYST_PERSONA,),
    )

    result = driver.run(state)

    assert result.node_trace == ("run_personas",)
    assert result.contributions == (
        PersonaContribution(
            persona_id="analyst_self",
            notes=("analyst_self considered: Should I split this project?",),
            confidence=0.0,
        ),
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


def test_persona_activation_policy_selects_analyst_and_skeptic_for_explicit_multi_view_request() -> None:
    policy = PersonaActivationPolicy()

    activation = policy.decide(PersonaInput(user_message="Please give me multiple perspectives on this plan."))

    assert activation.activated is True
    assert activation.trigger == "explicit_request"
    assert activation.selected_personas == (ANALYST_PERSONA, SKEPTIC_PERSONA)


def test_persona_activation_policy_selects_skeptic_for_risk_prompt() -> None:
    policy = PersonaActivationPolicy()

    activation = policy.decide(PersonaInput(user_message="What are the biggest risks and blind spots here?"))

    assert activation.activated is True
    assert activation.trigger == "skeptic_heuristic"
    assert activation.selected_personas == (SKEPTIC_PERSONA,)
