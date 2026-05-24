# pyright: reportPrivateUsage=false
"""Tests for REPL tab completion using prompt_toolkit Completer API."""

from __future__ import annotations

from pathlib import Path

from prompt_toolkit.document import Document

from nuself.agent.chat import ThreadState, ThreadStore
from nuself.cli import _InteractiveCompleter


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
