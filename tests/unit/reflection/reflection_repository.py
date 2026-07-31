"""Tests for ReflectionRepository."""

from __future__ import annotations

from pathlib import Path

import pytest

from nuself.config import runtime_paths
from nuself.reflection.repository import (
    ReflectionEntry,
    ReflectionEntryNotFound,
    ReflectionRepository,
)
from nuself.storage import get_default_backend


@pytest.fixture
def repo(tmp_path: Path) -> ReflectionRepository:
    return ReflectionRepository(runtime_paths(tmp_path), backend=get_default_backend(tmp_path))


def _sample_entry(index: int = 0) -> ReflectionEntry:
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
        discussion_approved=True,
        discussion_trace=("turn-1: analyst: good idea",),
        deep_link="nuself://conversation/reflections",
        created_at="2024-01-01T12:00:00+00:00",
        reviewed_at=None,
    )


def test_add_and_get(repo: ReflectionRepository) -> None:
    entry = _sample_entry()
    repo.add(entry)
    retrieved = repo.get(entry.id)
    assert retrieved.id == entry.id
    assert retrieved.title == entry.title


def test_get_missing(repo: ReflectionRepository) -> None:
    with pytest.raises(ReflectionEntryNotFound):
        repo.get("missing-id")


def test_list_all(repo: ReflectionRepository) -> None:
    repo.add(_sample_entry(0))
    repo.add(_sample_entry(1))
    entries = repo.list()
    assert len(entries) == 2


def test_list_filter_by_status(repo: ReflectionRepository) -> None:
    pending = _sample_entry(0)
    dismissed = _sample_entry(1)
    dismissed = dismissed.with_status("dismissed")
    repo.add(pending)
    repo.add(dismissed)
    assert len(repo.list(status="pending")) == 1
    assert len(repo.list(status="dismissed")) == 1
    assert len(repo.list(status="archived")) == 0


def test_dismiss(repo: ReflectionRepository) -> None:
    entry = _sample_entry()
    repo.add(entry)
    updated = repo.dismiss(entry.id)
    assert updated.status == "dismissed"
    assert updated.reviewed_at is not None
    retrieved = repo.get(entry.id)
    assert retrieved.status == "dismissed"


def test_archive(repo: ReflectionRepository) -> None:
    entry = _sample_entry()
    repo.add(entry)
    updated = repo.archive(entry.id)
    assert updated.status == "archived"
    assert updated.reviewed_at is not None
    retrieved = repo.get(entry.id)
    assert retrieved.status == "archived"


def test_update(repo: ReflectionRepository) -> None:
    entry = _sample_entry()
    repo.add(entry)
    updated = entry.with_status("dismissed")
    repo.update(updated)
    retrieved = repo.get(entry.id)
    assert retrieved.status == "dismissed"


def test_list_empty(repo: ReflectionRepository) -> None:
    assert repo.list() == []


def test_entry_to_wire_roundtrip() -> None:
    entry = _sample_entry()
    wire = entry.to_wire()
    restored = ReflectionEntry.from_wire(wire)
    assert restored == entry
