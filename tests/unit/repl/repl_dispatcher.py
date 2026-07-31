from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from _pytest.capture import CaptureFixture
import pytest

from nuself.agent.chat import ThreadState
from thread_fixtures import ThreadStore
import nuself.cli.repl.dispatcher as dispatcher_module
from nuself.cli.repl.dispatcher import ReplCommandDispatcher
from nuself.cli.repl.registry import command_names
from nuself.cli.repl.session import InteractiveSession
from nuself.runtime.handlers import HandlerRegistryCoverageError


def _session() -> InteractiveSession:
    return InteractiveSession(connected_at=datetime.now(UTC))


def test_dispatcher_owns_thread_switch_and_creation(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    ThreadStore(tmp_path).save(ThreadState.empty("default"))

    action = ReplCommandDispatcher().handle(
        ":thread project",
        tmp_path,
        "default",
        _session(),
    )

    assert action == ("redraw_header", "project")
    assert "project" in ThreadStore(tmp_path).list()
    assert "Switched to thread: project" in capsys.readouterr().out


def test_dispatcher_unknown_command_preserves_thread_and_uses_registry_help(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    action = ReplCommandDispatcher().handle(
        ":not-a-command",
        tmp_path,
        "current",
        _session(),
    )

    assert action == ("", "current")
    output = capsys.readouterr().out
    assert "Unknown interactive command: :not-a-command" in output
    assert ":help" in output


def test_dispatcher_registry_is_complete_and_sealed() -> None:
    dispatcher = ReplCommandDispatcher()

    assert set(dispatcher.registered_commands) == set(command_names())


def test_retry_requires_an_available_retryable_turn(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    action = ReplCommandDispatcher().handle(
        ":retry",
        tmp_path,
        "default",
        _session(),
    )

    assert action == ("", "default")
    assert "No retryable chat turn" in capsys.readouterr().out


def test_dispatcher_uses_shared_catalog_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dispatcher_module,
        "command_names",
        lambda: tuple(
            name for name in command_names() if name != "history"
        ),
    )

    with pytest.raises(HandlerRegistryCoverageError) as captured:
        ReplCommandDispatcher()

    assert captured.value.missing == frozenset()
    assert captured.value.extra == frozenset({"history"})
