"""Tests for reason repository."""

from __future__ import annotations

from pathlib import Path

from nuself.reason.domain import ReasoningStep, ReasoningThread
from nuself.reason.repository import ReasonNotFound, ReasonRepository


def test_save_and_get_thread(tmp_path: Path) -> None:
    repo = ReasonRepository(tmp_path)
    t = ReasoningThread(topic="What is the meaning of life?")
    saved = repo.save_thread(t)
    loaded = repo.get_thread(t.id)
    assert loaded == saved
    assert loaded.topic == "What is the meaning of life?"


def test_get_missing_thread_raises(tmp_path: Path) -> None:
    repo = ReasonRepository(tmp_path)
    try:
        repo.get_thread("nonexistent")
        assert False, "expected ReasonNotFound"
    except ReasonNotFound:
        pass


def test_list_threads(tmp_path: Path) -> None:
    repo = ReasonRepository(tmp_path)
    t1 = ReasoningThread(topic="Question 1")
    t2 = ReasoningThread(topic="Question 2", status="paused")
    t3 = ReasoningThread(topic="Question 3", status="resolved")
    repo.save_thread(t1)
    repo.save_thread(t2)
    repo.save_thread(t3)

    all_threads = repo.list_threads(status="all")
    assert len(all_threads) == 3

    default = repo.list_threads()
    assert len(default) == 3
    assert default[0].id == t1.id
    assert default[1].id == t2.id
    assert default[2].id == t3.id

    active = repo.list_threads(status="active")
    assert len(active) == 1
    assert active[0].id == t1.id

    paused = repo.list_threads(status="paused")
    assert len(paused) == 1

    resolved = repo.list_threads(status="resolved")
    assert len(resolved) == 1


def test_resolve_thread_by_id(tmp_path: Path) -> None:
    repo = ReasonRepository(tmp_path)
    t = ReasoningThread(topic="Test")
    repo.save_thread(t)
    resolved = repo.resolve_thread(t.id)
    assert resolved.id == t.id


def test_resolve_thread_by_numeric_handle(tmp_path: Path) -> None:
    repo = ReasonRepository(tmp_path)
    t1 = ReasoningThread(topic="First")
    t2 = ReasoningThread(topic="Second")
    repo.save_thread(t1)
    repo.save_thread(t2)
    resolved = repo.resolve_thread("1")
    assert resolved.id == t2.id


def test_save_and_list_steps(tmp_path: Path) -> None:
    repo = ReasonRepository(tmp_path)
    t = ReasoningThread(topic="Test")
    repo.save_thread(t)
    s1 = ReasoningStep(thread_id=t.id, summary="Step 1")
    s2 = ReasoningStep(thread_id=t.id, summary="Step 2")
    repo.save_step(s1)
    repo.save_step(s2)

    steps = repo.list_steps(t.id)
    assert len(steps) == 2


def test_get_step(tmp_path: Path) -> None:
    repo = ReasonRepository(tmp_path)
    t = ReasoningThread(topic="Test")
    repo.save_thread(t)
    s = ReasoningStep(thread_id=t.id, summary="Step")
    repo.save_step(s)
    loaded = repo.get_step(s.id)
    assert loaded.id == s.id


def test_list_empty_threads(tmp_path: Path) -> None:
    repo = ReasonRepository(tmp_path)
    assert repo.list_threads() == []


def test_list_empty_steps(tmp_path: Path) -> None:
    repo = ReasonRepository(tmp_path)
    assert repo.list_steps("reason-nonexistent") == []


def test_reindex(tmp_path: Path) -> None:
    repo = ReasonRepository(tmp_path)
    t = ReasoningThread(topic="Test")
    repo.save_thread(t)
    s = ReasoningStep(thread_id=t.id, summary="Step")
    repo.save_step(s)
    index_path = repo.reindex()
    assert index_path.exists()
