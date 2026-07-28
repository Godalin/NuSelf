from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from _pytest.capture import CaptureFixture

from nuself.agent.chat import ThreadState, ThreadStore
from nuself.cli.repl.dispatcher import handle_interactive_command
from nuself.cli.repl.session import InteractiveSession


def _session() -> InteractiveSession:
    return InteractiveSession(connected_at=datetime.now(UTC))


def test_dispatcher_owns_thread_switch_and_creation(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    ThreadStore(tmp_path).save(ThreadState.empty("default"))

    action = handle_interactive_command(
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
    action = handle_interactive_command(
        ":not-a-command",
        tmp_path,
        "current",
        _session(),
    )

    assert action == ("", "current")
    output = capsys.readouterr().out
    assert "Unknown interactive command: :not-a-command" in output
    assert ":help" in output
