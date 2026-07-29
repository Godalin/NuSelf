# pyright: reportPrivateUsage=false
"""Tests for ReflectionScheduler and proactive idea generation."""

from __future__ import annotations

from collections.abc import Sequence
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Never

import pytest
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, ValidationError

from nuself.agent.errors import AgentInvalidOutputError, AgentModelUnavailableError
from nuself.config import ReflectionDiscussionConfig, ReflectionGateConfig, ReflectionModeratorConfig, ReflectionSchedulerConfig, ReflectionSettings
from nuself.domain.proactive import IdeaCandidate
from nuself.logs import read_log_events
from nuself.reflection import IdeaCandidateGenerator, ReflectionScheduler
from nuself.reflection.repository import ReflectionEntry
from nuself.reflection.scheduler import (
    CandidateListOutput,
    ReflectionScheduleStateError,
    RelevanceScoreOutput,
)


def _local_datetime(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    tz = datetime.now().astimezone().tzinfo
    return datetime(year, month, day, hour, minute, 0, tzinfo=tz)


def _reflection_settings(
    *,
    interval_seconds: int = 3600,
    cooldown_seconds: int = 300,
    quiet_start_hour: int = 22,
    quiet_end_hour: int = 7,
    daily_cap: int = 5,
    jitter_percent: int = 20,
    relevance_threshold: float = 0.5,
    persona_discussion_threshold: float = 0.7,
    max_discussion_rounds: int = 10,
    moderator_convergence_patience: int = 5,
) -> ReflectionSettings:
    return ReflectionSettings(
        scheduler=ReflectionSchedulerConfig(
            interval_seconds=interval_seconds,
            cooldown_seconds=cooldown_seconds,
            quiet_start_hour=quiet_start_hour,
            quiet_end_hour=quiet_end_hour,
            daily_cap=daily_cap,
            jitter_percent=jitter_percent,
        ),
        gate=ReflectionGateConfig(
            relevance_threshold=relevance_threshold,
            persona_discussion_threshold=persona_discussion_threshold,
        ),
        moderator=ReflectionModeratorConfig(
            max_discussion_rounds=max_discussion_rounds,
            moderator_convergence_patience=moderator_convergence_patience,
        ),
        discussion=ReflectionDiscussionConfig(),
    )


_DEFAULT_CANDIDATES: list[dict[str, object]] = [
    {
        "title": "Proactive insight about memory patterns",
        "body": (
            "Your recent memories suggest a recurring interest in systems "
            "thinking. Consider exploring how this connects to your current "
            "projects."
        ),
        "candidate_type": "connection",
        "confidence": 0.8,
        "novelty": 0.9,
        "urgency": 0.3,
        "interruption_cost": 0.1,
    }
]


class _CandidateAgent:
    def __init__(
        self,
        candidates: list[dict[str, object]] | None = None,
    ) -> None:
        self._candidates = (
            _DEFAULT_CANDIDATES
            if candidates is None
            else candidates
        )
        self.messages: list[Sequence[BaseMessage]] = []

    def invoke(
        self,
        messages: Sequence[BaseMessage],
    ) -> CandidateListOutput:
        self.messages.append(messages)
        try:
            return CandidateListOutput.model_validate(
                {"candidates": self._candidates}
            )
        except ValidationError as exc:
            raise AgentInvalidOutputError(
                "candidate agent returned invalid structured output"
            ) from exc


class _RelevanceAgent:
    def __init__(
        self,
        response: dict[str, object] | None = None,
    ) -> None:
        self._response = response or {
            "novelty": 0.9,
            "confidence": 0.8,
            "urgency": 0.3,
            "interruption_cost": 0.1,
            "composite": 0.8,
            "passes": True,
            "reason": "good idea",
        }
        self.messages: list[Sequence[BaseMessage]] = []

    def invoke(
        self,
        messages: Sequence[BaseMessage],
    ) -> RelevanceScoreOutput:
        self.messages.append(messages)
        try:
            return RelevanceScoreOutput.model_validate(self._response)
        except ValidationError as exc:
            raise AgentInvalidOutputError(
                "relevance agent returned invalid structured output"
            ) from exc


class _BrokenAgent:
    def invoke(self, messages: Sequence[BaseMessage]) -> Never:
        raise AgentModelUnavailableError("simulated LLM failure")


def _fake_structured_agent(
    schema: type[BaseModel],
    *,
    project_root: Path | None = None,
    component: str,
) -> object:
    if schema is CandidateListOutput:
        return _CandidateAgent()
    if schema is RelevanceScoreOutput:
        return _RelevanceAgent()
    raise AssertionError(f"unexpected schema: {schema.__name__}")


def _seed_memory(tmp_path: Path) -> None:
    """Seed one memory entry so IdeaCandidateGenerator has context."""
    from nuself.memory.repository import MemoryEntryRepository
    from nuself.domain.memory import MemoryEntry

    repo = MemoryEntryRepository(tmp_path)
    repo.save(MemoryEntry(
        id="m1", type="belief", title="Test belief",
        body="A test entry for proactive generation.",
        tags=[], source_refs=[], importance=0.5, review_state="reviewed",
        created_at="2024-01-01T00:00:00", updated_at="2024-01-01T00:00:00",
    ))


def _sample_reflection_entry(index: int = 0) -> ReflectionEntry:
    return ReflectionEntry(
        id=f"reflection-test-{index:03d}",
        title=f"Test idea {index}",
        body=f"Body {index}",
        candidate_type="question",
        confidence=0.8,
        novelty=0.9,
        urgency=0.3,
        interruption_cost=0.1,
        composite_score=0.7,
        status="pending",
        discussion_approved=None,
        discussion_trace=(),
        deep_link="nuself://thread/reflections",
        created_at=f"2024-01-01T12:00:0{index}+00:00",
        reviewed_at=None,
    )


@pytest.fixture
def scheduler(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ReflectionScheduler:
    # Create a minimal project structure
    (tmp_path / "private" / "runtime").mkdir(parents=True)
    (tmp_path / "private" / "logs").mkdir(parents=True)
    (tmp_path / "private" / "outbox").mkdir(parents=True)
    monkeypatch.setattr(
        "nuself.reflection.scheduler.default_structured_agent",
        _fake_structured_agent,
    )
    # Seed data so generator has context
    _seed_memory(tmp_path)
    config = _reflection_settings(
        interval_seconds=5,
        cooldown_seconds=0,
        daily_cap=50,
        jitter_percent=0,
        relevance_threshold=0.0,
        persona_discussion_threshold=1.0,
        max_discussion_rounds=2,
        moderator_convergence_patience=1,
    )
    return ReflectionScheduler(tmp_path, config=config)


# --- scheduling tests ---

def test_should_reflect_first_time(scheduler: ReflectionScheduler) -> None:
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert scheduler.should_reflect(now) is True


def test_should_reflect_respects_cooldown(scheduler: ReflectionScheduler) -> None:
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    scheduler._write_last_reflection(now)
    assert scheduler.should_reflect(now) is False


def test_should_reflect_respects_interval(scheduler: ReflectionScheduler) -> None:
    now = _local_datetime(2024, 1, 1, 12)
    scheduler._write_last_reflection(now)
    later = now.replace(minute=6)
    scheduler._config = _reflection_settings(
        interval_seconds=3600,
        cooldown_seconds=300,
        quiet_start_hour=22,
        quiet_end_hour=7,
        daily_cap=5,
        jitter_percent=20,
        relevance_threshold=0.5,
        persona_discussion_threshold=0.7,
        max_discussion_rounds=10,
        moderator_convergence_patience=5,
    )
    assert scheduler.should_reflect(later) is False
    assert scheduler.should_reflect(now.replace(hour=14)) is True


def test_should_reflect_respects_quiet_hours(scheduler: ReflectionScheduler) -> None:
    scheduler._config = _reflection_settings(
        interval_seconds=10,
        cooldown_seconds=0,
        quiet_start_hour=22,
        quiet_end_hour=7,
        daily_cap=100,
        jitter_percent=0,
        relevance_threshold=0.0,
        persona_discussion_threshold=1.0,
        max_discussion_rounds=2,
        moderator_convergence_patience=1,
    )
    night = _local_datetime(2024, 1, 1, 23)
    assert scheduler.should_reflect(night) is False


def test_should_reflect_outside_quiet_hours(scheduler: ReflectionScheduler) -> None:
    noon = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert scheduler.should_reflect(noon) is True


def test_should_reflect_wraparound_quiet_hours(scheduler: ReflectionScheduler) -> None:
    scheduler._config = _reflection_settings(
        interval_seconds=3600,
        cooldown_seconds=300,
        quiet_start_hour=22,
        quiet_end_hour=7,
        daily_cap=5,
        jitter_percent=20,
        relevance_threshold=0.5,
        persona_discussion_threshold=0.7,
        max_discussion_rounds=10,
        moderator_convergence_patience=5,
    )
    early = _local_datetime(2024, 1, 1, 6, 59)
    assert scheduler.should_reflect(early) is False
    boundary = _local_datetime(2024, 1, 1, 7)
    assert scheduler.should_reflect(boundary) is True


def test_should_reflect_respects_daily_cap(scheduler: ReflectionScheduler) -> None:
    now = _local_datetime(2024, 1, 1, 12)
    scheduler._config = _reflection_settings(
        interval_seconds=1,
        cooldown_seconds=0,
        quiet_start_hour=22,
        quiet_end_hour=7,
        daily_cap=1,
        jitter_percent=0,
    )
    scheduler._write_last_reflection(now)

    assert scheduler.should_reflect(now.replace(hour=13)) is False


# --- reflection pipeline tests ---

def test_reflect_creates_reflection_entry(scheduler: ReflectionScheduler) -> None:
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    result = scheduler.reflect(now)
    assert result is True
    entries = scheduler._reflection_repo.list()
    assert len(entries) == 1
    assert entries[0].title == "Proactive insight about memory patterns"
    assert entries[0].status == "pending"
    assert entries[0].id.startswith("reflection-candidate-")
    assert entries[0].deep_link is not None
    assert entries[0].deep_link.startswith("nuself://thread/reflections")


def test_reflect_result_survives_unavailable_auxiliary_logs(
    scheduler: ReflectionScheduler,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def drop_log(*args: object, **kwargs: object) -> None:
        del args, kwargs

    monkeypatch.setattr(
        "nuself.reflection.scheduler.write_reflection_audit",
        drop_log,
    )
    monkeypatch.setattr(
        "nuself.reflection.scheduler.write_persona_audit",
        drop_log,
    )

    assert scheduler.reflect(datetime(2024, 1, 1, 12, tzinfo=UTC)) is True
    assert len(scheduler._reflection_repo.list()) == 1


def test_reflect_trace_diagnostics_cannot_interrupt_persisted_cycle(
    scheduler: ReflectionScheduler,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_trace(*args: object, **kwargs: object) -> None:
        raise RuntimeError("trace unavailable")

    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("audit store unavailable")

    def drop_cycle_log(*args: object, **kwargs: object) -> None:
        del args, kwargs

    monkeypatch.setattr(
        "nuself.trace.service.TraceRecorder.record_reflection_created",
        fail_trace,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        fail_log,
    )
    monkeypatch.setattr(
        "nuself.reflection.scheduler.write_reflection_audit",
        drop_cycle_log,
    )
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

    with pytest.warns(
        RuntimeWarning,
        match="runtime/observability_sink_failed",
    ):
        result = scheduler.reflect(now)

    assert result is True
    assert len(scheduler._reflection_repo.list()) == 1
    assert scheduler._read_last_reflection() == now
    assert read_log_events(
        project_root=scheduler._project_root,
        component="reflection",
    ) == []


def test_organizer_diagnostics_cannot_interrupt_best_effort_boundary(
    scheduler: ReflectionScheduler,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_organizer(*args: object, **kwargs: object) -> None:
        raise RuntimeError("organizer unavailable")

    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("audit store unavailable")

    monkeypatch.setattr(
        "nuself.reflection.scheduler.ReflectionOrganizer.organize_pending",
        fail_organizer,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        fail_log,
    )

    with pytest.warns(
        RuntimeWarning,
        match="runtime/observability_sink_failed",
    ):
        scheduler._organize_pending_reflections()


def test_reflect_creates_multiple_reflection_entries(scheduler: ReflectionScheduler) -> None:
    import time
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    scheduler.reflect(now)
    # Clear last reflection so the second run is not blocked by novelty gate
    scheduler._last_reflection_path.unlink(missing_ok=True)
    time.sleep(0.01)  # ensure unique candidate id timestamp
    scheduler.reflect(now)
    entries = scheduler._reflection_repo.list()
    assert len(entries) == 2


def test_reflect_does_not_skip_when_pending_reflections_exist(scheduler: ReflectionScheduler) -> None:
    scheduler._config = _reflection_settings(
        relevance_threshold=0.0,
        persona_discussion_threshold=1.0,
    )
    scheduler._reflection_repo.add(_sample_reflection_entry())

    result = scheduler.reflect(datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC))

    assert result is True
    assert len(scheduler._reflection_repo.list(status="pending")) >= 1
    events = read_log_events(project_root=scheduler._project_root, component="reflection")
    assert not any(event.event == "cycle_pending_limit_reached" for event in events)


def test_reflect_auto_notify_creates_outbox_entry(scheduler: ReflectionScheduler) -> None:
    from nuself.config import ReflectionSettings
    scheduler._config = ReflectionSettings(
        scheduler=scheduler._config.scheduler,
        gate=scheduler._config.gate,
        moderator=scheduler._config.moderator,
        discussion=scheduler._config.discussion,
        auto_notify=True,
    )
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    result = scheduler.reflect(now)
    assert result is True
    # Reflection repo has the entry
    refl_entries = scheduler._reflection_repo.list()
    assert len(refl_entries) == 1
    # Outbox has a notify entry pointing to it
    outbox_entries = scheduler._outbox.list()
    assert len(outbox_entries) == 1
    assert outbox_entries[0].title.startswith("New reflection:")
    assert refl_entries[0].id in outbox_entries[0].body


def test_reflect_returns_false_when_schedule_blocked(scheduler: ReflectionScheduler) -> None:
    scheduler._config = _reflection_settings(
        interval_seconds=10,
        cooldown_seconds=0,
        quiet_start_hour=22,
        quiet_end_hour=7,
        daily_cap=100,
        jitter_percent=0,
        relevance_threshold=0.0,
        persona_discussion_threshold=1.0,
        max_discussion_rounds=2,
        moderator_convergence_patience=1,
    )
    now = _local_datetime(2024, 1, 1, 23)
    result = scheduler.reflect(now)
    assert result is False
    assert len(scheduler._reflection_repo.list()) == 0
    events = read_log_events(project_root=scheduler._project_root, component="reflection")
    assert events[-1].event == "schedule_blocked"
    assert events[-1].status == "skipped"
    assert events[-1].metadata == {"reason": "quiet_hours"}


# --- last reflection persistence ---

def test_read_last_reflection_missing_file(scheduler: ReflectionScheduler) -> None:
    assert scheduler._read_last_reflection() is None


def test_read_write_last_reflection_roundtrip(scheduler: ReflectionScheduler) -> None:
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    scheduler._write_last_reflection(now)
    loaded = scheduler._read_last_reflection()
    assert loaded is not None
    assert loaded.isoformat() == now.isoformat()
    record = json.loads(
        scheduler._last_reflection_path.read_text(encoding="utf-8")
    )
    assert record == {
        "daily_count": 1,
        "daily_date": "2024-01-01",
        "schema_version": 1,
        "timestamp": "2024-01-01T12:00:00Z",
    }
    assert list(scheduler._last_reflection_path.parent.glob("*.tmp")) == []


def test_read_last_reflection_corrupt_file(scheduler: ReflectionScheduler) -> None:
    scheduler._last_reflection_path.parent.mkdir(parents=True, exist_ok=True)
    scheduler._last_reflection_path.write_text("not-json", encoding="utf-8")
    with pytest.raises(
        ReflectionScheduleStateError,
        match="malformed or unsupported",
    ):
        scheduler._read_last_reflection()


def test_read_last_reflection_invalid_timestamp(scheduler: ReflectionScheduler) -> None:
    scheduler._last_reflection_path.parent.mkdir(parents=True, exist_ok=True)
    scheduler._last_reflection_path.write_text(
        json.dumps({"timestamp": "not-a-date"}), encoding="utf-8"
    )
    with pytest.raises(
        ReflectionScheduleStateError,
        match="malformed or unsupported",
    ):
        scheduler._read_last_reflection()


@pytest.mark.parametrize(
    "record",
    [
        {
            "schema_version": 1,
            "timestamp": "2024-01-01T12:00:00Z",
            "daily_count": True,
            "daily_date": "2024-01-01",
        },
        {
            "schema_version": 1,
            "timestamp": "2024-01-01T12:00:00Z",
            "daily_count": -1,
            "daily_date": "2024-01-01",
        },
        {
            "schema_version": 1,
            "timestamp": "2024-01-01T12:00:00Z",
            "daily_count": 1,
        },
        {
            "schema_version": 2,
            "timestamp": "2024-01-01T12:00:00Z",
            "daily_count": 1,
            "daily_date": "2024-01-01",
        },
    ],
)
def test_corrupt_schedule_state_fails_closed(
    scheduler: ReflectionScheduler,
    record: dict[str, object],
) -> None:
    scheduler._last_reflection_path.write_text(
        json.dumps(record),
        encoding="utf-8",
    )

    assert scheduler.should_reflect(
        datetime(2024, 1, 2, 12, tzinfo=UTC)
    ) is False
    events = read_log_events(
        project_root=scheduler._project_root,
        component="reflection",
    )
    assert events[-1].event == "schedule_state_corrupt"
    assert events[-1].status == "degraded"
    assert events[-1].metadata == {"record": "last_reflection.json"}
    assert "2024-01-01" not in (events[-1].error or "")


def test_corrupt_schedule_diagnostics_cannot_change_fail_closed_decision(
    scheduler: ReflectionScheduler,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("audit store unavailable")

    scheduler._last_reflection_path.write_text(
        '{"schema_version":1}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        fail_log,
    )

    with pytest.warns(
        RuntimeWarning,
        match="runtime/observability_sink_failed",
    ):
        result = scheduler.should_reflect(
            datetime(2024, 1, 2, 12, tzinfo=UTC)
        )

    assert result is False


def test_reflect_reports_corrupt_schedule_state_as_blocked(
    scheduler: ReflectionScheduler,
) -> None:
    scheduler._last_reflection_path.write_text(
        '{"schema_version":1}',
        encoding="utf-8",
    )

    assert scheduler.reflect(
        datetime(2024, 1, 2, 12, tzinfo=UTC)
    ) is False
    events = read_log_events(
        project_root=scheduler._project_root,
        component="reflection",
    )
    assert [event.event for event in events[-2:]] == [
        "schedule_state_corrupt",
        "schedule_blocked",
    ]
    assert events[-1].metadata == {"reason": "state_corrupt"}


def test_quiet_hours_non_wrapping_range() -> None:
    config = _reflection_settings(
        interval_seconds=3600,
        cooldown_seconds=300,
        quiet_start_hour=9,
        quiet_end_hour=17,
        daily_cap=5,
        jitter_percent=20,
        relevance_threshold=0.5,
        persona_discussion_threshold=0.7,
        max_discussion_rounds=10,
        moderator_convergence_patience=5,
    )
    scheduler = ReflectionScheduler.__new__(ReflectionScheduler)
    scheduler._config = config
    assert scheduler._in_quiet_hours(_local_datetime(2024, 1, 1, 12)) is True
    assert scheduler._in_quiet_hours(_local_datetime(2024, 1, 1, 8)) is False
    assert scheduler._in_quiet_hours(_local_datetime(2024, 1, 1, 18)) is False


# --- IdeaCandidateGenerator tests ---

def test_generator_returns_empty_with_no_data(tmp_path: Path) -> None:
    """No threads, no memory, no sources → no candidates."""
    gen = IdeaCandidateGenerator(tmp_path, agent=_CandidateAgent())
    candidates = gen.generate()
    assert candidates == []


def test_generator_produces_ideas_from_memory(tmp_path: Path) -> None:
    """Memory entries alone should be enough to generate ideas."""
    _seed_memory(tmp_path)

    gen = IdeaCandidateGenerator(tmp_path, agent=_CandidateAgent())
    candidates = gen.generate()
    assert len(candidates) == 1
    assert candidates[0].title == "Proactive insight about memory patterns"


def test_generator_produces_ideas_from_threads(tmp_path: Path) -> None:
    """Conversations alone should be enough to generate ideas."""
    from nuself.agent.chat import ThreadState, ThreadStore, ThreadMessage

    store = ThreadStore(tmp_path)
    state = ThreadState.empty("default")
    state.messages.append(ThreadMessage(role="user", content="What is consciousness?"))
    state = ThreadState(
        thread_id=state.thread_id,
        messages=state.messages,
        next_message_index=1,
    )
    store.save(state)

    gen = IdeaCandidateGenerator(tmp_path, agent=_CandidateAgent())
    candidates = gen.generate()
    assert len(candidates) == 1


def test_generator_llm_error_returns_empty(tmp_path: Path) -> None:
    """LLM failure → returns empty list (no broken fallback)."""
    _seed_memory(tmp_path)

    gen = IdeaCandidateGenerator(tmp_path, agent=_BrokenAgent())  # type: ignore[arg-type]
    candidates = gen.generate()
    assert candidates == []


def test_generator_invalid_structured_output_returns_empty(
    tmp_path: Path,
) -> None:
    class _InvalidCandidateAgent:
        def invoke(
            self,
            messages: Sequence[BaseMessage],
        ) -> CandidateListOutput:
            raise AgentInvalidOutputError("invalid structured output")

    _seed_memory(tmp_path)

    gen = IdeaCandidateGenerator(
        tmp_path,
        agent=_InvalidCandidateAgent(),
    )
    candidates = gen.generate()
    assert candidates == []


@pytest.mark.parametrize("error_type", [RuntimeError, ValueError])
def test_generator_propagates_untyped_agent_errors(
    tmp_path: Path,
    error_type: type[Exception],
) -> None:
    _seed_memory(tmp_path)
    expected = error_type("raw agent implementation failure")

    class _UntypedFailureAgent:
        def invoke(
            self,
            messages: Sequence[BaseMessage],
        ) -> CandidateListOutput:
            raise expected

    generator = IdeaCandidateGenerator(
        tmp_path,
        agent=_UntypedFailureAgent(),
    )

    with pytest.raises(error_type) as caught:
        generator.generate()
    assert caught.value is expected


@pytest.mark.parametrize(
    "candidates",
    [
        [
            {
                "title": "Valid-looking idea",
                "body": "This item is valid by itself.",
                "candidate_type": "question",
            },
            {
                "title": "Missing body",
                "candidate_type": "action",
            },
        ],
        [
            {
                "title": "Unknown type",
                "body": "Unknown types must not be coerced.",
                "candidate_type": "surprise",
            },
        ],
    ],
)
def test_generator_rejects_entire_malformed_candidate_batch(
    tmp_path: Path,
    candidates: list[dict[str, object]],
) -> None:
    _seed_memory(tmp_path)
    llm = _CandidateAgent(candidates=candidates)
    gen = IdeaCandidateGenerator(tmp_path, agent=llm)

    assert gen.generate() == []
    event = read_log_events(
        project_root=tmp_path,
        component="reflection",
    )[-1]
    assert event.event == "candidate_generation_failed"


def test_generator_parses_multiple_candidates(tmp_path: Path) -> None:
    """LLM returning multiple candidates → all parsed."""
    multi_agent = _CandidateAgent(candidates=[
        {"title": "Idea A", "body": "First idea", "candidate_type": "question", "confidence": 0.8, "novelty": 0.9, "urgency": 0.3, "interruption_cost": 0.1},
        {"title": "Idea B", "body": "Second idea", "candidate_type": "connection", "confidence": 0.7, "novelty": 0.8, "urgency": 0.5, "interruption_cost": 0.2},
    ])
    _seed_memory(tmp_path)

    gen = IdeaCandidateGenerator(tmp_path, agent=multi_agent)
    candidates = gen.generate()
    assert len(candidates) == 2
    assert candidates[0].title == "Idea A"
    assert candidates[1].title == "Idea B"


def test_generator_injects_language_instruction(tmp_path: Path) -> None:
    """Non-English language preference appends a language directive to the system prompt."""
    private_dir = tmp_path / "private"
    private_dir.mkdir(parents=True)
    (private_dir / "config.yaml").write_text(
        "chat:\n  language_preference: zh-CN\n",
        encoding="utf-8",
    )
    _seed_memory(tmp_path)

    agent = _CandidateAgent(candidates=[])
    gen = IdeaCandidateGenerator(tmp_path, agent=agent)
    gen.generate()
    assert len(agent.messages) == 1
    system_prompt = agent.messages[0][0].text
    assert "Respond in zh-CN" in system_prompt


# --- LLMRelevanceGate tests ---

def _make_candidate(
    body: str,
    title: str = "Test",
    confidence: float = 0.8,
    novelty: float = 0.8,
    urgency: float = 0.5,
    interruption_cost: float = 0.2,
) -> IdeaCandidate:
    return IdeaCandidate(
        id="c1",
        title=title,
        body=body,
        candidate_type="question",
        confidence=confidence,
        novelty=novelty,
        urgency=urgency,
        interruption_cost=interruption_cost,
        evidence_refs=(),
        suggested_thread_id=None,
        source_summary="",
        created_at="2024-01-01T00:00:00",
    )


def test_relevance_gate_allows_passing_candidate(tmp_path: Path) -> None:
    from nuself.reflection import LLMRelevanceGate

    gate = LLMRelevanceGate(tmp_path, agent=_RelevanceAgent())
    score = gate.score(_make_candidate("New insight about X"))
    assert score.passes is True
    assert score.composite == 0.8


def test_relevance_gate_rejects_failing_candidate(tmp_path: Path) -> None:
    from nuself.reflection import LLMRelevanceGate

    gate = LLMRelevanceGate(
        tmp_path,
        agent=_RelevanceAgent(response={
            "novelty": 0.1, "confidence": 0.1, "urgency": 0.1,
            "interruption_cost": 0.9, "composite": 0.1, "passes": False,
            "reason": "not relevant",
        }),
    )
    score = gate.score(_make_candidate("Boring idea"))
    assert score.passes is False
    assert score.reasons == ("not relevant",)


def test_relevance_gate_uses_llm_judgment_not_formula(tmp_path: Path) -> None:
    from nuself.reflection import LLMRelevanceGate

    # LLM says passes=True even if scores look low — judgment overrides formula
    gate = LLMRelevanceGate(
        tmp_path,
        agent=_RelevanceAgent(response={
            "novelty": 0.2, "confidence": 0.2, "urgency": 0.2,
            "interruption_cost": 0.2, "composite": 0.3, "passes": True,
            "reason": "contextually important",
        }),
    )
    score = gate.score(_make_candidate("Contextual"))
    assert score.passes is True
    assert score.reasons == ("contextually important",)


def test_relevance_gate_rejects_out_of_range_scores(
    tmp_path: Path,
) -> None:
    from nuself.reflection import LLMRelevanceGate

    gate = LLMRelevanceGate(
        tmp_path,
        agent=_RelevanceAgent(response={
            "novelty": 1.5, "confidence": -0.3, "urgency": 0.5,
            "interruption_cost": 0.5, "composite": 2.0, "passes": True,
            "reason": "clamped",
        }),
    )
    score = gate.score(_make_candidate("Overflow"))
    assert score.passes is False
    assert score.composite == 0.0
    assert score.reasons == ("llm_fallback",)


def test_relevance_gate_fallback_on_llm_failure(tmp_path: Path) -> None:
    from nuself.reflection import LLMRelevanceGate

    gate = LLMRelevanceGate(tmp_path, agent=_BrokenAgent())  # type: ignore[arg-type]
    candidate = _make_candidate("Will fail")
    score = gate.score(candidate)
    assert score.passes is False
    assert score.composite == 0.0
    assert score.reasons == ("llm_fallback",)
    assert score.novelty == candidate.novelty


def test_relevance_gate_fallback_on_invalid_structured_output(
    tmp_path: Path,
) -> None:
    from nuself.reflection import LLMRelevanceGate

    class _InvalidRelevanceAgent:
        def invoke(
            self,
            messages: Sequence[BaseMessage],
        ) -> RelevanceScoreOutput:
            raise AgentInvalidOutputError("invalid structured output")

    gate = LLMRelevanceGate(
        tmp_path,
        agent=_InvalidRelevanceAgent(),
    )
    score = gate.score(_make_candidate("Bad json"))
    assert score.passes is False
    assert score.reasons == ("llm_fallback",)


@pytest.mark.parametrize("error_type", [RuntimeError, ValueError])
def test_relevance_gate_propagates_untyped_agent_errors(
    tmp_path: Path,
    error_type: type[Exception],
) -> None:
    from nuself.reflection import LLMRelevanceGate

    expected = error_type("raw agent implementation failure")

    class _UntypedFailureAgent:
        def invoke(
            self,
            messages: Sequence[BaseMessage],
        ) -> RelevanceScoreOutput:
            raise expected

    gate = LLMRelevanceGate(tmp_path, agent=_UntypedFailureAgent())

    with pytest.raises(error_type) as caught:
        gate.score(_make_candidate("Will propagate"))
    assert caught.value is expected


def test_relevance_gate_fallback_on_missing_field(tmp_path: Path) -> None:
    from nuself.reflection import LLMRelevanceGate

    gate = LLMRelevanceGate(
        tmp_path,
        agent=_RelevanceAgent(response={"novelty": 0.5}),
    )
    score = gate.score(_make_candidate("Missing field"))
    assert score.passes is False
    assert score.reasons == ("llm_fallback",)


def test_relevance_gate_rejects_passes_from_string(tmp_path: Path) -> None:
    from nuself.reflection import LLMRelevanceGate

    gate = LLMRelevanceGate(
        tmp_path,
        agent=_RelevanceAgent(response={
            "novelty": 0.5,
            "confidence": 0.5,
            "urgency": 0.5,
            "interruption_cost": 0.5,
            "composite": 0.5,
            "passes": "true",
            "reason": "string true",
        }),
    )
    score = gate.score(_make_candidate("String true"))
    assert score.passes is False
    assert score.composite == 0.0
    assert score.reasons == ("llm_fallback",)


def test_relevance_gate_cooldown_uses_config(tmp_path: Path) -> None:
    from nuself.reflection import LLMRelevanceGate

    config = _reflection_settings(cooldown_seconds=600)
    gate = LLMRelevanceGate(tmp_path, config=config)
    # Write a recent last_reflection to trigger cooldown
    last_path = tmp_path / "private" / "runtime" / "last_reflection.json"
    last_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    last_path.write_text(json.dumps({
        "schema_version": 1,
        "timestamp": now.isoformat(),
        "daily_count": 1,
        "daily_date": now.astimezone().date().isoformat(),
    }))
    assert gate._cooldown_ok() is False


def test_relevance_gate_corrupt_state_keeps_cooldown_active(
    tmp_path: Path,
) -> None:
    from nuself.reflection import LLMRelevanceGate

    gate = LLMRelevanceGate(tmp_path, agent=_RelevanceAgent())
    last_path = tmp_path / "private" / "runtime" / "last_reflection.json"
    last_path.parent.mkdir(parents=True, exist_ok=True)
    last_path.write_text('{"timestamp":"not-a-date"}', encoding="utf-8")

    assert gate._cooldown_ok() is False
    events = read_log_events(project_root=tmp_path, component="reflection")
    assert events[-1].event == "schedule_state_corrupt"
    assert events[-1].status == "degraded"


def test_relevance_gate_corrupt_diagnostics_keep_cooldown_active(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nuself.reflection import LLMRelevanceGate

    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("audit store unavailable")

    gate = LLMRelevanceGate(tmp_path, agent=_RelevanceAgent())
    last_path = tmp_path / "private" / "runtime" / "last_reflection.json"
    last_path.parent.mkdir(parents=True, exist_ok=True)
    last_path.write_text('{"timestamp":"not-a-date"}', encoding="utf-8")
    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        fail_log,
    )

    with pytest.warns(
        RuntimeWarning,
        match="runtime/observability_sink_failed",
    ):
        result = gate._cooldown_ok()

    assert result is False


def test_relevance_gate_no_cooldown_when_no_last_reflection(tmp_path: Path) -> None:
    from nuself.reflection import LLMRelevanceGate

    gate = LLMRelevanceGate(tmp_path, agent=_RelevanceAgent())
    assert gate._cooldown_ok() is True
