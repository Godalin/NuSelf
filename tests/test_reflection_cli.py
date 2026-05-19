# pyright: reportPrivateUsage=false
"""Tests for nuself reflection CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nuself.reflection.repository import ReflectionEntry, ReflectionRepository


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    (tmp_path / "private" / "runtime").mkdir(parents=True)
    (tmp_path / "private" / "logs").mkdir(parents=True)
    (tmp_path / "private" / "outbox").mkdir(parents=True)
    (tmp_path / "private" / "reflections").mkdir(parents=True)
    return tmp_path


def _seed_reflection_entries(project_root: Path, count: int = 3) -> list[ReflectionEntry]:
    repo = ReflectionRepository(project_root)
    entries: list[ReflectionEntry] = []
    for i in range(count):
        entry = ReflectionEntry(
            id=f"reflection-test-{i:03d}",
            title=f"Test idea {i}",
            body=f"Body for idea {i}",
            candidate_type="question" if i % 2 == 0 else "connection",
            confidence=0.7 + i * 0.05,
            novelty=0.8,
            urgency=0.3,
            interruption_cost=0.1,
            composite_score=0.6 + i * 0.1,
            status="pending" if i < 2 else "dismissed",
            discussion_approved=i % 2 == 0,
            discussion_trace=(f"turn-1: analyst scores 0.{8 + i}",),
            deep_link="nuself://thread/reflections",
            created_at=f"2024-01-0{i + 1}T12:00:00+00:00",
            reviewed_at=None,
        )
        repo.add(entry)
        entries.append(entry)
    return entries


def test_reflection_list_empty(project_root: Path) -> None:
    from nuself.cli import handle_reflection_list
    import argparse

    args = argparse.Namespace(project_root=project_root, status=None, as_json=False)
    assert handle_reflection_list(args) == 0


def test_reflection_list_with_entries(project_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from nuself.cli import handle_reflection_list
    import argparse

    entries = _seed_reflection_entries(project_root, 3)
    args = argparse.Namespace(project_root=project_root, status=None, as_json=False)
    assert handle_reflection_list(args) == 0
    output = capsys.readouterr().out
    assert "Test idea 0" in output
    assert "Test idea 1" in output
    assert "status=[pending]" in output
    assert "status=[dismissed]" in output
    assert "[0] [reflection]" in output
    assert "\n  Test idea 0\n" in output
    assert entries[0].id not in output
    assert entries[1].id not in output


def test_reflection_list_filters_by_status(project_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from nuself.cli import handle_reflection_list
    import argparse

    _seed_reflection_entries(project_root, 3)
    args = argparse.Namespace(project_root=project_root, status="pending", as_json=False)
    assert handle_reflection_list(args) == 0
    output = capsys.readouterr().out
    assert "Test idea 0" in output
    assert "Test idea 1" in output
    assert "Test idea 2" not in output  # dismissed


def test_reflection_list_json(project_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from nuself.cli import handle_reflection_list
    import argparse

    _seed_reflection_entries(project_root, 2)
    args = argparse.Namespace(project_root=project_root, status=None, as_json=True)
    assert handle_reflection_list(args) == 0
    output = capsys.readouterr().out
    lines = [line for line in output.strip().splitlines() if line]
    assert len(lines) == 2
    for line in lines:
        parsed = json.loads(line)
        assert "id" in parsed
        assert "title" in parsed


def test_reflection_show_by_id(project_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from nuself.cli import handle_reflection_show
    import argparse

    entries = _seed_reflection_entries(project_root, 3)
    args = argparse.Namespace(project_root=project_root, entry_id=entries[0].id, by_index=False, as_json=False)
    assert handle_reflection_show(args) == 0
    output = capsys.readouterr().out
    assert entries[0].title in output
    assert "[discussion]" in output


def test_reflection_show_by_index(project_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from nuself.cli import handle_reflection_show
    import argparse

    _seed_reflection_entries(project_root, 3)
    args = argparse.Namespace(project_root=project_root, entry_id="0", by_index=True, as_json=False)
    assert handle_reflection_show(args) == 0
    output = capsys.readouterr().out
    assert "Test idea 2" in output  # most recent (reverse order)


def test_reflection_show_json(project_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from nuself.cli import handle_reflection_show
    import argparse

    entries = _seed_reflection_entries(project_root, 1)
    args = argparse.Namespace(project_root=project_root, entry_id=entries[0].id, by_index=False, as_json=True)
    assert handle_reflection_show(args) == 0
    output = capsys.readouterr().out
    parsed = json.loads(output.strip())
    assert parsed["id"] == entries[0].id


def test_reflection_show_invalid_index(project_root: Path) -> None:
    from nuself.cli import handle_reflection_show
    import argparse

    _seed_reflection_entries(project_root, 2)
    args = argparse.Namespace(project_root=project_root, entry_id="99", by_index=True, as_json=False)
    assert handle_reflection_show(args) == 1


def test_reflection_show_empty(project_root: Path) -> None:
    from nuself.cli import handle_reflection_show
    import argparse

    args = argparse.Namespace(project_root=project_root, entry_id="0", by_index=True, as_json=False)
    assert handle_reflection_show(args) == 1


def test_reflection_dismiss(project_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from nuself.cli import handle_reflection_dismiss
    import argparse

    entries = _seed_reflection_entries(project_root, 2)
    args = argparse.Namespace(project_root=project_root, entry_id=entries[0].id, by_index=False)
    assert handle_reflection_dismiss(args) == 0
    output = capsys.readouterr().out
    assert f"Dismissed: {entries[0].id}" in output
    repo = ReflectionRepository(project_root)
    assert repo.get(entries[0].id).status == "dismissed"


def test_reflection_dismiss_by_index(project_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from nuself.cli import handle_reflection_dismiss
    import argparse

    _seed_reflection_entries(project_root, 2)
    args = argparse.Namespace(project_root=project_root, entry_id="0", by_index=True)
    assert handle_reflection_dismiss(args) == 0
    output = capsys.readouterr().out
    assert "Dismissed:" in output


def test_reflection_archive(project_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from nuself.cli import handle_reflection_archive
    import argparse

    entries = _seed_reflection_entries(project_root, 2)
    args = argparse.Namespace(project_root=project_root, entry_id=entries[0].id, by_index=False)
    assert handle_reflection_archive(args) == 0
    output = capsys.readouterr().out
    assert f"Archived: {entries[0].id}" in output
    repo = ReflectionRepository(project_root)
    assert repo.get(entries[0].id).status == "archived"


def test_reflection_dismiss_missing(project_root: Path) -> None:
    from nuself.cli import handle_reflection_dismiss
    import argparse

    args = argparse.Namespace(project_root=project_root, entry_id="missing", by_index=False)
    assert handle_reflection_dismiss(args) == 1


def test_reflection_archive_missing(project_root: Path) -> None:
    from nuself.cli import handle_reflection_archive
    import argparse

    args = argparse.Namespace(project_root=project_root, entry_id="missing", by_index=False)
    assert handle_reflection_archive(args) == 1
