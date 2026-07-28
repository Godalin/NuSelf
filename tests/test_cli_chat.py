from __future__ import annotations

from pathlib import Path

import pytest

from nuself.cli import chat
from nuself.daemon.client import (
    DaemonApplicationError,
    DaemonConnectionError,
)
from nuself.daemon.payloads import ChatResponsePayload
from nuself.logs import read_log_events


def test_daemon_connection_failure_is_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_chat(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise DaemonConnectionError("timed out")

    monkeypatch.setattr(chat.client, "chat", fail_chat)

    result = chat.send_daemon_chat_interactive(
        "hello",
        tmp_path,
        "thread-1",
        turn_id="turn-1",
    )

    assert result.code == 1
    assert result.retryable is True
    assert result.error == "daemon request failed: timed out"
    assert result.reply is None
    assert result.error in capsys.readouterr().err


def test_daemon_application_failure_is_correlated_and_not_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_chat(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise DaemonApplicationError("graph failed")

    monkeypatch.setattr(chat.client, "chat", fail_chat)

    result = chat.send_daemon_chat_interactive(
        "hello",
        tmp_path,
        "thread-1",
        turn_id="turn-1",
    )

    assert result.code == 1
    assert result.retryable is False
    assert result.error == "graph failed"
    event = read_log_events(
        project_root=tmp_path,
        component="chat",
    )[-1]
    assert event.event == "daemon_chat_failed"
    assert event.thread_id == "thread-1"
    assert event.turn_id == "turn-1"
    assert event.error == "graph failed"


def test_daemon_success_projects_reply_and_memory_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def succeed_chat(*args: object, **kwargs: object) -> ChatResponsePayload:
        del args, kwargs
        return ChatResponsePayload(
            answer="answer",
            reply="reply",
            thread_id="thread-1",
            evidence_references=(),
            epistemic_status=None,
            memory_update="created=1",
        )

    monkeypatch.setattr(chat.client, "chat", succeed_chat)

    result = chat.send_daemon_chat_interactive(
        "hello",
        tmp_path,
        "thread-1",
        turn_id="turn-1",
    )

    assert result.code == 0
    assert result.reply == "reply"
    assert result.memory_update == "created=1"


def test_one_shot_success_runs_curator_after_reply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def reply(
        message: str,
        project_root: Path | None,
        thread_id: str = "default",
        *,
        turn_id: str | None = None,
    ) -> str:
        assert project_root == tmp_path
        calls.append(f"reply:{message}:{thread_id}:{turn_id}")
        return "done"

    def curate(project_root: Path | None) -> None:
        assert project_root == tmp_path
        calls.append("curator")

    monkeypatch.setattr(chat, "one_shot_reply", reply)
    monkeypatch.setattr(chat, "run_memory_curator", curate)

    result = chat.send_one_shot_chat_interactive(
        "hello",
        tmp_path,
        "thread-1",
        turn_id="turn-1",
    )

    assert result.code == 0
    assert result.reply == "done"
    assert calls == ["reply:hello:thread-1:turn-1", "curator"]
