from pathlib import Path

import pytest

from nuself import cli
from nuself.agent.chat import ThreadStore
from nuself.cli.chat import chat_request_timeout_seconds
from nuself.cli.repl.commands import handle_interactive_history_command
from nuself.config import ConfigSystem


def test_chat_timeout_uses_default_after_malformed_yaml(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_dir = tmp_path / "private"
    private_dir.mkdir()
    (private_dir / "config.yaml").write_text(
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
