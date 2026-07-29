from __future__ import annotations

from collections.abc import Sequence

from langchain_core.messages import BaseMessage
from nuself.persona import AgentBackedActivationPolicy
from nuself.persona.definition import (
    ANALYST_PERSONA,
    BUILDER_PERSONA,
    PersonaActivationOutput,
    PersonaInput,
)


class _FakeActivationAgent:
    def __init__(self, response: dict[str, object]) -> None:
        self._response = response

    def invoke(
        self,
        messages: Sequence[BaseMessage],
    ) -> PersonaActivationOutput:
        return PersonaActivationOutput.model_validate(self._response)


def test_host_escalation_for_explicit_request() -> None:
    policy = AgentBackedActivationPolicy(
        agent=_FakeActivationAgent({
            "activated": True,
            "selected_persona_ids": ["analyst_self"],
            "trigger": "explicit request",
            "should_escalate": True,
            "escalation_reason": "user asked for multi-perspective discussion",
        })
    )

    activation = policy.decide(PersonaInput(user_message="Can we discuss this from multiple perspectives?"))

    assert activation.should_escalate is True
    assert activation.escalation_reason == "user asked for multi-perspective discussion"


def test_host_skips_plain_request() -> None:
    policy = AgentBackedActivationPolicy(
        agent=_FakeActivationAgent({
            "activated": False,
            "selected_persona_ids": [],
            "trigger": "no signal",
            "should_escalate": False,
            "escalation_reason": "no escalation needed",
        })
    )

    activation = policy.decide(PersonaInput(user_message="What is the current status?"))

    assert activation.should_escalate is False


def test_host_escalates_for_tradeoff_with_multiple_personas() -> None:
    policy = AgentBackedActivationPolicy(
        agent=_FakeActivationAgent({
            "activated": True,
            "selected_persona_ids": ["analyst_self", "builder_self"],
            "trigger": "architecture tradeoff",
            "should_escalate": True,
            "escalation_reason": "deep tradeoff with multiple relevant personas",
        })
    )

    activation = policy.decide(
        PersonaInput(user_message="What tradeoffs should I consider for this architecture decision?")
    )

    assert activation.should_escalate is True
    assert activation.selected_personas == (ANALYST_PERSONA, BUILDER_PERSONA)
    assert activation.escalation_reason == "deep tradeoff with multiple relevant personas"
