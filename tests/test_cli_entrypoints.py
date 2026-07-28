from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

import pytest

from nuself.agent.chat import ThreadStore
from nuself.cli import entrypoints
from nuself.cli.entrypoints import (
    EntrypointCallbacks,
    EntrypointController,
    InteractiveSender,
)
from nuself.cli.repl.types import InteractiveChatResult
from nuself.daemon.lifecycle import DaemonStatus


class RecordingCallbacks:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def send_daemon_chat(
        self,
        message: str,
        project_root: Path | None,
        thread_id: str = "default",
    ) -> int:
        self.calls.append(("daemon", message, project_root, thread_id))
        return 0

    def send_daemon_chat_interactive(
        self,
        message: str,
        project_root: Path | None,
        thread_id: str = "default",
        *,
        turn_id: str | None = None,
    ) -> InteractiveChatResult:
        self.calls.append(
            ("daemon-interactive", message, project_root, thread_id, turn_id)
        )
        return InteractiveChatResult(code=0, reply="daemon reply")

    def send_one_shot_chat(
        self,
        message: str,
        project_root: Path | None,
        thread_id: str = "default",
    ) -> int:
        self.calls.append(("one-shot", message, project_root, thread_id))
        return 0

    def send_one_shot_chat_interactive(
        self,
        message: str,
        project_root: Path | None,
        thread_id: str = "default",
        *,
        turn_id: str | None = None,
    ) -> InteractiveChatResult:
        self.calls.append(
            ("one-shot-interactive", message, project_root, thread_id, turn_id)
        )
        return InteractiveChatResult(code=0, reply="one-shot reply")

    def run_interactive(
        self,
        send_message: InteractiveSender,
        project_root: Path | None,
        *,
        initial_thread_id: str = "default",
        daemon_activity: bool = False,
    ) -> int:
        self.calls.append(
            ("interactive", project_root, initial_thread_id, daemon_activity)
        )
        result = send_message("interactive message", initial_thread_id, "turn-1")
        self.calls.append(("interactive-result", result.reply))
        return result.code

    def controller(self) -> EntrypointController:
        return EntrypointController(
            EntrypointCallbacks(
                send_daemon_chat=self.send_daemon_chat,
                send_daemon_chat_interactive=self.send_daemon_chat_interactive,
                send_one_shot_chat=self.send_one_shot_chat,
                send_one_shot_chat_interactive=self.send_one_shot_chat_interactive,
                run_interactive=self.run_interactive,
            )
        )


def _status(tmp_path: Path, *, running: bool) -> DaemonStatus:
    return DaemonStatus(
        running=running,
        pid=123 if running else None,
        socket_path=tmp_path / "private/runtime/nuself.sock",
        pid_path=tmp_path / "private/runtime/nuself.pid",
    )


def _return_status(
    value: DaemonStatus,
) -> Callable[[Path | None], DaemonStatus]:
    def get_status(_project_root: Path | None) -> DaemonStatus:
        return value

    return get_status


def test_default_entrypoint_stops_when_daemon_start_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stopped = _status(tmp_path, running=False)
    monkeypatch.setattr(entrypoints.lifecycle, "status", _return_status(stopped))
    monkeypatch.setattr(entrypoints.lifecycle, "start", _return_status(stopped))
    callbacks = RecordingCallbacks()

    result = callbacks.controller().handle_default(
        argparse.Namespace(project_root=tmp_path, message="hello")
    )

    assert result == 1
    assert callbacks.calls == []
    captured = capsys.readouterr()
    assert "Starting NuSelf daemon..." in captured.out
    assert "Failed to start daemon:" in captured.err


def test_chat_require_daemon_rejects_local_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        entrypoints.lifecycle,
        "status",
        _return_status(_status(tmp_path, running=False)),
    )
    callbacks = RecordingCallbacks()

    result = callbacks.controller().handle_chat(
        argparse.Namespace(
            project_root=tmp_path,
            message="hello",
            require_daemon=True,
        )
    )

    assert result == 1
    assert callbacks.calls == []
    assert "NuSelf daemon is not running." in capsys.readouterr().err


def test_running_chat_injects_daemon_sender_into_repl(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        entrypoints.lifecycle,
        "status",
        _return_status(_status(tmp_path, running=True)),
    )
    callbacks = RecordingCallbacks()

    result = callbacks.controller().handle_chat(
        argparse.Namespace(
            project_root=tmp_path,
            message=None,
            require_daemon=False,
        )
    )

    assert result == 0
    assert callbacks.calls == [
        ("interactive", tmp_path, "default", True),
        (
            "daemon-interactive",
            "interactive message",
            tmp_path,
            "default",
            "turn-1",
        ),
        ("interactive-result", "daemon reply"),
    ]


def test_new_thread_deep_link_routes_message_then_local_repl(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        entrypoints.lifecycle,
        "status",
        _return_status(_status(tmp_path, running=False)),
    )
    callbacks = RecordingCallbacks()
    args = argparse.Namespace(
        project_root=tmp_path,
        thread_id=None,
        deep_link=(
            "nuself://new-thread?"
            "title=proactive-thread&message=hello%20there"
        ),
        message=None,
        create=False,
    )

    result = callbacks.controller().handle_open(args)

    assert result == 0
    assert args.message is None
    assert "proactive-thread" in ThreadStore(tmp_path).list()
    assert callbacks.calls == [
        ("one-shot", "hello there", tmp_path, "proactive-thread"),
        ("interactive", tmp_path, "proactive-thread", False),
        (
            "one-shot-interactive",
            "interactive message",
            tmp_path,
            "proactive-thread",
            "turn-1",
        ),
        ("interactive-result", "one-shot reply"),
    ]
