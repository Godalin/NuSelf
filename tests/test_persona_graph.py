from __future__ import annotations

from nuself.agent.persona import (
    ANALYST_PERSONA,
    BUILDER_PERSONA,
    CARE_PERSONA,
    HISTORIAN_PERSONA,
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
    assert activation.trigger == "explicit_relevant_personas"
    assert activation.selected_personas == (BUILDER_PERSONA,)


def test_persona_activation_policy_selects_skeptic_for_risk_prompt() -> None:
    policy = PersonaActivationPolicy()

    activation = policy.decide(PersonaInput(user_message="What are the biggest risks and blind spots here?"))

    assert activation.activated is True
    assert activation.trigger == "skeptic_heuristic"
    assert activation.selected_personas == (SKEPTIC_PERSONA,)


def test_persona_activation_policy_selects_builder_for_planning_prompt() -> None:
    policy = PersonaActivationPolicy()

    activation = policy.decide(PersonaInput(user_message="Can you propose an implementation roadmap with steps?"))

    assert activation.activated is True
    assert activation.trigger == "builder_heuristic"
    assert activation.selected_personas == (BUILDER_PERSONA,)


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


def test_persona_activation_policy_selects_historian_for_retrospective_prompt() -> None:
    policy = PersonaActivationPolicy()

    activation = policy.decide(PersonaInput(user_message="Can we review the timeline and what happened earlier?"))

    assert activation.activated is True
    assert activation.trigger == "historian_heuristic"
    assert activation.selected_personas == (HISTORIAN_PERSONA,)


def test_persona_activation_policy_applies_mixed_intent_precedence() -> None:
    policy = PersonaActivationPolicy()

    activation = policy.decide(
        PersonaInput(user_message="What are the risks, and can you give an implementation roadmap for this decision?")
    )

    assert activation.activated is True
    assert activation.trigger == "mixed_intent_heuristic"
    assert activation.selected_personas == (SKEPTIC_PERSONA, BUILDER_PERSONA, ANALYST_PERSONA)


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


def test_persona_activation_policy_selects_care_for_emotional_prompt() -> None:
    policy = PersonaActivationPolicy()

    activation = policy.decide(PersonaInput(user_message="I'm feeling stressed and anxious about this situation."))

    assert activation.activated is True
    assert activation.trigger == "care_heuristic"
    assert activation.selected_personas == (CARE_PERSONA,)


def test_persona_activation_policy_explicit_multi_view_includes_all_relevant_personas() -> None:
    policy = PersonaActivationPolicy()

    activation = policy.decide(
        PersonaInput(
            user_message=(
                "Please provide multiple perspectives: what are the risks, implementation roadmap, "
                "timeline context, and emotional impact?"
            )
        )
    )

    assert activation.activated is True
    assert activation.trigger == "explicit_relevant_personas"
    assert activation.selected_personas == (
        SKEPTIC_PERSONA,
        BUILDER_PERSONA,
        HISTORIAN_PERSONA,
        CARE_PERSONA,
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
