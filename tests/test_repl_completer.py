# pyright: reportPrivateUsage=false
"""Tests for REPL tab completion using prompt_toolkit Completer API."""

from __future__ import annotations

from pathlib import Path

import pytest
from prompt_toolkit.document import Document

from nuself.agent.chat import ThreadState, ThreadStore
from nuself.cli import _InteractiveCompleter
from nuself.logs import read_log_events
from nuself.reason.repository import ReasonRepository


def test_completer_suggests_commands(tmp_path: Path) -> None:
    completer = _InteractiveCompleter(tmp_path)
    doc = Document(":th", cursor_position=3)
    completions = list(completer.get_completions(doc, None))
    texts = [c.text for c in completions]
    assert ":thread" in texts
    assert ":threads" not in texts


def test_completer_suggests_thread_ids(tmp_path: Path) -> None:
    ThreadStore(tmp_path).save(ThreadState.empty("alpha"))
    ThreadStore(tmp_path).save(ThreadState.empty("beta"))
    completer = _InteractiveCompleter(tmp_path)
    doc = Document(":thread a", cursor_position=9)
    completions = list(completer.get_completions(doc, None))
    texts = [c.text for c in completions]
    assert "alpha" in texts


def test_completer_empty_for_non_command(tmp_path: Path) -> None:
    completer = _InteractiveCompleter(tmp_path)
    doc = Document("hello", cursor_position=5)
    completions = list(completer.get_completions(doc, None))
    assert len(completions) == 0


def test_completer_multiple_command_matches(tmp_path: Path) -> None:
    completer = _InteractiveCompleter(tmp_path)
    doc = Document(":mem", cursor_position=4)
    completions = list(completer.get_completions(doc, None))
    texts = [c.text for c in completions]
    assert ":memory" not in texts
    assert ":mem" in texts


def test_completer_suggests_archived_thread_ids(tmp_path: Path) -> None:
    store = ThreadStore(tmp_path)
    store.save(ThreadState.empty("alpha"))
    store.save(ThreadState.empty("beta"))
    store.archive("alpha")
    completer = _InteractiveCompleter(tmp_path)
    doc = Document(":unarchive a", cursor_position=12)
    completions = list(completer.get_completions(doc, None))
    texts = [c.text for c in completions]
    assert "alpha" in texts


@pytest.mark.parametrize(
    ("method_name", "command", "completion_kind"),
    [
        ("list", ":thread a", "threads"),
        ("list_archived", ":unarchive a", "archived_threads"),
    ],
)
def test_thread_completion_failure_is_observed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
    command: str,
    completion_kind: str,
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("thread index unavailable")

    monkeypatch.setattr(ThreadStore, method_name, fail)
    completer = _InteractiveCompleter(tmp_path)

    completions = list(
        completer.get_completions(
            Document(command, cursor_position=len(command)),
            None,
        )
    )

    assert completions == []
    event = read_log_events(project_root=tmp_path, component="chat")[-1]
    assert event.event == "completion_load_failed"
    assert event.error == "thread index unavailable"
    assert event.metadata == {"completion": completion_kind}


def test_reason_completion_failure_is_observed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("reason index unavailable")

    monkeypatch.setattr(ReasonRepository, "list_threads", fail)
    command = ":reason show a"
    completer = _InteractiveCompleter(tmp_path)

    completions = list(
        completer.get_completions(
            Document(command, cursor_position=len(command)),
            None,
        )
    )

    assert completions == []
    event = read_log_events(
        project_root=tmp_path,
        component="reasoning",
    )[-1]
    assert event.event == "completion_load_failed"
    assert event.error == "reason index unavailable"
    assert event.metadata == {}
