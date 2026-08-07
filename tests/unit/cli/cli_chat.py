from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

from nuself.agent.chat.types import ChatResult
from nuself.application.lifecycle import open_application_runtime, use_application_runtime
from nuself.cli import chat
from nuself.conversation import CompletedTurn
from nuself.daemon.client import (
    DaemonApplicationError,
    DaemonConnectionError,
)
from nuself.daemon.payloads import (
    ChatToolEffectPayload,
    ChatResponsePayload,
)
from nuself.log.reader import read_log_events
from nuself.log.store import write_log_event
from nuself.runtime.context import (
    RuntimeContext,
    current_runtime_context,
    runtime_context,
)
from nuself.runtime.execution import CancellationToken, use_cancellation
from nuself.runtime.feature.approval import (
    ApprovalEffectDecision,
    ApprovalEffectRequest,
    ApprovalEffectResolution,
)
from nuself.config.scope import resolve_scope


@pytest.fixture(autouse=True)
def _application_runtime(tmp_path: Path):  # pyright: ignore[reportUnusedFunction]
    runtime = open_application_runtime(tmp_path)
    try:
        with use_application_runtime(runtime):
            yield
    finally:
        runtime.close()


def _chat_result(
    answer: str = "done",
    *,
    conversation_id: str = "thread-1",
    turn_id: str | None = "turn-1",
) -> ChatResult:
    return ChatResult(
        answer=answer,
        conversation_id=conversation_id,
        completed_turn=CompletedTurn(
            conversation_id=conversation_id,
            start_index=0,
            end_index=2,
            user_content="hello",
            assistant_content=answer,
            turn_id=turn_id,
        ),
    )


@pytest.mark.parametrize("approved", [True, False])
def test_daemon_chat_transports_exact_tool_effect_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    approved: bool,
) -> None:
    request = ApprovalEffectRequest(
        component="memory",
        operation="memory_create",
        action="create",
        resource="memory",
        risk="reversible",
        summary="Create exact memory",
    )
    resolutions: list[object] = []

    def respond(*args: object, **kwargs: object):
        del args
        resolutions.append(kwargs.get("effect_resolution"))
        if len(resolutions) == 1:
            return ChatToolEffectPayload("default", request)
        resolution = kwargs.get("effect_resolution")
        assert isinstance(resolution, ApprovalEffectResolution)
        assert resolution.request == request
        assert resolution.decision.approved is approved
        return ChatResponsePayload(
            answer="saved" if approved else "not saved",
            conversation_id="default",
            evidence_references=(),
            epistemic_status="grounded",
        )

    monkeypatch.setattr(chat.client, "chat", respond)

    challenge = chat.send_daemon_chat_interactive(
        "remember this",
        tmp_path,
        turn_id="turn-approval",
    )
    assert challenge.tool_effect_request == request
    decision = (
        ApprovalEffectDecision(
            True,
            approver="tester",
            input_kind="affirmative",
        )
        if approved
        else ApprovalEffectDecision(False, input_kind="declined")
    )
    result = chat.send_daemon_chat_interactive(
        "remember this",
        tmp_path,
        turn_id="turn-approval",
        effect_resolution=ApprovalEffectResolution(request, decision),
    )

    assert result.reply == ("saved" if approved else "not saved")
    assert resolutions[0] is None
    assert resolutions[1] is not None


class _StubConversationRuntime:
    def __init__(
        self,
        respond: Callable[[str, str, str | None], ChatResult],
        compress: Callable[[str], None] | None = None,
    ) -> None:
        self._respond = respond
        self._compress = compress or self._ignore_compression

    @staticmethod
    def _ignore_compression(_conversation_id: str) -> None:
        return None

    def respond(
        self,
        message: str,
        *,
        conversation_id: str,
        turn_id: str | None,
    ) -> ChatResult:
        return self._respond(message, conversation_id, turn_id)

    def compress_conversation(self, conversation_id: str) -> None:
        self._compress(conversation_id)


def _use_stub_runtime(
    monkeypatch: pytest.MonkeyPatch,
    runtime: _StubConversationRuntime,
) -> None:
    def compose(*args: object, **kwargs: object) -> object:
        del args, kwargs
        return runtime

    monkeypatch.setattr(chat, "compose_conversation_runtime", compose)


def test_daemon_chat_preserves_user_timeout_in_workspace_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_root = tmp_path / "user"
    workspace = tmp_path / "workspace"
    user_root.mkdir()
    (workspace / ".nuself").mkdir(parents=True)
    (user_root / "config.yaml").write_text(
        "chat:\n  request_timeout_seconds: 37\n",
        encoding="utf-8",
    )
    scope = resolve_scope(
        workspace=workspace,
        environ={"NUSELF_HOME": str(user_root)},
    )
    captured_timeout = 0.0

    def respond(*args: object, **kwargs: object) -> ChatResponsePayload:
        del args
        nonlocal captured_timeout
        timeout = kwargs["timeout"]
        assert isinstance(timeout, (int, float))
        captured_timeout = float(timeout)
        return ChatResponsePayload(
            answer="done",
            conversation_id="default",
            evidence_references=(),
            epistemic_status=None,
        )

    monkeypatch.setattr(chat.client, "chat", respond)
    runtime = open_application_runtime(scope)
    try:
        with use_application_runtime(runtime):
            result = chat.send_daemon_chat_interactive(
                "hello",
                scope.root,
            )
    finally:
        runtime.close()

    assert result.reply == "done"
    assert captured_timeout == 37


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
            conversation_id="thread-1",
            request_id="request-1",
            turn_id="turn-1",
            job_id="job-1",
            trace_id="trace-1",
            source="client",
        )
    ]


def test_cancelled_daemon_failure_is_not_presented(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_chat(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise DaemonConnectionError("cancelled socket")

    monkeypatch.setattr(chat.client, "chat", fail_chat)
    cancellation = CancellationToken()
    cancellation.cancel()

    with use_cancellation(cancellation):
        result = chat.send_daemon_chat_interactive("hello", tmp_path)

    assert result.code == 130
    assert result.error is None
    assert capsys.readouterr().err == ""


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
    assert event.conversation_id == "thread-1"
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

    monkeypatch.setattr(chat, "compose_conversation_runtime", fail_reply)

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

    monkeypatch.setattr(chat, "compose_conversation_runtime", fail_reply)

    result = chat.send_one_shot_chat_interactive(
        "hello",
        tmp_path,
    )

    assert result.code == 1
    assert capsys.readouterr().err == "BrokenMessageError\n"
    [event] = read_log_events(project_root=tmp_path, component="chat")
    assert event.error == "BrokenMessageError"


def test_daemon_success_projects_answer_as_reply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[RuntimeContext] = []

    def succeed_chat(*args: object, **kwargs: object) -> ChatResponsePayload:
        del args, kwargs
        observed.append(current_runtime_context())
        return ChatResponsePayload(
            answer="reply",
            conversation_id="server-thread",
            evidence_references=(),
            epistemic_status=None,
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
    assert observed == [
        RuntimeContext(
            conversation_id="thread-1",
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
    assert event.conversation_id == "server-thread"
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
            answer="reply",
            conversation_id="thread-1",
            evidence_references=(),
            epistemic_status=None,
        )

    monkeypatch.setattr(
        chat.client,
        "chat",
        succeed_chat,
    )
    def drop_audit(*args: object, **kwargs: object) -> None:
        del args, kwargs

    monkeypatch.setattr(chat, "CHAT_AUDIT", SimpleNamespace(write=drop_audit))

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
        conversation_id: str,
        turn_id: str | None,
    ) -> ChatResult:
        contexts.append(current_runtime_context())
        calls.append(f"reply:{message}:{conversation_id}:{turn_id}")
        return _chat_result(conversation_id=conversation_id, turn_id=turn_id)

    def curate(project_root: Path | None, observation_id: str) -> None:
        assert project_root == tmp_path
        assert observation_id.startswith("obs_")
        contexts.append(current_runtime_context())
        calls.append("curator")
        write_log_event(
            "memory",
            "curator_test",
            "curator test",
            project_root=project_root,
        )

    _use_stub_runtime(monkeypatch, _StubConversationRuntime(reply))
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
            conversation_id="thread-1",
            turn_id="turn-1",
            trace_id="trace-1",
            source="client",
        ),
        RuntimeContext(
            conversation_id="thread-1",
            turn_id="turn-1",
            trace_id="trace-1",
            source="client",
        ),
    ]
    event = read_log_events(
        project_root=tmp_path,
        component="memory",
    )[-1]
    assert event.conversation_id == "thread-1"
    assert event.turn_id == "turn-1"
    assert event.trace_id == "trace-1"
    assert event.source == "client"


def test_one_shot_reuses_runtime_for_after_reply_compression(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compositions = 0
    compressed: list[str] = []

    runtime = _StubConversationRuntime(
        lambda message, conversation_id, turn_id: _chat_result(),
        compressed.append,
    )

    def compose(*args: object, **kwargs: object) -> object:
        del args, kwargs
        nonlocal compositions
        compositions += 1
        return runtime

    monkeypatch.setattr(chat, "compose_conversation_runtime", compose)

    def skip_curator(
        project_root: Path | None,
        observation_id: str,
    ) -> None:
        del project_root, observation_id

    monkeypatch.setattr(chat, "run_memory_curator", skip_curator)

    result = chat.send_one_shot_chat_interactive("hello", tmp_path)

    assert compositions == 1
    assert compressed == []
    assert result.after_reply is not None
    result.after_reply()
    assert compositions == 1
    assert compressed == ["default"]


def test_one_shot_compresses_only_after_reply_is_presented(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def send(
        message: str,
        project_root: Path | None,
        conversation_id: str = "default",
        *,
        turn_id: str | None = None,
    ) -> chat.InteractiveChatResult:
        del message, project_root, conversation_id, turn_id
        return chat.InteractiveChatResult(
            code=0,
            reply="done",
            after_reply=lambda: calls.append("compress"),
        )

    monkeypatch.setattr(
        chat,
        "send_one_shot_chat_interactive",
        send,
    )

    result = chat.send_one_shot_chat(
        "hello",
        tmp_path,
        print_reply=lambda reply: calls.append(f"reply:{reply}"),
    )

    assert result == 0
    assert calls == ["reply:done", "compress"]


def test_one_shot_success_survives_uncertain_completion_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def reply(
        message: str,
        conversation_id: str,
        turn_id: str | None,
    ) -> ChatResult:
        del message, conversation_id, turn_id
        return _chat_result()

    def curate(_project_root: Path | None, _conversation_id: str) -> None:
        calls.append("curator")

    _use_stub_runtime(monkeypatch, _StubConversationRuntime(reply))
    monkeypatch.setattr(
        chat,
        "run_memory_curator",
        curate,
    )
    def drop_audit(*args: object, **kwargs: object) -> None:
        del args, kwargs

    monkeypatch.setattr(chat, "CHAT_AUDIT", SimpleNamespace(write=drop_audit))

    result = chat.send_one_shot_chat_interactive(
        "hello",
        tmp_path,
        "thread-1",
        turn_id="turn-1",
    )

    assert result == chat.InteractiveChatResult(code=0, reply="done")
    assert calls == ["curator"]
