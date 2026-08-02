from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

import pytest

from conversation_fixtures import ConversationStore
from nuself.cli import entrypoints
from nuself.cli.entrypoints import (
    EntrypointCallbacks,
    EntrypointController,
    InteractiveSender,
)
from nuself.cli.repl.types import InteractiveChatResult
from nuself.daemon.lifecycle import (
    DaemonStartError,
    DaemonStartResult,
    DaemonStatus,
)
from nuself.application.runtime import open_application_runtime, use_application_runtime
from nuself.config import runtime_paths


@pytest.fixture(autouse=True)
def _application_runtime(tmp_path: Path):  # pyright: ignore[reportUnusedFunction]
    runtime = open_application_runtime(tmp_path)
    try:
        with use_application_runtime(runtime):
            yield
    finally:
        runtime.close()


class RecordingCallbacks:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def send_daemon_chat(
        self,
        message: str,
        project_root: Path | None,
        conversation_id: str = "default",
    ) -> int:
        self.calls.append(("daemon", message, project_root, conversation_id))
        return 0

    def send_daemon_chat_interactive(
        self,
        message: str,
        project_root: Path | None,
        conversation_id: str = "default",
        *,
        turn_id: str | None = None,
    ) -> InteractiveChatResult:
        self.calls.append(
            ("daemon-interactive", message, project_root, conversation_id, turn_id)
        )
        return InteractiveChatResult(code=0, reply="daemon reply")

    def send_one_shot_chat(
        self,
        message: str,
        project_root: Path | None,
        conversation_id: str = "default",
    ) -> int:
        self.calls.append(("one-shot", message, project_root, conversation_id))
        return 0

    def send_one_shot_chat_interactive(
        self,
        message: str,
        project_root: Path | None,
        conversation_id: str = "default",
        *,
        turn_id: str | None = None,
    ) -> InteractiveChatResult:
        self.calls.append(
            ("one-shot-interactive", message, project_root, conversation_id, turn_id)
        )
        return InteractiveChatResult(code=0, reply="one-shot reply")

    def run_interactive(
        self,
        send_message: InteractiveSender,
        project_root: Path | None,
        *,
        initial_conversation_id: str = "default",
        daemon_activity: bool = False,
    ) -> int:
        self.calls.append(
            ("interactive", project_root, initial_conversation_id, daemon_activity)
        )
        result = send_message("interactive message", initial_conversation_id, "turn-1")
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
        phase="ready" if running else "stopped",
        pid=123 if running else None,
        socket_path=tmp_path / "private/runtime/nuself.sock",
        pid_path=tmp_path / "private/runtime/nuself.pid",
    )


def _return_status(
    value: DaemonStatus,
) -> Callable[..., DaemonStatus]:
    def get_status(
        _project_root: Path | None,
        **_kwargs: object,
    ) -> DaemonStatus:
        return value

    return get_status


def test_default_entrypoint_reuses_its_initial_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stopped = _status(tmp_path, running=False)
    ready = _status(tmp_path, running=True)
    status_calls = 0

    def observe(project_root: Path | None) -> DaemonStatus:
        nonlocal status_calls
        status_calls += 1
        return stopped

    def start(
        project_root: Path | None,
        *,
        initial_status: DaemonStatus | None = None,
    ) -> DaemonStartResult:
        assert initial_status is stopped
        return DaemonStartResult(
            before=stopped,
            status=ready,
            outcome="started",
        )

    monkeypatch.setattr(entrypoints.lifecycle, "status", observe)
    monkeypatch.setattr(entrypoints.lifecycle, "start", start)

    result = RecordingCallbacks().controller().handle_default(
        argparse.Namespace(
            project_root=tmp_path,
            scope=runtime_paths(tmp_path).scope,
            message="hello",
        )
    )

    assert result == 0
    assert status_calls == 1


def test_default_entrypoint_reports_typed_start_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stopped = _status(tmp_path, running=False)
    failure = DaemonStartError(
        "process_exited",
        status=stopped,
        exit_code=7,
    )

    def fail_start(
        project_root: Path | None,
        *,
        initial_status: DaemonStatus | None = None,
    ) -> DaemonStatus:
        del initial_status
        raise failure

    monkeypatch.setattr(entrypoints.lifecycle, "status", _return_status(stopped))
    monkeypatch.setattr(entrypoints.lifecycle, "start", fail_start)
    callbacks = RecordingCallbacks()

    result = callbacks.controller().handle_default(
        argparse.Namespace(
            project_root=tmp_path,
            scope=runtime_paths(tmp_path).scope,
            message="hello",
        )
    )

    assert result == 1
    assert callbacks.calls == []
    captured = capsys.readouterr()
    assert "Failed to start daemon: daemon process exited" in captured.err
    assert "daemon stopped" not in captured.err


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

    assert result == 3
    assert callbacks.calls == []
    assert "NuSelf daemon is not ready: stopped." in capsys.readouterr().err


def test_chat_owned_unready_never_falls_back_to_one_shot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    owned_unready = DaemonStatus(
        phase="owned_unready",
        pid=None,
        socket_path=tmp_path / "private/runtime/nuself.sock",
        pid_path=tmp_path / "private/runtime/nuself.pid",
    )
    monkeypatch.setattr(
        entrypoints.lifecycle,
        "status",
        _return_status(owned_unready),
    )
    callbacks = RecordingCallbacks()

    result = callbacks.controller().handle_chat(
        argparse.Namespace(
            project_root=tmp_path,
            message="hello",
            require_daemon=False,
        )
    )

    assert result == 4
    assert callbacks.calls == []
    assert "not ready: owned_unready" in capsys.readouterr().err


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


def test_new_conversation_deep_link_routes_message_then_local_repl(
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
        conversation_id=None,
        deep_link=(
            "nuself://new-conversation?"
            "title=proactive-conversation&message=hello%20there"
        ),
        message=None,
        create=False,
    )

    result = callbacks.controller().handle_open(args)

    assert result == 0
    assert args.message is None
    assert "proactive-conversation" in ConversationStore(tmp_path).list()
    assert callbacks.calls == [
        ("one-shot", "hello there", tmp_path, "proactive-conversation"),
        ("interactive", tmp_path, "proactive-conversation", False),
        (
            "one-shot-interactive",
            "interactive message",
            tmp_path,
            "proactive-conversation",
            "turn-1",
        ),
        ("interactive-result", "one-shot reply"),
    ]
