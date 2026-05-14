from __future__ import annotations

import json

from nuself.agent.persona import (
    ANALYST_PERSONA,
    BUILDER_PERSONA,
    LLMBackedActivationPolicy,
    PersonaInput,
)


class _FakeActivationLLM:
    def __init__(self, response: dict[str, object]) -> None:
        self._response = response

    def complete(self, messages: object) -> str:
        return json.dumps(self._response)


def test_host_escalation_for_explicit_request() -> None:
    policy = LLMBackedActivationPolicy(
        llm=_FakeActivationLLM({
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
    policy = LLMBackedActivationPolicy(
        llm=_FakeActivationLLM({
            "activated": False,
            "selected_persona_ids": [],
            "trigger": "no signal",
            "should_escalate": False,
            "escalation_reason": "",
        })
    )

    activation = policy.decide(PersonaInput(user_message="What is the current status?"))

    assert activation.should_escalate is False


def test_host_escalates_for_tradeoff_with_multiple_personas() -> None:
    policy = LLMBackedActivationPolicy(
        llm=_FakeActivationLLM({
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
