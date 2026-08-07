from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import pytest

from nuself.cli.repl import loop
from nuself.cli.repl.loop import (
    InteractiveLifecycleError,
    ReplCallbacks,
    run_interactive_loop,
)
from nuself.cli.repl.session import InteractiveSession
from nuself.cli.repl.types import InteractiveChatResult
from nuself.log.reader import read_log_events
from nuself.runtime.feature.protocol import ToolEffectResolution


class FakeInteractiveInput:
    def __init__(self, failure: BaseException) -> None:
        self.failure = failure

    def read(self) -> str:
        raise self.failure


class InputReader(Protocol):
    def read(self) -> str: ...


def _install_input(
    monkeypatch: pytest.MonkeyPatch,
    reader: InputReader,
) -> None:
    def input_factory(project_root: Path | None) -> InputReader:
        del project_root
        return reader

    monkeypatch.setattr(
        loop,
        "InteractiveInput",
        input_factory,
    )


def _callbacks(
    *,
    handle_command: Callable[
        [str, Path | None, str, InteractiveSession],
        tuple[str, str],
    ] | None = None,
    auto_save: Callable[
        [Path | None, InteractiveSession],
        None,
    ],
    run_curator: Callable[[Path | None], None],
    show_startup_notices: Callable[[Path | None], None] | None = None,
) -> ReplCallbacks:
    def default_command(
        command: str,
        project_root: Path | None,
        conversation_id: str,
        session: InteractiveSession,
    ) -> tuple[str, str]:
        del command, project_root, session
        return "exit", conversation_id

    def send_turn(
        send_message: Callable[
            [str, str, str | None, ToolEffectResolution | None],
            InteractiveChatResult,
        ],
        project_root: Path | None,
        conversation_id: str,
        message: str,
        session: InteractiveSession,
    ) -> int:
        del send_message, project_root, conversation_id, message, session
        return 0

    return ReplCallbacks(
        handle_command=handle_command or default_command,
        send_turn=send_turn,
        auto_save=auto_save,
        run_curator=run_curator,
        show_session_header=lambda project_root, conversation_id: None,
        show_startup_notices=show_startup_notices or (
            lambda project_root: None
        ),
        brand_banner=lambda: "NuSelf",
    )


def _unused_send(
    message: str,
    conversation_id: str,
    turn_id: str | None,
    effect_resolution: ToolEffectResolution | None,
) -> InteractiveChatResult:
    del message, conversation_id, turn_id, effect_resolution
    raise AssertionError("send callback must not run")


def test_eof_runs_each_cleanup_once_in_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    _install_input(
        monkeypatch,
        FakeInteractiveInput(EOFError()),
    )

    result = run_interactive_loop(
        _unused_send,
        tmp_path,
        _callbacks(
            auto_save=lambda project_root, session: calls.append("save"),
            run_curator=lambda project_root: calls.append("curator"),
        ),
    )

    assert result == 0
    assert calls == ["save", "curator"]


def test_startup_notices_are_presented_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Path | None] = []
    _install_input(monkeypatch, FakeInteractiveInput(EOFError()))

    result = run_interactive_loop(
        _unused_send,
        tmp_path,
        _callbacks(
            auto_save=lambda project_root, session: None,
            run_curator=lambda project_root: None,
            show_startup_notices=calls.append,
        ),
    )

    assert result == 0
    assert calls == [tmp_path]


def test_cleanup_attempts_both_steps_and_retains_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_error = OSError("transcript unavailable")
    curator_error = RuntimeError("curator unavailable")
    calls: list[str] = []
    _install_input(
        monkeypatch,
        FakeInteractiveInput(EOFError()),
    )

    def fail_save(
        project_root: Path | None,
        session: InteractiveSession,
    ) -> None:
        del project_root, session
        calls.append("save")
        raise save_error

    def fail_curator(project_root: Path | None) -> None:
        del project_root
        calls.append("curator")
        raise curator_error

    with pytest.raises(InteractiveLifecycleError) as captured:
        run_interactive_loop(
            _unused_send,
            tmp_path,
            _callbacks(
                auto_save=fail_save,
                run_curator=fail_curator,
            ),
        )

    assert calls == ["save", "curator"]
    assert captured.value.primary_error is None
    assert [failure.step for failure in captured.value.failures] == [
        "transcript.auto_save",
        "memory.curator.run",
    ]
    assert [failure.error for failure in captured.value.failures] == [
        save_error,
        curator_error,
    ]
    event = read_log_events(
        project_root=tmp_path,
        component="chat",
    )[-1]
    assert event.event == "interactive_cleanup_failed"
    assert event.metadata == {
        "steps": ("transcript.auto_save", "memory.curator.run"),
        "primary_failed": False,
    }


def test_cleanup_failure_retains_main_loop_control_as_cause(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary = SystemExit(7)
    cleanup_error = OSError("transcript unavailable")
    calls: list[str] = []

    def fail_command(
        command: str,
        project_root: Path | None,
        conversation_id: str,
        session: InteractiveSession,
    ) -> tuple[str, str]:
        del command, project_root, conversation_id, session
        raise primary

    def fail_save(
        project_root: Path | None,
        session: InteractiveSession,
    ) -> None:
        del project_root, session
        calls.append("save")
        raise cleanup_error

    def run_curator(project_root: Path | None) -> None:
        del project_root
        calls.append("curator")

    class CommandInput:
        def __init__(self) -> None:
            self.reads = 0

        def read(self) -> str:
            self.reads += 1
            return ":quit"

    _install_input(monkeypatch, CommandInput())

    with pytest.raises(InteractiveLifecycleError) as captured:
        run_interactive_loop(
            _unused_send,
            tmp_path,
            _callbacks(
                handle_command=fail_command,
                auto_save=fail_save,
                run_curator=run_curator,
            ),
        )

    assert calls == ["save", "curator"]
    assert captured.value.primary_error is primary
    assert captured.value.__cause__ is primary
    assert len(captured.value.failures) == 1
    assert captured.value.failures[0].error is cleanup_error


def test_primary_control_is_reraised_unchanged_when_cleanup_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary = SystemExit(9)
    calls: list[str] = []

    def fail_command(
        command: str,
        project_root: Path | None,
        conversation_id: str,
        session: InteractiveSession,
    ) -> tuple[str, str]:
        del command, project_root, conversation_id, session
        raise primary

    class CommandInput:
        def read(self) -> str:
            return ":quit"

    _install_input(monkeypatch, CommandInput())

    with pytest.raises(SystemExit) as captured:
        run_interactive_loop(
            _unused_send,
            tmp_path,
            _callbacks(
                handle_command=fail_command,
                auto_save=lambda project_root, session: calls.append(
                    "save"
                ),
                run_curator=lambda project_root: calls.append(
                    "curator"
                ),
            ),
        )

    assert captured.value is primary
    assert captured.value.__traceback__ is not None
    assert calls == ["save", "curator"]
    assert read_log_events(
        project_root=tmp_path,
        component="chat",
    ) == []


def test_cleanup_diagnostic_failure_cannot_replace_lifecycle_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cleanup_error = OSError("transcript unavailable")
    _install_input(
        monkeypatch,
        FakeInteractiveInput(EOFError()),
    )

    def fail_save(
        project_root: Path | None,
        session: InteractiveSession,
    ) -> None:
        del project_root, session
        raise cleanup_error

    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("diagnostic store unavailable")

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        fail_log,
    )

    with pytest.warns(
        RuntimeWarning,
        match="runtime/observability_sink_failed",
    ):
        with pytest.raises(InteractiveLifecycleError) as captured:
            run_interactive_loop(
                _unused_send,
                tmp_path,
                _callbacks(
                    auto_save=fail_save,
                    run_curator=lambda project_root: None,
                ),
            )

    assert len(captured.value.failures) == 1
    assert captured.value.failures[0].error is cleanup_error
