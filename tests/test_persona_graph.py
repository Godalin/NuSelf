from __future__ import annotations

from nuself.agent.persona import (
    ANALYST_PERSONA,
    PersonaContribution,
    PersonaDefinition,
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
