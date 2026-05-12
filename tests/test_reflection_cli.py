# pyright: reportPrivateUsage=false
"""Tests for nuself reflection CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nuself.logs import write_log_event


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    (tmp_path / "private" / "runtime").mkdir(parents=True)
    (tmp_path / "private" / "logs").mkdir(parents=True)
    (tmp_path / "private" / "outbox").mkdir(parents=True)
    return tmp_path


def _seed_reflection_events(project_root: Path, count: int = 3) -> None:
    for i in range(count):
        write_log_event(
            "reflection",
            "persona_discussion",
            f"[{'approved' if i % 2 == 0 else 'rejected'}] Test idea {i}",
            project_root=project_root,
            status="approved" if i % 2 == 0 else "rejected",
            metadata={
                "candidate_id": f"candidate-{i}",
                "candidate_title": f"Test idea {i}",
                "candidate_type": "question",
                "composite": 0.6 + i * 0.1,
                "approved": i % 2 == 0,
                "scores": {"analyst": 0.8, "skeptic": 0.6},
                "blocking_vetos": [],
                "winner_persona_ids": ["analyst"] if i % 2 == 0 else [],
                "emergent_persona_ids": [],
                "discussion_trace": [
                    f"candidate: Test idea {i}",
                    "turn-1: analyst scores 0.8",
                    "turn-1: skeptic scores 0.6",
                ],
                "revised_title": f"Revised idea {i}",
                "revised_body": f"Body for idea {i}",
            },
        )


def test_reflection_list_empty(project_root: Path) -> None:
    from nuself.cli import handle_reflection_list
    import argparse

    args = argparse.Namespace(project_root=project_root, tail=20, as_json=False)
    assert handle_reflection_list(args) == 0


def test_reflection_list_with_events(project_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from nuself.cli import handle_reflection_list
    import argparse

    _seed_reflection_events(project_root, 3)
    args = argparse.Namespace(project_root=project_root, tail=20, as_json=False)
    assert handle_reflection_list(args) == 0
    output = capsys.readouterr().out
    assert "[approved]" in output
    assert "[rejected]" in output


def test_reflection_list_hides_started_by_default(project_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from nuself.cli import handle_reflection_list
    import argparse

    write_log_event(
        "reflection",
        "cycle_started",
        "reflection cycle triggered",
        project_root=project_root,
        status="started",
    )
    _seed_reflection_events(project_root, 1)

    args = argparse.Namespace(project_root=project_root, tail=20, as_json=False, include_started=False)
    assert handle_reflection_list(args) == 0
    output = capsys.readouterr().out
    assert "triggered" not in output
    assert "[approved]" in output


def test_reflection_list_can_include_started(project_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from nuself.cli import handle_reflection_list
    import argparse

    write_log_event(
        "reflection",
        "cycle_started",
        "reflection cycle triggered",
        project_root=project_root,
        status="started",
    )
    _seed_reflection_events(project_root, 1)

    args = argparse.Namespace(project_root=project_root, tail=20, as_json=False, include_started=True)
    assert handle_reflection_list(args) == 0
    output = capsys.readouterr().out
    assert "triggered" in output


def test_reflection_list_json(project_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from nuself.cli import handle_reflection_list
    import argparse

    _seed_reflection_events(project_root, 2)
    args = argparse.Namespace(project_root=project_root, tail=20, as_json=True)
    assert handle_reflection_list(args) == 0
    output = capsys.readouterr().out
    lines = [line for line in output.strip().splitlines() if line]
    assert len(lines) == 2
    for line in lines:
        parsed = json.loads(line)
        assert "component" in parsed
        assert parsed["component"] == "reflection"


def test_reflection_show(project_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from nuself.cli import handle_reflection_show
    import argparse

    _seed_reflection_events(project_root, 3)
    args = argparse.Namespace(project_root=project_root, event_index=0, as_json=False)
    assert handle_reflection_show(args) == 0
    output = capsys.readouterr().out
    assert "Test idea 0" in output
    assert "discussion trace:" in output


def test_reflection_show_uses_same_indexing_as_list(project_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from nuself.cli import handle_reflection_list, handle_reflection_show
    import argparse

    write_log_event(
        "reflection",
        "cycle_started",
        "reflection cycle triggered",
        project_root=project_root,
        status="started",
    )
    _seed_reflection_events(project_root, 2)

    list_args = argparse.Namespace(project_root=project_root, tail=20, as_json=False, include_started=False)
    assert handle_reflection_list(list_args) == 0
    list_output = capsys.readouterr().out
    assert "Test idea 0" in list_output
    assert "triggered" not in list_output

    show_args = argparse.Namespace(project_root=project_root, event_index=0, as_json=False, include_started=False)
    assert handle_reflection_show(show_args) == 0
    show_output = capsys.readouterr().out
    assert "Test idea 0" in show_output
    assert "triggered" not in show_output


def test_reflection_show_json(project_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from nuself.cli import handle_reflection_show
    import argparse

    _seed_reflection_events(project_root, 1)
    args = argparse.Namespace(project_root=project_root, event_index=0, as_json=True)
    assert handle_reflection_show(args) == 0
    output = capsys.readouterr().out
    parsed = json.loads(output.strip())
    assert parsed["metadata"]["candidate_id"] == "candidate-0"


def test_reflection_show_invalid_index(project_root: Path) -> None:
    from nuself.cli import handle_reflection_show
    import argparse

    _seed_reflection_events(project_root, 2)
    args = argparse.Namespace(project_root=project_root, event_index=99, as_json=False)
    assert handle_reflection_show(args) == 1


def test_reflection_show_empty(project_root: Path) -> None:
    from nuself.cli import handle_reflection_show
    import argparse

    args = argparse.Namespace(project_root=project_root, event_index=0, as_json=False)
    assert handle_reflection_show(args) == 1
