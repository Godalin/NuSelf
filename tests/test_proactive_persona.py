# pyright: reportPrivateUsage=false
"""Tests for competitive proactive persona discussion."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Generic, Never, TypeVar

import pytest
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, ValidationError

from nuself.agent.errors import AgentInvalidOutputError, AgentModelUnavailableError
from nuself.domain.proactive import IdeaCandidate
from nuself.logs import read_log_events
from nuself.persona import (
    PersonaCompetitionResult,
    ProactivePersonaDiscussion,
)
from nuself.persona.discussion import (
    AgentBackedScoringPersonaNode,
    ModeratorJudgmentOutput,
    PersonaDiscussionAgents,
    PersonaScoreOutput,
    PersonaSelectionOutput,
)
from nuself.persona.definition import (
    ANALYST_PERSONA,
    BUILDER_PERSONA,
    HISTORIAN_PERSONA,
    SKEPTIC_PERSONA,
    PersonaContribution,
    PersonaDefinition,
    PersonaInput,
    PersonaSynthesis,
    PersonaSynthesisOutput,
    PersonaTurnState,
)


class _FakePersonaDriver:
    def run(self, turn_state: PersonaTurnState) -> PersonaTurnState:
        contributions: list[PersonaContribution] = []
        notes: list[str] = []
        for persona in turn_state.selected_personas:
            note = f"{persona.id}|{turn_state.input.memory_context}"
            contributions.append(PersonaContribution(persona_id=persona.id, notes=(note,), confidence=0.0))
            notes.append(note)
        return PersonaTurnState(
            input=turn_state.input,
            selected_personas=turn_state.selected_personas,
            contributions=tuple(contributions),
            synthesis=PersonaSynthesis(
                summary=" | ".join(notes),
                source_personas=tuple(p.id for p in turn_state.selected_personas),
                confidence=0.0,
            ),
        )

    def run_personas_only(self, turn_state: PersonaTurnState) -> PersonaTurnState:
        full = self.run(turn_state)
        return PersonaTurnState(
            input=full.input,
            selected_personas=full.selected_personas,
            contributions=full.contributions,
        )


OutputT = TypeVar("OutputT", bound=BaseModel)


class _FixtureAgent(Generic[OutputT]):
    def __init__(
        self,
        fixture: _FakeLLM,
        key: str,
        schema: type[OutputT],
    ) -> None:
        self._fixture = fixture
        self._key = key
        self._schema = schema

    def invoke(
        self,
        messages: Sequence[BaseMessage],
    ) -> OutputT:
        self._fixture.agent_calls.append(messages)
        try:
            return self._schema.model_validate_json(
                self._fixture.response(self._key)
            )
        except ValidationError as exc:
            raise AgentInvalidOutputError(
                f"{self._key} agent returned invalid structured output"
            ) from exc


class _FakeLLM:
    """Typed persona discussion fixtures."""

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self._responses = responses or {}
        self.agent_calls: list[Sequence[BaseMessage]] = []
        self.agents = PersonaDiscussionAgents(
            scoring=_FixtureAgent(self, "score", PersonaScoreOutput),
            selection=_FixtureAgent(
                self,
                "select",
                PersonaSelectionOutput,
            ),
            moderator=_FixtureAgent(
                self,
                "moderator",
                ModeratorJudgmentOutput,
            ),
        )
        self.synthesis_agent = _FixtureAgent(
            self,
            "synthesis",
            PersonaSynthesisOutput,
        )

    def response(self, key: str) -> str:
        defaults = {
            "select": (
                '{"selected_persona_ids":'
                '["analyst_self","skeptic_self"],"reason":"test"}'
            ),
            "score": '{"note":"test note","score":0.6}',
            "moderator": (
                '{"converged":false,"emergent_persona":"none",'
                '"reason":"test"}'
            ),
            "synthesis": (
                '{"summary":"Discussion synthesis.","confidence":0.5}'
            ),
        }
        return self._responses.get(key, defaults[key])


@pytest.mark.parametrize(
    ("schema", "payload"),
    [
        (
            PersonaScoreOutput,
            {"note": "valid", "score": 0.5, "unknown": True},
        ),
        (
            PersonaScoreOutput,
            {"note": " ", "score": 0.5},
        ),
        (
            PersonaSelectionOutput,
            {
                "selected_persona_ids": ["a", "b", "c", "d", "e", "f"],
                "reason": "too many",
            },
        ),
        (
            PersonaSelectionOutput,
            {
                "selected_persona_ids": ["analyst_self"],
                "reason": " ",
            },
        ),
        (
            ModeratorJudgmentOutput,
            {
                "converged": False,
                "emergent_persona": "invented_self",
                "reason": "invalid",
            },
        ),
    ],
)
def test_discussion_output_models_fail_closed(
    schema: type[BaseModel],
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        schema.model_validate(payload)


def _make_candidate(
    body: str = "Test body",
    candidate_type: str = "question",
    confidence: float = 0.8,
    novelty: float = 0.8,
    urgency: float = 0.5,
    interruption_cost: float = 0.2,
) -> IdeaCandidate:
    return IdeaCandidate(
        id="c1",
        title="Test",
        body=body,
        candidate_type=candidate_type,  # type: ignore[arg-type]
        confidence=confidence,
        novelty=novelty,
        urgency=urgency,
        interruption_cost=interruption_cost,
        evidence_refs=(),
        suggested_thread_id=None,
        source_summary="",
        created_at="2024-01-01T00:00:00",
    )


# --- No-LLM fallback tests ---


def test_discuss_approves_strong_candidate() -> None:
    discussion = ProactivePersonaDiscussion(min_participants=2, max_participants=4)
    candidate = _make_candidate(confidence=0.9, novelty=0.9, interruption_cost=0.1)
    result = discussion.discuss(candidate)
    assert isinstance(result, PersonaCompetitionResult)
    assert result.approved is True
    assert result.scores
    assert result.reason.startswith("approved after ")


def test_select_personas_fallback_without_agents() -> None:
    personas = (ANALYST_PERSONA, SKEPTIC_PERSONA, BUILDER_PERSONA, HISTORIAN_PERSONA)
    discussion = ProactivePersonaDiscussion(personas=personas, min_participants=2, max_participants=3)
    selected = discussion._select_personas(_make_candidate())
    assert 2 <= len(selected) <= 3
    assert all(p.id != "synthesizer_self" for p in selected)


def test_blocking_veto_with_weak_support() -> None:
    discussion = ProactivePersonaDiscussion(
        personas=(SKEPTIC_PERSONA, ANALYST_PERSONA),
        min_participants=2,
        max_participants=2,
        blocking_threshold=0.5,
        override_threshold=0.9,
        composite_threshold=0.1,
    )
    candidate = _make_candidate(confidence=0.1, novelty=0.1, interruption_cost=0.9)
    result = discussion.discuss(candidate)
    # Without LLM, all scores are 0.5 (fallback). 0.5 is not below blocking_threshold=0.5,
    # so no blocking veto. Composite 0.5 >= 0.1, so approved.
    assert result.approved is True


def test_discuss_shares_context_across_rounds(monkeypatch: pytest.MonkeyPatch) -> None:
    discussion = ProactivePersonaDiscussion(
        personas=(ANALYST_PERSONA, SKEPTIC_PERSONA),
        min_participants=2,
        max_participants=2,
        max_turns=3,
        consensus_spread_threshold=0.0,
    )
    discussion._driver = _FakePersonaDriver()  # type: ignore[attr-defined]
    candidate = _make_candidate(body="A shared context should evolve during debate.")

    result = discussion.discuss(candidate)

    assert result.approved is True
    assert any(line.startswith("host:") for line in result.discussion_trace)
    assert any("moderator_self" in line for line in result.discussion_trace)
    assert any(line.startswith("turn-1:") for line in result.discussion_trace)
    assert any(line.startswith("turn-2:") for line in result.discussion_trace)
    assert any(line.startswith("turn-3:") for line in result.discussion_trace)
    assert any(line.startswith("turn-2:") and "turn-1:" in line for line in result.discussion_trace)
    assert any(line.startswith("turn-3:") and "turn-2:" in line for line in result.discussion_trace)


def test_discuss_spawns_emergent_temporary_persona(monkeypatch: pytest.MonkeyPatch) -> None:
    discussion = ProactivePersonaDiscussion(
        personas=(ANALYST_PERSONA, SKEPTIC_PERSONA, BUILDER_PERSONA),
        min_participants=2,
        max_participants=2,
        max_turns=2,
    )
    discussion._driver = _FakePersonaDriver()  # type: ignore[attr-defined]
    monkeypatch.setattr(
        discussion,
        "_moderator_judgment",
        _spawn_bridge_judgment,
    )
    candidate = _make_candidate(
        candidate_type="connection",
        confidence=0.9,
        novelty=0.9,
        interruption_cost=0.2,
    )

    result = discussion.discuss(candidate)

    assert result.approved is True
    assert result.emergent_persona_ids == ("bridge_self",)
    assert any("bridge_self" in line for line in result.discussion_trace)


# --- LLM-driven tests ---


def test_agent_backed_scoring_persona_node_uses_typed_output() -> None:
    fixture = _FakeLLM({
        "score": '{"note":"This is a strong idea.","score":0.85}',
    })
    node = AgentBackedScoringPersonaNode(fixture.agents.scoring)
    persona = PersonaDefinition(id="analyst_self", description="Decomposes questions.")
    result = node(persona, PersonaInput(user_message="Test candidate"))

    assert result.notes == ("This is a strong idea.",)
    assert result.confidence == 0.85


def test_agent_backed_scoring_persona_node_fallback_on_invalid_output(
    tmp_path: Path,
) -> None:
    fixture = _FakeLLM({"score": "not valid structured output"})
    node = AgentBackedScoringPersonaNode(
        fixture.agents.scoring,
        project_root=tmp_path,
    )
    persona = PersonaDefinition(id="analyst_self", description="Decomposes questions.")
    result = node(persona, PersonaInput(user_message="Test"))

    assert result.notes == ("analyst_self considered the topic.",)
    assert result.confidence == 0.5
    [event] = read_log_events(
        project_root=tmp_path,
        component="persona",
    )
    assert event.event == "persona_discussion_degraded"
    assert event.metadata == {"stage": "scoring"}


def test_agent_backed_scoring_persona_node_rejects_numeric_string(
    tmp_path: Path,
) -> None:
    fixture = _FakeLLM({
        "score": '{"note":"Looks strong.","score":"0.85"}',
    })
    node = AgentBackedScoringPersonaNode(
        fixture.agents.scoring,
        project_root=tmp_path,
    )
    persona = PersonaDefinition(id="analyst_self", description="Decomposes questions.")
    result = node(persona, PersonaInput(user_message="Test"))

    assert result.notes == ("analyst_self considered the topic.",)
    assert result.confidence == 0.5


def test_agent_backed_scoring_persona_node_rejects_overflow() -> None:
    fixture = _FakeLLM({
        "score": '{"note":"Overflow","score":1.5}',
    })
    node = AgentBackedScoringPersonaNode(fixture.agents.scoring)
    persona = PersonaDefinition(id="analyst_self", description="Decomposes questions.")
    result = node(persona, PersonaInput(user_message="Test"))

    assert result.confidence == 0.5


@pytest.mark.parametrize("error_type", [RuntimeError, ValueError])
def test_scoring_persona_propagates_untyped_agent_errors(
    error_type: type[Exception],
) -> None:
    expected = error_type("raw scoring implementation failure")

    class _UntypedFailureAgent:
        def invoke(
            self,
            messages: Sequence[BaseMessage],
        ) -> PersonaScoreOutput:
            raise expected

    node = AgentBackedScoringPersonaNode(_UntypedFailureAgent())

    with pytest.raises(error_type) as caught:
        node(ANALYST_PERSONA, PersonaInput(user_message="Review this"))
    assert caught.value is expected


def test_select_personas_uses_typed_agent_response() -> None:
    llm = _FakeLLM({
        "select": '{"selected_persona_ids": ["builder_self", "skeptic_self"], "reason": "needs action and critique"}',
    })
    discussion = ProactivePersonaDiscussion(
        personas=(ANALYST_PERSONA, SKEPTIC_PERSONA, BUILDER_PERSONA, HISTORIAN_PERSONA),
        agents=llm.agents,
        synthesis_agent=llm.synthesis_agent,
        min_participants=2,
        max_participants=3,
    )
    selected = discussion._select_personas(_make_candidate())
    assert len(selected) == 2
    assert selected[0].id == "builder_self"
    assert selected[1].id == "skeptic_self"


def test_select_personas_rejects_partially_malformed_selection(
    tmp_path: Path,
) -> None:
    llm = _FakeLLM({
        "select": '{"selected_persona_ids": ["builder_self", 7], "reason": "mixed"}',
    })
    discussion = ProactivePersonaDiscussion(
        personas=(ANALYST_PERSONA, SKEPTIC_PERSONA, BUILDER_PERSONA),
        agents=llm.agents,
        synthesis_agent=llm.synthesis_agent,
        min_participants=2,
        max_participants=2,
        project_root=tmp_path,
    )

    selected = discussion._select_personas(_make_candidate())

    assert selected == (ANALYST_PERSONA, SKEPTIC_PERSONA)
    [event] = read_log_events(
        project_root=tmp_path,
        component="persona",
    )
    assert event.event == "persona_discussion_degraded"
    assert event.metadata == {"stage": "selection"}


@pytest.mark.parametrize("error_type", [RuntimeError, ValueError])
def test_select_personas_propagates_untyped_agent_errors(
    error_type: type[Exception],
) -> None:
    fixture = _FakeLLM()
    expected = error_type("raw selection implementation failure")

    class _UntypedFailureAgent:
        def invoke(
            self,
            messages: Sequence[BaseMessage],
        ) -> PersonaSelectionOutput:
            raise expected

    agents = PersonaDiscussionAgents(
        scoring=fixture.agents.scoring,
        selection=_UntypedFailureAgent(),
        moderator=fixture.agents.moderator,
    )
    discussion = ProactivePersonaDiscussion(agents=agents)

    with pytest.raises(error_type) as caught:
        discussion._select_personas(_make_candidate())
    assert caught.value is expected


def test_moderator_judgment_detects_convergence() -> None:
    llm = _FakeLLM({"moderator": '{"converged": true, "emergent_persona": "none", "reason": "stable consensus"}'})
    discussion = ProactivePersonaDiscussion(
        agents=llm.agents,
        synthesis_agent=llm.synthesis_agent,
    )
    judgment = discussion._moderator_judgment(
        {"analyst_self": 0.8, "builder_self": 0.75},
        ["turn-1: discussion"],
        2,
    )
    assert judgment.converged is True
    assert judgment.emergent_persona == "none"


def test_moderator_judgment_rejects_string_boolean(
    tmp_path: Path,
) -> None:
    llm = _FakeLLM({
        "moderator": '{"converged": "true", "emergent_persona": "bridge_self", "reason": "invalid"}',
    })
    discussion = ProactivePersonaDiscussion(
        agents=llm.agents,
        synthesis_agent=llm.synthesis_agent,
        project_root=tmp_path,
    )

    judgment = discussion._moderator_judgment(
        {"analyst_self": 0.8, "builder_self": 0.75},
        ["turn-1: discussion"],
        2,
    )

    assert judgment == ModeratorJudgmentOutput(
        converged=False,
        emergent_persona="none",
        reason="fallback",
    )
    [event] = read_log_events(
        project_root=tmp_path,
        component="persona",
    )
    assert event.event == "persona_discussion_degraded"
    assert event.metadata == {"stage": "moderator"}


@pytest.mark.parametrize("error_type", [RuntimeError, ValueError])
def test_moderator_judgment_propagates_untyped_agent_errors(
    error_type: type[Exception],
) -> None:
    fixture = _FakeLLM()
    expected = error_type("raw moderator implementation failure")

    class _UntypedFailureAgent:
        def invoke(
            self,
            messages: Sequence[BaseMessage],
        ) -> ModeratorJudgmentOutput:
            raise expected

    agents = PersonaDiscussionAgents(
        scoring=fixture.agents.scoring,
        selection=fixture.agents.selection,
        moderator=_UntypedFailureAgent(),
    )
    discussion = ProactivePersonaDiscussion(agents=agents)

    with pytest.raises(error_type) as caught:
        discussion._moderator_judgment(
            {"analyst_self": 0.8},
            ["turn-1: discussion"],
            1,
        )
    assert caught.value is expected


def test_discussion_diagnostic_failure_does_not_replace_scoring_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class _BrokenScoringAgent:
        def invoke(
            self,
            messages: Sequence[BaseMessage],
        ) -> Never:
            raise AgentModelUnavailableError("scoring unavailable")

    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("diagnostic store unavailable")

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        fail_log,
    )
    node = AgentBackedScoringPersonaNode(
        _BrokenScoringAgent(),
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
    assert result.confidence == 0.5


def test_moderator_judgment_spawns_emergent_persona() -> None:
    llm = _FakeLLM({"moderator": '{"converged": false, "emergent_persona": "bridge_self", "reason": "needs bridge"}'})
    discussion = ProactivePersonaDiscussion(
        agents=llm.agents,
        synthesis_agent=llm.synthesis_agent,
    )
    judgment = discussion._moderator_judgment(
        {"analyst_self": 0.6, "skeptic_self": 0.4},
        ["turn-1: debate"],
        1,
    )
    assert judgment.converged is False
    assert judgment.emergent_persona == "bridge_self"


def test_discuss_with_llm_blocks_low_scores() -> None:
    llm = _FakeLLM({
        "select": '{"selected_persona_ids": ["analyst_self", "skeptic_self"], "reason": "test"}',
        "score": '{"note": "weak idea", "score": 0.2}',
        "moderator": '{"converged": true, "emergent_persona": "none", "reason": "test"}',
    })
    discussion = ProactivePersonaDiscussion(
        personas=(ANALYST_PERSONA, SKEPTIC_PERSONA),
        agents=llm.agents,
        synthesis_agent=llm.synthesis_agent,
        min_participants=2,
        max_participants=2,
    )
    candidate = _make_candidate()
    result = discussion.discuss(candidate)
    # score=0.2 < blocking_threshold=0.35, strong_support=0 < 2 → blocked
    assert result.approved is False
    assert result.blocking_vetos


def test_discuss_with_llm_approves_high_scores() -> None:
    llm = _FakeLLM({
        "select": '{"selected_persona_ids": ["analyst_self", "builder_self"], "reason": "test"}',
        "score": '{"note": "strong idea", "score": 0.8}',
        "moderator": '{"converged": true, "emergent_persona": "none", "reason": "test"}',
    })
    discussion = ProactivePersonaDiscussion(
        personas=(ANALYST_PERSONA, BUILDER_PERSONA),
        agents=llm.agents,
        synthesis_agent=llm.synthesis_agent,
        min_participants=2,
        max_participants=2,
    )
    candidate = _make_candidate()
    result = discussion.discuss(candidate)
    assert result.approved is True
    assert result.scores["analyst_self"] == 0.8
    assert result.scores["builder_self"] == 0.8


def test_proactive_persona_discussion_uses_llm_when_provided(monkeypatch: pytest.MonkeyPatch) -> None:
    personas = (
        PersonaDefinition(id="skeptic_self", description="Challenges assumptions."),
        PersonaDefinition(id="builder_self", description="Proposes steps."),
        PersonaDefinition(id="analyst_self", description="Decomposes questions."),
    )
    llm = _FakeLLM({
        "select": '{"selected_persona_ids": ["skeptic_self", "builder_self", "analyst_self"], "reason": "test"}',
        "score": '{"note": "good idea", "score": 0.7}',
        "moderator": '{"converged": true, "emergent_persona": "none", "reason": "test"}',
    })
    discussion = ProactivePersonaDiscussion(
        personas=personas,
        agents=llm.agents,
        synthesis_agent=llm.synthesis_agent,
        min_participants=3,
        max_participants=3,
    )
    monkeypatch.setattr(discussion, "_participants_for_turn", lambda selected, emergent: personas)  # type: ignore[arg-type]
    candidate = IdeaCandidate(
        id="c1",
        title="Test idea",
        body="A test idea for discussion.",
        candidate_type="question",
        confidence=0.8,
        novelty=0.8,
        urgency=0.5,
        interruption_cost=0.2,
        evidence_refs=(),
        suggested_thread_id=None,
        source_summary="",
        created_at="2024-01-01T00:00:00",
    )
    result = discussion.discuss(candidate)

    assert result.approved is True
    trace = result.discussion_trace
    assert any("skeptic_self" in entry for entry in trace)
    assert any("builder_self" in entry for entry in trace)
    assert any("analyst_self" in entry for entry in trace)


def test_proactive_persona_discussion_injects_language_preference() -> None:
    personas = (
        PersonaDefinition(id="skeptic_self", description="Challenges assumptions."),
        PersonaDefinition(id="builder_self", description="Proposes steps."),
        PersonaDefinition(id="analyst_self", description="Decomposes questions."),
    )
    llm = _FakeLLM({
        "select": '{"selected_persona_ids": ["skeptic_self", "builder_self", "analyst_self"], "reason": "test"}',
        "score": '{"note": "中文观点", "score": 0.7}',
        "moderator": '{"converged": true, "emergent_persona": "none", "reason": "test"}',
    })
    discussion = ProactivePersonaDiscussion(
        personas=personas,
        agents=llm.agents,
        synthesis_agent=llm.synthesis_agent,
        min_participants=3,
        max_participants=3,
        language_preference="zh-CN",
    )

    discussion.discuss(_make_candidate())

    prompts = "\n".join(
        call[0].text for call in llm.agent_calls
    )
    assert "Write the note in zh-CN" in prompts
    assert "Write the summary in zh-CN" in prompts


def test_llm_backed_persona_node_generates_distinct_notes() -> None:
    from nuself.persona.graph import AgentBackedPersonaNode
    from nuself.persona.definition import (
        PersonaContributionOutput,
        PersonaDefinition,
        PersonaInput,
    )

    class _ContributionAgent:
        def invoke(
            self,
            messages: Sequence[BaseMessage],
        ) -> PersonaContributionOutput:
            text = "\n".join(message.text for message in messages)
            if "skeptic_self" in text:
                note = "Skeptic challenges the core assumption here."
            elif "builder_self" in text:
                note = "Builder proposes three concrete steps to act on this."
            else:
                note = "Analyst breaks this into components and implications."
            return PersonaContributionOutput(
                note=note,
                questions=[],
                confidence=0.5,
            )

    node = AgentBackedPersonaNode(_ContributionAgent())

    analyst = PersonaDefinition(id="analyst_self", description="Decomposes questions.")
    skeptic = PersonaDefinition(id="skeptic_self", description="Challenges assumptions.")
    builder = PersonaDefinition(id="builder_self", description="Proposes steps.")

    inp = PersonaInput(user_message="Test candidate")

    a = node(analyst, inp)
    s = node(skeptic, inp)
    b = node(builder, inp)

    assert a.notes[0] == "Analyst breaks this into components and implications."
    assert s.notes[0] == "Skeptic challenges the core assumption here."
    assert b.notes[0] == "Builder proposes three concrete steps to act on this."
    assert a.notes[0] != s.notes[0]
    assert s.notes[0] != b.notes[0]


def test_llm_backed_synthesizer_node_produces_summary() -> None:
    from nuself.persona.graph import AgentBackedSynthesizerNode
    from nuself.persona.definition import (
        PersonaContribution,
        PersonaInput,
        PersonaSynthesisOutput,
        PersonaTurnState,
    )

    class _SynthesisAgent:
        def invoke(
            self,
            messages: Sequence[BaseMessage],
        ) -> PersonaSynthesisOutput:
            return PersonaSynthesisOutput(
                summary="Summary of the discussion.",
                confidence=0.5,
            )

    node = AgentBackedSynthesizerNode(_SynthesisAgent())

    state = PersonaTurnState(
        input=PersonaInput(user_message="test"),
        selected_personas=(),
        contributions=(
            PersonaContribution(persona_id="a", notes=("note a",)),
            PersonaContribution(persona_id="b", notes=("note b",)),
        ),
    )
    result = node(state)
    assert result is not None
    assert result.summary == "Summary of the discussion."
    assert result.source_personas == ("a", "b")


def _spawn_bridge_judgment(
    scores: dict[str, float],
    trace: list[str],
    turn: int,
) -> ModeratorJudgmentOutput:
    del scores, trace, turn
    return ModeratorJudgmentOutput(
        converged=False,
        emergent_persona="bridge_self",
        reason="test",
    )
