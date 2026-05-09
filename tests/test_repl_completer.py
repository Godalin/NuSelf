# pyright: reportPrivateUsage=false
"""Tests for REPL tab completion."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from nuself.agent.chat import ThreadState, ThreadStore
from nuself.cli import _InteractiveCompleter, _setup_interactive_completer


class FakeReadline:
    def __init__(self) -> None:
        self._completer: object | None = None
        self._delims = " \t\n`~!@#$%^&*()-=+[{]}\\|;:'\",<>/?"
        self._line_buffer = ""

    def parse_and_bind(self, binding: str) -> None:
        pass

    def set_completer(self, completer: object | None) -> None:
        self._completer = completer

    def get_completer_delims(self) -> str:
        return self._delims

    def set_completer_delims(self, delims: str) -> None:
        self._delims = delims

    def get_line_buffer(self) -> str:
        return self._line_buffer


@pytest.fixture
def fake_readline() -> FakeReadline:
    return FakeReadline()


def test_setup_completer_sets_bindings(fake_readline: FakeReadline) -> None:
    with patch("nuself.cli.readline", fake_readline):
        _setup_interactive_completer(None)
        assert fake_readline._completer is not None
        assert ":" not in fake_readline._delims


def test_completer_returns_none_without_readline(tmp_path: Path) -> None:
    completer = _InteractiveCompleter(tmp_path)
    with patch("nuself.cli.readline", None):
        assert completer(":th", 0) is None


def test_completer_suggests_commands(tmp_path: Path, fake_readline: FakeReadline) -> None:
    completer = _InteractiveCompleter(tmp_path)
    with patch("nuself.cli.readline", fake_readline):
        fake_readline._line_buffer = ":th"
        results: list[str | None] = []
        for state in range(10):
            result = completer(":th", state)
            if result is None:
                break
            results.append(result)
        assert ":thread" in results
        assert ":threads" in results


def test_completer_suggests_thread_ids(tmp_path: Path, fake_readline: FakeReadline) -> None:
    ThreadStore(tmp_path).save(ThreadState.empty("alpha"))
    ThreadStore(tmp_path).save(ThreadState.empty("beta"))
    completer = _InteractiveCompleter(tmp_path)
    with patch("nuself.cli.readline", fake_readline):
        fake_readline._line_buffer = ":thread a"
        assert completer("a", 0) == "alpha"
        assert completer("a", 1) is None


def test_completer_empty_for_non_command(tmp_path: Path, fake_readline: FakeReadline) -> None:
    completer = _InteractiveCompleter(tmp_path)
    with patch("nuself.cli.readline", fake_readline):
        fake_readline._line_buffer = "hello"
        assert completer("hello", 0) is None


def test_completer_multiple_command_matches(tmp_path: Path, fake_readline: FakeReadline) -> None:
    completer = _InteractiveCompleter(tmp_path)
    with patch("nuself.cli.readline", fake_readline):
        fake_readline._line_buffer = ":mem"
        results: list[str | None] = []
        for state in range(10):
            result = completer(":mem", state)
            if result is None:
                break
            results.append(result)
        assert ":memory" in results
        assert ":mem" in results


def test_completer_suggests_archived_thread_ids(tmp_path: Path, fake_readline: FakeReadline) -> None:
    store = ThreadStore(tmp_path)
    store.save(ThreadState.empty("alpha"))
    store.save(ThreadState.empty("beta"))
    store.archive("alpha")
    completer = _InteractiveCompleter(tmp_path)
    with patch("nuself.cli.readline", fake_readline):
        fake_readline._line_buffer = ":unarchive a"
        assert completer("a", 0) == "alpha"
        assert completer("a", 1) is None
