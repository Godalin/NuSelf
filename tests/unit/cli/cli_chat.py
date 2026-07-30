from __future__ import annotations

from pathlib import Path

import pytest

from nuself.cli import chat
from nuself.daemon.client import (
    DaemonApplicationError,
    DaemonConnectionError,
)
from nuself.daemon.payloads import ChatResponsePayload
from nuself.logs import read_log_events, write_log_event
from nuself.runtime.context import (
    RuntimeContext,
    current_runtime_context,
    runtime_context,
)


def test_daemon_connection_failure_is_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    observed: list[RuntimeContext] = []

    def fail_chat(*args: object, **kwargs: object) -> None:
        del args, kwargs
        observed.append(current_runtime_context())
        raise DaemonConnectionError("timed out")

    monkeypatch.setattr(chat.client, "chat", fail_chat)

    with runtime_context(
        request_id="request-1",
        job_id="job-1",
        trace_id="trace-1",
        source="outer",
    ):
        result = chat.send_daemon_chat_interactive(
            "hello",
            tmp_path,
            "thread-1",
            turn_id="turn-1",
        )
        assert current_runtime_context() == RuntimeContext(
            request_id="request-1",
            job_id="job-1",
            trace_id="trace-1",
            source="outer",
        )

    assert result.code == 4
    assert result.retryable is True
    assert result.error == "daemon request failed: timed out"
    assert result.reply is None
    assert result.failure_phase == "unknown"
    assert result.request_id is None
    assert result.request_may_have_completed is True
    assert result.error in capsys.readouterr().err
    assert observed == [
        RuntimeContext(
            thread_id="thread-1",
            request_id="request-1",
            turn_id="turn-1",
            job_id="job-1",
            trace_id="trace-1",
            source="client",
        )
    ]


def test_daemon_payload_decode_failure_is_not_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_chat(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise DaemonConnectionError(
            "daemon chat response is malformed",
            phase="payload_decode",
            request_id="request-1",
        )

    monkeypatch.setattr(chat.client, "chat", fail_chat)

    result = chat.send_daemon_chat_interactive(
        "hello",
        tmp_path,
        "thread-1",
        turn_id="turn-1",
    )

    assert result.code == 1
    assert result.retryable is False
    assert result.error == (
        "daemon request failed: daemon chat response is malformed"
    )
    assert result.failure_phase == "payload_decode"
    assert result.request_id == "request-1"
    assert result.request_may_have_completed is True


def test_daemon_connection_failure_redacts_cli_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    connection_secret = "connection-secret-value"

    def fail_chat(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise DaemonConnectionError(
            f"connection failed api_key={connection_secret}"
        )

    monkeypatch.setattr(chat.client, "chat", fail_chat)

    result = chat.send_daemon_chat_interactive(
        "hello",
        tmp_path,
    )

    assert result.error == "daemon request failed: connection failed api_key=***"
    assert connection_secret not in capsys.readouterr().err


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
    assert event.source == "client"
    assert event.error == "graph failed"


def test_one_shot_failure_is_safely_presented_and_audited(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime_secret = "runtime-secret-value"

    def fail_reply(*args: object, **kwargs: object) -> str:
        del args, kwargs
        raise RuntimeError(
            f"one-shot failed password={runtime_secret}"
        )

    monkeypatch.setattr(chat, "one_shot_reply", fail_reply)

    result = chat.send_one_shot_chat_interactive(
        "hello",
        tmp_path,
    )

    assert result.code == 1
    assert capsys.readouterr().err == "one-shot failed password=***\n"
    [event] = read_log_events(project_root=tmp_path, component="chat")
    assert event.error == "one-shot failed password=***"
    assert runtime_secret not in str(event.to_record())


def test_one_shot_failure_survives_broken_exception_renderer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class BrokenMessageError(RuntimeError):
        def __str__(self) -> str:
            raise KeyboardInterrupt

    def fail_reply(*args: object, **kwargs: object) -> str:
        del args, kwargs
        raise BrokenMessageError

    monkeypatch.setattr(chat, "one_shot_reply", fail_reply)

    result = chat.send_one_shot_chat_interactive(
        "hello",
        tmp_path,
    )

    assert result.code == 1
    assert capsys.readouterr().err == "BrokenMessageError\n"
    [event] = read_log_events(project_root=tmp_path, component="chat")
    assert event.error == "BrokenMessageError"


def test_daemon_success_projects_reply_and_memory_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[RuntimeContext] = []

    def succeed_chat(*args: object, **kwargs: object) -> ChatResponsePayload:
        del args, kwargs
        observed.append(current_runtime_context())
        return ChatResponsePayload(
            answer="answer",
            reply="reply",
            thread_id="server-thread",
            evidence_references=(),
            epistemic_status=None,
            memory_update="created=1",
        )

    monkeypatch.setattr(chat.client, "chat", succeed_chat)

    with runtime_context(request_id="request-1", source="outer"):
        result = chat.send_daemon_chat_interactive(
            "hello",
            tmp_path,
            "thread-1",
            turn_id="turn-1",
        )
        assert current_runtime_context() == RuntimeContext(
            request_id="request-1",
            source="outer",
        )

    assert result.code == 0
    assert result.reply == "reply"
    assert result.memory_update == "created=1"
    assert observed == [
        RuntimeContext(
            thread_id="thread-1",
            request_id="request-1",
            turn_id="turn-1",
            source="client",
        )
    ]
    event = read_log_events(
        project_root=tmp_path,
        component="chat",
    )[-1]
    assert event.event == "daemon_chat_completed"
    assert event.thread_id == "server-thread"
    assert event.request_id == "request-1"
    assert event.turn_id == "turn-1"
    assert event.source == "client"


def test_daemon_success_survives_uncertain_completion_audit(
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
            memory_update="",
        )

    monkeypatch.setattr(
        chat.client,
        "chat",
        succeed_chat,
    )
    def drop_audit(*args: object, **kwargs: object) -> None:
        del args, kwargs

    monkeypatch.setattr(chat, "write_chat_audit", drop_audit)

    result = chat.send_daemon_chat_interactive(
        "hello",
        tmp_path,
        "thread-1",
        turn_id="turn-1",
    )

    assert result == chat.InteractiveChatResult(code=0, reply="reply")
    assert read_log_events(project_root=tmp_path, component="chat") == []


def test_one_shot_success_runs_curator_after_reply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    contexts: list[RuntimeContext] = []

    def reply(
        message: str,
        project_root: Path | None,
        thread_id: str = "default",
        *,
        turn_id: str | None = None,
    ) -> str:
        assert project_root == tmp_path
        contexts.append(current_runtime_context())
        calls.append(f"reply:{message}:{thread_id}:{turn_id}")
        return "done"

    def curate(project_root: Path | None) -> None:
        assert project_root == tmp_path
        contexts.append(current_runtime_context())
        calls.append("curator")
        write_log_event(
            "memory",
            "curator_test",
            "curator test",
            project_root=project_root,
        )

    monkeypatch.setattr(chat, "one_shot_reply", reply)
    monkeypatch.setattr(chat, "run_memory_curator", curate)

    with runtime_context(trace_id="trace-1", source="outer"):
        result = chat.send_one_shot_chat_interactive(
            "hello",
            tmp_path,
            "thread-1",
            turn_id="turn-1",
        )
        assert current_runtime_context() == RuntimeContext(
            trace_id="trace-1",
            source="outer",
        )

    assert result.code == 0
    assert result.reply == "done"
    assert calls == ["reply:hello:thread-1:turn-1", "curator"]
    assert contexts == [
        RuntimeContext(
            thread_id="thread-1",
            turn_id="turn-1",
            trace_id="trace-1",
            source="client",
        ),
        RuntimeContext(
            thread_id="thread-1",
            turn_id="turn-1",
            trace_id="trace-1",
            source="client",
        ),
    ]
    event = read_log_events(
        project_root=tmp_path,
        component="memory",
    )[-1]
    assert event.thread_id == "thread-1"
    assert event.turn_id == "turn-1"
    assert event.trace_id == "trace-1"
    assert event.source == "client"


def test_one_shot_success_survives_uncertain_completion_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def reply(*args: object, **kwargs: object) -> str:
        del args, kwargs
        return "done"

    def curate(_project_root: Path | None) -> None:
        calls.append("curator")

    monkeypatch.setattr(
        chat,
        "one_shot_reply",
        reply,
    )
    monkeypatch.setattr(
        chat,
        "run_memory_curator",
        curate,
    )
    def drop_audit(*args: object, **kwargs: object) -> None:
        del args, kwargs

    monkeypatch.setattr(chat, "write_chat_audit", drop_audit)

    result = chat.send_one_shot_chat_interactive(
        "hello",
        tmp_path,
        "thread-1",
        turn_id="turn-1",
    )

    assert result == chat.InteractiveChatResult(code=0, reply="done")
    assert calls == ["curator"]
