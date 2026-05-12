from __future__ import annotations

from nuself.agent.persona import ANALYST_PERSONA, BUILDER_PERSONA, HostDiscussionPolicy


def test_host_discussion_policy_escalates_for_explicit_request() -> None:
    policy = HostDiscussionPolicy()

    decision = policy.decide(
        user_message="Can we discuss this from multiple perspectives?",
        synthesis_summary="",
        selected_personas=(),
    )

    assert decision.should_escalate is True
    assert decision.reason == "host sees explicit request for multi-perspective discussion"
    assert "multiple perspectives" in decision.matched_markers


def test_host_discussion_policy_skips_plain_request() -> None:
    policy = HostDiscussionPolicy()

    decision = policy.decide(
        user_message="What is the current status?",
        synthesis_summary="",
        selected_personas=(),
    )

    assert decision.should_escalate is False
    assert decision.reason == "host does not see enough discussion depth"
    assert decision.matched_markers == ()


def test_host_discussion_policy_escalates_for_tradeoff_with_selected_personas() -> None:
    policy = HostDiscussionPolicy()

    decision = policy.decide(
        user_message="What tradeoffs should I consider for this architecture decision?",
        synthesis_summary="",
        selected_personas=(ANALYST_PERSONA, BUILDER_PERSONA),
    )

    assert decision.should_escalate is True
    assert decision.reason == "host sees a deep tradeoff that merits competitive discussion"
    assert "tradeoff" in decision.matched_markers
