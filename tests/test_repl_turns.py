from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

import nuself.cli.repl.turns as turns
from nuself.agent.chat import ThreadMessage, ThreadState, ThreadStore
from nuself.cli.repl.session import InteractiveSession
from nuself.cli.repl.turns import send_interactive_chat_turn
from nuself.cli.repl.types import InteractiveChatResult
from nuself.logs import (
    InteractiveLogCursor,
    LogAppendLifecycleError,
    LogEvent,
    read_log_events,
)
from nuself.runtime import (
    RuntimeContext,
    current_runtime_context,
    runtime_context,
)


def _read_no_activity(
    project_root: Path | None,
    log_cursor: InteractiveLogCursor,
    *,
    turn_id: str | None = None,
) -> list[LogEvent]:
    del project_root, log_cursor, turn_id
    return []


def _print_no_activity(events: list[LogEvent]) -> None:
    assert events == []


def test_turn_coordinator_retries_one_stable_context_and_captures_reply(
    tmp_path: Path,
) -> None:
    store = ThreadStore(tmp_path)
    store.save(ThreadState.empty("default"))
    session = InteractiveSession(connected_at=datetime.now(UTC))
    assert session.start_index_for(tmp_path, "default") == 0
    observed: list[RuntimeContext] = []
    turn_ids: list[str | None] = []
    replies: list[str] = []

    def send(
        _message: str,
        thread_id: str,
        turn_id: str | None,
    ) -> InteractiveChatResult:
        observed.append(current_runtime_context())
        turn_ids.append(turn_id)
        if len(observed) == 1:
            return InteractiveChatResult(
                code=1,
                retryable=True,
                error="temporary transport failure",
            )
        store.save(
            ThreadState(
                thread_id=thread_id,
                messages=[
                    ThreadMessage(role="user", content="hello", turn_id=turn_id),
                    ThreadMessage(role="assistant", content="done", turn_id=turn_id),
                ],
            )
        )
        return InteractiveChatResult(code=0, reply="done")

    with runtime_context(
        request_id="ambient-request",
        job_id="ambient-job",
        source="test",
    ):
        result = send_interactive_chat_turn(
            send,
            tmp_path,
            "default",
            "hello",
            session,
            daemon_activity=False,
            max_attempts=2,
            poll_interval_seconds=0,
            read_activity_events=_read_no_activity,
            print_activity_events=_print_no_activity,
            print_reply=replies.append,
        )
        assert current_runtime_context() == RuntimeContext(
            request_id="ambient-request",
            job_id="ambient-job",
            source="test",
        )

    assert result == 0
    assert len(turn_ids) == 2
    assert turn_ids[0] == turn_ids[1]
    assert turn_ids[0] is not None
    assert all(context.thread_id == "default" for context in observed)
    assert all(context.turn_id == turn_ids[0] for context in observed)
    assert all(context.request_id is None for context in observed)
    assert all(context.job_id is None for context in observed)
    assert replies == ["done"]
    assert [message[2] for message in session.transcript_messages(tmp_path, "default")] == [
        "hello",
        "done",
    ]
    retry = next(
        event
        for event in read_log_events(project_root=tmp_path, component="chat")
        if event.event == "turn_retry"
    )
    assert retry.turn_id == turn_ids[0]
    assert retry.thread_id == "default"
    assert retry.source == "client"
    assert retry.request_id is None
    assert retry.job_id is None


def test_turn_retry_continues_when_retry_audit_persistence_is_uncertain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ThreadStore(tmp_path).save(ThreadState.empty("default"))
    session = InteractiveSession(connected_at=datetime.now(UTC))
    attempts = 0
    close_error = OSError("retry audit close failed")

    def send(
        _message: str,
        _thread_id: str,
        _turn_id: str | None,
    ) -> InteractiveChatResult:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return InteractiveChatResult(
                code=1,
                retryable=True,
                error="transport failed",
            )
        return InteractiveChatResult(code=0, reply="done")

    def fail_audit(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise LogAppendLifecycleError(
            primary_error=None,
            rollback_error=None,
            close_error=close_error,
            record_may_have_persisted=True,
        ) from close_error

    monkeypatch.setattr(turns, "write_log_event", fail_audit)

    result = send_interactive_chat_turn(
        send,
        tmp_path,
        "default",
        "hello",
        session,
        daemon_activity=False,
        max_attempts=2,
        poll_interval_seconds=0,
        read_activity_events=_read_no_activity,
        print_activity_events=_print_no_activity,
        print_reply=lambda _reply: None,
    )

    assert result == 0
    assert attempts == 2
    diagnostics = read_log_events(project_root=tmp_path, component="chat")
    assert [event.event for event in diagnostics] == ["audit_projection_failed"]
    assert diagnostics[0].metadata == {"audit_event": "turn_retry"}
