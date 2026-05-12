# pyright: reportPrivateUsage=false
"""Tests for ReflectionScheduler and proactive idea generation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nuself.config_system import ReflectionGateConfig, ReflectionModeratorConfig, ReflectionSchedulerConfig, ReflectionSettings
from nuself.domain.proactive import IdeaCandidate
from nuself.reflection import IdeaCandidateGenerator, ReflectionScheduler


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
    )


class _FakeLLM:
    """Deterministic LLM that returns a valid candidates JSON."""

    def __init__(self, candidates: list[dict[str, object]] | None = None) -> None:
        self._candidates = candidates or [
            {
                "title": "Proactive insight about memory patterns",
                "body": "Your recent memories suggest a recurring interest in systems thinking. Consider exploring how this connects to your current projects.",
                "candidate_type": "connection",
                "confidence": 0.8,
                "novelty": 0.9,
                "urgency": 0.3,
                "interruption_cost": 0.1,
            }
        ]

    def complete(self, messages: object) -> str:
        return json.dumps({"candidates": self._candidates})


class _BrokenLLM:
    def complete(self, messages: object) -> str:
        raise RuntimeError("simulated LLM failure")


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


@pytest.fixture
def scheduler(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ReflectionScheduler:
    # Create a minimal project structure
    (tmp_path / "private" / "runtime").mkdir(parents=True)
    (tmp_path / "private" / "logs").mkdir(parents=True)
    (tmp_path / "private" / "outbox").mkdir(parents=True)
    # Monkeypatch default_llm so IdeaCandidateGenerator gets a fake LLM
    monkeypatch.setattr(  # type: ignore[reportUnknownArgumentType]
        "nuself.llm.default_llm", lambda root: _FakeLLM()  # type: ignore[reportUnknownLambdaType]
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
    assert scheduler.should_reflect(now) is True


def test_should_reflect_respects_interval(scheduler: ReflectionScheduler) -> None:
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
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
    assert scheduler.should_reflect(later) is True


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
    night = datetime(2024, 1, 1, 23, 0, 0, tzinfo=UTC)
    assert scheduler.should_reflect(night) is True


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
    early = datetime(2024, 1, 1, 6, 59, 0, tzinfo=UTC)
    assert scheduler.should_reflect(early) is True
    boundary = datetime(2024, 1, 1, 7, 0, 0, tzinfo=UTC)
    assert scheduler.should_reflect(boundary) is True


# --- reflection pipeline tests ---

def test_reflect_creates_outbox_entry(scheduler: ReflectionScheduler) -> None:
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    result = scheduler.reflect(now)
    assert result is True
    entries = scheduler._outbox.list()
    assert len(entries) == 1
    assert entries[0].title == "Proactive insight about memory patterns"
    assert entries[0].status == "pending"
    assert entries[0].idempotency_key == "reflection-2024-01-01"
    assert entries[0].deep_link is not None
    assert entries[0].deep_link.startswith("nuself://thread/reflections")


def test_reflect_idempotent_per_day(scheduler: ReflectionScheduler) -> None:
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    scheduler.reflect(now)
    scheduler.reflect(now)
    entries = scheduler._outbox.list()
    assert len(entries) == 1


def test_reflect_returns_false_when_blocked(scheduler: ReflectionScheduler) -> None:
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
    now = datetime(2024, 1, 1, 23, 0, 0, tzinfo=UTC)
    result = scheduler.reflect(now)
    assert result is True
    assert len(scheduler._outbox.list()) == 1


# --- last reflection persistence ---

def test_read_last_reflection_missing_file(scheduler: ReflectionScheduler) -> None:
    assert scheduler._read_last_reflection() is None


def test_read_write_last_reflection_roundtrip(scheduler: ReflectionScheduler) -> None:
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    scheduler._write_last_reflection(now)
    loaded = scheduler._read_last_reflection()
    assert loaded is not None
    assert loaded.isoformat() == now.isoformat()


def test_read_last_reflection_corrupt_file(scheduler: ReflectionScheduler) -> None:
    scheduler._last_reflection_path.parent.mkdir(parents=True, exist_ok=True)
    scheduler._last_reflection_path.write_text("not-json", encoding="utf-8")
    assert scheduler._read_last_reflection() is None


def test_read_last_reflection_invalid_timestamp(scheduler: ReflectionScheduler) -> None:
    scheduler._last_reflection_path.parent.mkdir(parents=True, exist_ok=True)
    scheduler._last_reflection_path.write_text(
        json.dumps({"timestamp": "not-a-date"}), encoding="utf-8"
    )
    assert scheduler._read_last_reflection() is None


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
    assert scheduler._in_quiet_hours(datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)) is True
    assert scheduler._in_quiet_hours(datetime(2024, 1, 1, 8, 0, 0, tzinfo=UTC)) is False
    assert scheduler._in_quiet_hours(datetime(2024, 1, 1, 18, 0, 0, tzinfo=UTC)) is False


# --- IdeaCandidateGenerator tests ---

def test_generator_returns_empty_with_no_data(tmp_path: Path) -> None:
    """No threads, no memory, no sources → no candidates."""
    gen = IdeaCandidateGenerator(tmp_path, llm=_FakeLLM())
    candidates = gen.generate()
    assert candidates == []


def test_generator_produces_ideas_from_memory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Memory entries alone should be enough to generate ideas."""
    # Monkeypatch default_llm so IdeaCandidateGenerator gets a fake LLM
    monkeypatch.setattr(  # type: ignore[reportUnknownArgumentType]
        "nuself.llm.default_llm", lambda root: _FakeLLM()  # type: ignore[reportUnknownLambdaType]
    )
    _seed_memory(tmp_path)

    gen = IdeaCandidateGenerator(tmp_path, llm=_FakeLLM())
    candidates = gen.generate()
    assert len(candidates) == 1
    assert candidates[0].title == "Proactive insight about memory patterns"


def test_generator_produces_ideas_from_threads(tmp_path: Path) -> None:
    """Conversations alone should be enough to generate ideas."""
    from nuself.agent.chat import ThreadState, ThreadStore, ThreadMessage

    store = ThreadStore(tmp_path)
    state = ThreadState.empty("default")
    state.messages.append(ThreadMessage(role="user", content="What is consciousness?"))
    store.save(state)

    gen = IdeaCandidateGenerator(tmp_path, llm=_FakeLLM())
    candidates = gen.generate()
    assert len(candidates) == 1


def test_generator_llm_error_returns_empty(tmp_path: Path) -> None:
    """LLM failure → returns empty list (no broken fallback)."""
    _seed_memory(tmp_path)

    gen = IdeaCandidateGenerator(tmp_path, llm=_BrokenLLM())  # type: ignore[arg-type]
    candidates = gen.generate()
    assert candidates == []


def test_generator_llm_bad_json_returns_empty(tmp_path: Path) -> None:
    """LLM returns non-JSON → returns empty list."""
    class _BadJSONLLM:
        def complete(self, messages: object) -> str:
            return "I think you should consider..."

    _seed_memory(tmp_path)

    gen = IdeaCandidateGenerator(tmp_path, llm=_BadJSONLLM())  # type: ignore[arg-type]
    candidates = gen.generate()
    assert candidates == []


def test_generator_parses_multiple_candidates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM returning multiple candidates → all parsed."""
    multi_llm = _FakeLLM(candidates=[
        {"title": "Idea A", "body": "First idea", "candidate_type": "question", "confidence": 0.8, "novelty": 0.9, "urgency": 0.3, "interruption_cost": 0.1},
        {"title": "Idea B", "body": "Second idea", "candidate_type": "connection", "confidence": 0.7, "novelty": 0.8, "urgency": 0.5, "interruption_cost": 0.2},
    ])
    monkeypatch.setattr("nuself.llm.default_llm", lambda root: multi_llm)  # type: ignore[reportUnknownArgumentType,reportUnknownLambdaType]
    _seed_memory(tmp_path)

    gen = IdeaCandidateGenerator(tmp_path, llm=multi_llm)
    candidates = gen.generate()
    assert len(candidates) == 2
    assert candidates[0].title == "Idea A"
    assert candidates[1].title == "Idea B"


# --- RelevanceGate tests ---

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


def test_relevance_gate_allows_first_candidate(tmp_path: Path) -> None:
    from nuself.reflection import RelevanceGate

    gate = RelevanceGate(tmp_path)
    assert gate.passes(_make_candidate("New insight about X")) is True


def test_relevance_gate_rejects_duplicate_title(tmp_path: Path) -> None:
    from nuself.reflection import RelevanceGate

    gate = RelevanceGate(tmp_path)
    last_path = tmp_path / "private" / "runtime" / "last_reflection.json"
    last_path.parent.mkdir(parents=True, exist_ok=True)
    last_path.write_text(json.dumps({"timestamp": "2024-01-01T00:00:00", "title": "Same Title", "body": "Some body"}))
    assert gate.passes(_make_candidate("Different body", title="Same Title")) is False


def test_relevance_gate_allows_different_title(tmp_path: Path) -> None:
    from nuself.reflection import RelevanceGate

    gate = RelevanceGate(tmp_path)
    last_path = tmp_path / "private" / "runtime" / "last_reflection.json"
    last_path.parent.mkdir(parents=True, exist_ok=True)
    last_path.write_text(json.dumps({"timestamp": "2024-01-01T00:00:00", "title": "Old topic", "body": "Old body"}))
    assert gate.passes(_make_candidate("New body", title="New topic")) is True


def test_relevance_gate_reduces_novelty_on_body_overlap(tmp_path: Path) -> None:
    from nuself.reflection import RelevanceGate

    gate = RelevanceGate(tmp_path)
    last_path = tmp_path / "private" / "runtime" / "last_reflection.json"
    last_path.parent.mkdir(parents=True, exist_ok=True)
    last_path.write_text(json.dumps({"timestamp": "2024-01-01T00:00:00", "title": "Old", "body": "This is the full body text"}))
    score = gate.score(_make_candidate("full body text", title="Different"))
    assert score.novelty == 0.5  # partial overlap


def test_relevance_gate_uses_config_threshold(tmp_path: Path) -> None:
    from nuself.reflection import RelevanceGate

    config = _reflection_settings(
        interval_seconds=3600, cooldown_seconds=300,
        quiet_start_hour=22, quiet_end_hour=7,
        daily_cap=5, jitter_percent=20,
        relevance_threshold=0.9,
        persona_discussion_threshold=0.7,
        max_discussion_rounds=10, moderator_convergence_patience=5,
    )
    gate = RelevanceGate(tmp_path, config=config)
    score = gate.score(_make_candidate("Moderate", confidence=0.5, urgency=0.5, interruption_cost=0.2))
    assert score.passes is False


def test_relevance_gate_scores_high_urgency_low_interruption(tmp_path: Path) -> None:
    from nuself.reflection import RelevanceGate

    gate = RelevanceGate(tmp_path)
    score = gate.score(_make_candidate("Important idea", urgency=0.9, interruption_cost=0.1))
    assert score.passes is True
    assert score.urgency == 0.9
    assert score.interruption_cost == 0.1
    assert "high_urgency" in score.reasons


def test_relevance_gate_blocks_high_interruption_low_urgency(tmp_path: Path) -> None:
    from nuself.reflection import RelevanceGate

    gate = RelevanceGate(tmp_path)
    score = gate.score(_make_candidate("Interrupt", urgency=0.2, interruption_cost=0.9))
    assert score.passes is False
    assert "high_interruption_cost" in score.reasons


def test_relevance_gate_composite_threshold(tmp_path: Path) -> None:
    from nuself.reflection import RelevanceGate

    gate = RelevanceGate(tmp_path)
    score = gate.score(_make_candidate("Weak", confidence=0.1, novelty=0.1, urgency=0.1, interruption_cost=0.1))
    assert score.passes is False
    assert score.composite < 0.5
