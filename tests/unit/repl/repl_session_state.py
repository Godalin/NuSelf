from pathlib import Path

import pytest
from prompt_toolkit.history import FileHistory

from nuself.cli.repl.input import InteractiveInput
from nuself.log.reader import read_log_events


def _fallback_input(prompt: str) -> str:
    return "fallback line"


def test_interactive_input_instances_do_not_share_mutable_objects(
    tmp_path: Path,
) -> None:
    first = InteractiveInput(tmp_path / "first")
    second = InteractiveInput(tmp_path / "second")

    assert first.history is not second.history
    assert first.completer is not second.completer


def test_builtin_input_survives_history_persistence_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interactive_input = InteractiveInput(tmp_path)

    def fail_history(self: FileHistory, line: str) -> None:
        raise OSError("history file unavailable")

    def fake_input(prompt: str) -> str:
        return "accepted line"

    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr(FileHistory, "append_string", fail_history)

    assert interactive_input.read() == "accepted line"
    event = read_log_events(project_root=tmp_path, component="chat")[-1]
    assert event.event == "interactive_history_write_failed"
    assert event.error == "history file unavailable"


def test_non_tty_builtin_input_is_not_a_prompt_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interactive_input = InteractiveInput(tmp_path)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("builtins.input", _fallback_input)

    assert interactive_input.read() == "fallback line"
    assert read_log_events(
        project_root=tmp_path,
        component="chat",
    ) == []


@pytest.mark.parametrize(
    "failure",
    (
        AttributeError("terminal capability unavailable"),
        OSError("styled prompt unavailable"),
    ),
)
def test_styled_input_failure_is_observed_before_builtin_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    interactive_input = InteractiveInput(tmp_path)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    def fail_prompt(*args: object, **kwargs: object) -> str:
        raise failure

    monkeypatch.setattr("nuself.cli.repl.input._prompt", fail_prompt)
    monkeypatch.setattr("builtins.input", _fallback_input)

    assert interactive_input.read() == "fallback line"

    event = read_log_events(
        project_root=tmp_path,
        component="chat",
    )[-1]
    assert event.event == "interactive_prompt_failed"
    assert event.status == "degraded"
    assert event.error == str(failure)
    assert event.metadata == {"fallback": "builtin_input"}


def test_terminal_detection_failure_uses_observed_builtin_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interactive_input = InteractiveInput(tmp_path)

    def fail_isatty() -> bool:
        raise OSError("terminal detection unavailable")

    monkeypatch.setattr("sys.stdin.isatty", fail_isatty)
    monkeypatch.setattr("builtins.input", _fallback_input)

    assert interactive_input.read() == "fallback line"
    event = read_log_events(
        project_root=tmp_path,
        component="chat",
    )[-1]
    assert event.event == "interactive_prompt_failed"
    assert event.error == "terminal detection unavailable"


@pytest.mark.parametrize(
    "failure",
    (
        RuntimeError("unexpected prompt failure"),
        EOFError(),
        KeyboardInterrupt(),
    ),
)
def test_styled_input_does_not_swallow_undeclared_control_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException,
) -> None:
    interactive_input = InteractiveInput(tmp_path)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    builtin_called = False

    def fail_prompt(*args: object, **kwargs: object) -> str:
        raise failure

    def builtin_input(prompt: str) -> str:
        nonlocal builtin_called
        builtin_called = True
        return "must not be read"

    monkeypatch.setattr("nuself.cli.repl.input._prompt", fail_prompt)
    monkeypatch.setattr("builtins.input", builtin_input)

    with pytest.raises(type(failure)):
        interactive_input.read()

    assert not builtin_called
    assert read_log_events(
        project_root=tmp_path,
        component="chat",
    ) == []
