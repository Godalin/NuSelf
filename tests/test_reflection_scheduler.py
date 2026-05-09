# pyright: reportPrivateUsage=false
"""Tests for ReflectionScheduler."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from nuself.reflection import ReflectionScheduler, ReflectionSettings


def empty_str_list() -> list[str]:
    return []


@pytest.fixture
def scheduler(tmp_path: Path) -> ReflectionScheduler:
    # Create a minimal project structure so runtime_paths works
    (tmp_path / "private" / "runtime").mkdir(parents=True)
    (tmp_path / "private" / "logs").mkdir(parents=True)
    (tmp_path / "private" / "outbox").mkdir(parents=True)
    return ReflectionScheduler(tmp_path)


def test_should_reflect_first_time(scheduler: ReflectionScheduler) -> None:
    # No previous reflection → interval passes by default
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert scheduler.should_reflect(now) is True


def test_should_reflect_respects_cooldown(scheduler: ReflectionScheduler) -> None:
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    scheduler.reflect(now)
    # Immediately after, cooldown should block
    assert scheduler.should_reflect(now) is False


def test_should_reflect_respects_interval(scheduler: ReflectionScheduler) -> None:
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    scheduler.reflect(now)
    # After cooldown but before interval
    later = now.replace(minute=6)
    scheduler._settings = ReflectionSettings(
        interval_seconds=3600,
        cooldown_seconds=300,
        quiet_start_hour=22,
        quiet_end_hour=7,
    )
    assert scheduler.should_reflect(later) is False


def test_should_reflect_respects_quiet_hours(scheduler: ReflectionScheduler) -> None:
    # 23:00 is inside quiet hours (22-07)
    night = datetime(2024, 1, 1, 23, 0, 0, tzinfo=UTC)
    assert scheduler.should_reflect(night) is False


def test_should_reflect_outside_quiet_hours(scheduler: ReflectionScheduler) -> None:
    # 12:00 is outside quiet hours (22-07)
    noon = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert scheduler.should_reflect(noon) is True


def test_should_reflect_wraparound_quiet_hours(scheduler: ReflectionScheduler) -> None:
    scheduler._settings = ReflectionSettings(
        interval_seconds=3600,
        cooldown_seconds=300,
        quiet_start_hour=22,
        quiet_end_hour=7,
    )
    # 06:59 is inside wraparound quiet hours
    early = datetime(2024, 1, 1, 6, 59, 0, tzinfo=UTC)
    assert scheduler.should_reflect(early) is False
    # 07:00 is exactly at boundary → outside
    boundary = datetime(2024, 1, 1, 7, 0, 0, tzinfo=UTC)
    assert scheduler.should_reflect(boundary) is True


def test_reflect_creates_outbox_entry(scheduler: ReflectionScheduler) -> None:
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    result = scheduler.reflect(now)
    assert result is True
    entries = scheduler._outbox.list()
    assert len(entries) == 1
    assert entries[0].title == "Daemon reflection"
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
    now = datetime(2024, 1, 1, 23, 0, 0, tzinfo=UTC)
    result = scheduler.reflect(now)
    assert result is False
    assert len(scheduler._outbox.list()) == 0


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
    import json
    scheduler._last_reflection_path.write_text(
        json.dumps({"timestamp": "not-a-date"}), encoding="utf-8"
    )
    assert scheduler._read_last_reflection() is None


def test_quiet_hours_non_wrapping_range() -> None:
    settings = ReflectionSettings(
        interval_seconds=3600,
        cooldown_seconds=300,
        quiet_start_hour=9,
        quiet_end_hour=17,
    )
    scheduler = ReflectionScheduler.__new__(ReflectionScheduler)
    scheduler._settings = settings
    # Inside quiet hours
    assert scheduler._in_quiet_hours(datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)) is True
    # Outside quiet hours
    assert scheduler._in_quiet_hours(datetime(2024, 1, 1, 8, 0, 0, tzinfo=UTC)) is False
    assert scheduler._in_quiet_hours(datetime(2024, 1, 1, 18, 0, 0, tzinfo=UTC)) is False


def test_idea_candidate_generator_falls_back_when_no_threads(tmp_path: Path) -> None:
    from nuself.reflection import IdeaCandidateGenerator

    gen = IdeaCandidateGenerator(tmp_path)
    assert gen.generate() == "Time for a self-reflection cycle."


def test_idea_candidate_generator_uses_latest_user_message(tmp_path: Path) -> None:
    from nuself.agent.chat import ThreadState, ThreadStore, ThreadMessage
    from nuself.reflection import IdeaCandidateGenerator

    store = ThreadStore(tmp_path)
    state = ThreadState.empty("default")
    state.messages.append(ThreadMessage(role="user", content="What is the meaning of life?"))
    store.save(state)

    gen = IdeaCandidateGenerator(tmp_path)
    body = gen.generate()
    assert body.startswith("Consider:")
    assert "meaning of life" in body


def test_relevance_gate_allows_first_fallback(tmp_path: Path) -> None:
    from nuself.reflection import RelevanceGate

    gate = RelevanceGate(tmp_path)
    assert gate.passes("Time for a self-reflection cycle.") is True


def test_relevance_gate_rejects_duplicate_fallback(tmp_path: Path) -> None:
    from nuself.reflection import RelevanceGate
    import json

    gate = RelevanceGate(tmp_path)
    last_path = tmp_path / "private" / "runtime" / "last_reflection.json"
    last_path.parent.mkdir(parents=True, exist_ok=True)
    last_path.write_text(json.dumps({"timestamp": "2024-01-01T00:00:00", "body": "Time for a self-reflection cycle."}))
    assert gate.passes("Time for a self-reflection cycle.") is False


def test_relevance_gate_allows_new_candidate(tmp_path: Path) -> None:
    from nuself.reflection import RelevanceGate
    import json

    gate = RelevanceGate(tmp_path)
    last_path = tmp_path / "private" / "runtime" / "last_reflection.json"
    last_path.parent.mkdir(parents=True, exist_ok=True)
    last_path.write_text(json.dumps({"timestamp": "2024-01-01T00:00:00", "body": "Consider: old topic"}))
    assert gate.passes("Consider: new topic") is True


def test_relevance_gate_rejects_duplicate_candidate(tmp_path: Path) -> None:
    from nuself.reflection import RelevanceGate
    import json

    gate = RelevanceGate(tmp_path)
    last_path = tmp_path / "private" / "runtime" / "last_reflection.json"
    last_path.parent.mkdir(parents=True, exist_ok=True)
    last_path.write_text(json.dumps({"timestamp": "2024-01-01T00:00:00", "body": "Consider: same topic"}))
    assert gate.passes("Consider: same topic") is False
