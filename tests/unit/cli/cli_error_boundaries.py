import argparse
from pathlib import Path

import pytest

from nuself import cli
from nuself.agent.chat.thread import ThreadStore
from nuself.cli.chat import chat_request_timeout_seconds
from nuself.cli.commands.reason import handle_reason_start
from nuself.cli.repl.commands import (
    handle_interactive_history_command,
    handle_interactive_persona_command,
    handle_interactive_reason_command,
)
from nuself.config import ConfigSystem
from nuself.logs import read_log_events
from nuself.persona.prompt_repo import PersonaPromptRepository
from nuself.reason.errors import ReasonPromptError
from nuself.reason.service import ReasonService


def test_chat_timeout_uses_default_after_malformed_yaml(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "config.yaml").write_text(
        "chat: [unterminated",
        encoding="utf-8",
    )
    ConfigSystem.clear_cache()

    timeout = chat_request_timeout_seconds(tmp_path)

    assert timeout == cli.CHAT_REQUEST_TIMEOUT_SECONDS
    assert "ignoring unreadable config" in capsys.readouterr().err


def test_chat_timeout_does_not_hide_unexpected_config_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_load(*args: object, **kwargs: object) -> None:
        raise RuntimeError("config implementation failed")

    monkeypatch.setattr(ConfigSystem, "load", fail_load)

    with pytest.raises(RuntimeError, match="config implementation failed"):
        chat_request_timeout_seconds(tmp_path)


def test_history_reports_empty_missing_thread(tmp_path: Path) -> None:
    assert handle_interactive_history_command(tmp_path, "missing") == (
        "No messages in this thread."
    )


def test_history_reports_compact_load_failure_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_load(self: ThreadStore, thread_id: str) -> None:
        try:
            raise OSError("thread file unreadable")
        except OSError as exc:
            raise RuntimeError("history decode failed") from exc

    monkeypatch.setattr(ThreadStore, "load", fail_load)

    rendered = handle_interactive_history_command(
        tmp_path,
        "default",
    )

    assert rendered == (
        "Unable to load thread history for 'default': "
        "history decode failed <- thread file unreadable"
    )
    [event] = read_log_events(project_root=tmp_path, component="chat")
    assert event.event == "interactive_history_load_failed"
    assert event.level == "error"
    assert event.status == "error"
    assert event.error == "history decode failed <- thread file unreadable"
    assert event.metadata == {"thread_id": "default"}


def test_persona_command_reports_failure_without_logging_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_create(args: object) -> None:
        raise OSError("persona store unavailable")

    monkeypatch.setattr(
        "nuself.cli.repl.commands.handle_persona_create",
        fail_create,
    )

    rendered = handle_interactive_persona_command(
        "create guide private-prompt-text",
        tmp_path,
    )

    assert "persona store unavailable" in rendered
    [event] = read_log_events(project_root=tmp_path, component="persona")
    assert event.event == "interactive_command_failed"
    assert event.level == "error"
    assert event.status == "error"
    assert event.error == "persona store unavailable"
    assert event.metadata == {"action": "create"}
    assert "private-prompt-text" not in event.message
    assert "private-prompt-text" not in event.error


def test_history_keeps_rendered_error_when_diagnostic_sink_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_load(self: ThreadStore, thread_id: str) -> None:
        raise RuntimeError("history unavailable")

    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("log disk full")

    monkeypatch.setattr(ThreadStore, "load", fail_load)
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
        match=(
            "runtime/observability_sink_failed.*"
            "component=chat event=interactive_history_load_failed.*"
            "history unavailable.*log disk full"
        ),
    ):
        rendered = handle_interactive_history_command(tmp_path, "default")

    assert rendered == (
        "Unable to load thread history for 'default': history unavailable"
    )


def test_history_does_not_convert_control_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interrupt = KeyboardInterrupt()

    def interrupt_load(self: ThreadStore, thread_id: str) -> None:
        raise interrupt

    monkeypatch.setattr(ThreadStore, "load", interrupt_load)

    with pytest.raises(KeyboardInterrupt) as caught:
        handle_interactive_history_command(tmp_path, "default")

    assert caught.value is interrupt
    assert read_log_events(project_root=tmp_path, component="chat") == []


def test_persona_command_does_not_convert_control_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interrupt = KeyboardInterrupt()

    def interrupt_list(self: PersonaPromptRepository) -> None:
        raise interrupt

    monkeypatch.setattr(PersonaPromptRepository, "list", interrupt_list)

    with pytest.raises(KeyboardInterrupt) as caught:
        handle_interactive_persona_command("", tmp_path)

    assert caught.value is interrupt
    assert read_log_events(project_root=tmp_path, component="persona") == []


def test_reason_cli_renders_declared_domain_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def reject_start(
        self: ReasonService,
        topic: str,
        **kwargs: object,
    ) -> None:
        raise ReasonPromptError("reason prompt unavailable")

    monkeypatch.setattr(ReasonService, "start_thread", reject_start)
    args = argparse.Namespace(
        project_root=tmp_path,
        topic="topic",
        priority="normal",
        mandate=[],
    )

    assert handle_reason_start(args) == 1
    assert capsys.readouterr().err == "Error: reason prompt unavailable\n"


def test_reason_cli_does_not_relabel_unexpected_runtime_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unexpected = RuntimeError("reason implementation failed")

    def fail_start(
        self: ReasonService,
        topic: str,
        **kwargs: object,
    ) -> None:
        raise unexpected

    monkeypatch.setattr(ReasonService, "start_thread", fail_start)
    args = argparse.Namespace(
        project_root=tmp_path,
        topic="topic",
        priority="normal",
        mandate=[],
    )

    with pytest.raises(RuntimeError) as caught:
        handle_reason_start(args)

    assert caught.value is unexpected


def test_reason_repl_does_not_relabel_unexpected_runtime_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unexpected = RuntimeError("reason implementation failed")

    def fail_start(
        self: ReasonService,
        topic: str,
        **kwargs: object,
    ) -> None:
        raise unexpected

    monkeypatch.setattr(ReasonService, "start_thread", fail_start)

    with pytest.raises(RuntimeError) as caught:
        handle_interactive_reason_command("start topic", tmp_path)

    assert caught.value is unexpected
