from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from _pytest.capture import CaptureFixture
from _pytest.monkeypatch import MonkeyPatch

from nuself.cli.repl import activity
from nuself.cli.repl.activity import (
    captured_interactive_activity_events,
    read_interactive_activity_events,
    run_live_activity_send,
    visible_interactive_activity_events,
)
from nuself.cli.repl.types import InteractiveChatResult
from nuself.logs import (
    InteractiveLogCursor,
    LogComponent,
    LogEvent,
    read_log_events,
    write_log_event,
)
from nuself.runtime.execution import OwnedCall, current_cancellation


def _event(
    component: str,
    event: str,
    *,
    status: str | None = None,
) -> LogEvent:
    return LogEvent(
        time="2026-07-28T00:00:00+00:00",
        level="info",
        component=cast(LogComponent, component),
        event=event,
        message=event,
        status=status,
    )


def _successful_send(
    _message: str,
    _thread_id: str,
    _turn_id: str | None,
) -> InteractiveChatResult:
    return InteractiveChatResult(code=0, reply="done")


def _mark_presented(
    events: list[LogEvent],
    *,
    printed_logs: bool,
) -> bool:
    del events
    return True if not printed_logs else printed_logs


def test_activity_projection_keeps_capture_and_visibility_distinct() -> None:
    tool = _event("chat", "service_tool_called")
    background_chat = _event("chat", "one_shot_chat_completed")
    approval = _event("chat", "tool.activity", status="pending")
    background_reason = _event("reasoning", "advance_completed")

    events = [tool, background_chat, approval, background_reason]

    assert visible_interactive_activity_events(events) == [tool, approval]
    assert captured_interactive_activity_events(events) == [
        tool,
        background_chat,
        approval,
    ]


def test_daemon_failures_are_visible_without_capturing_other_domains() -> None:
    daemon_failure = _event("daemon", "socket_failed", status="error")
    memory_failure = _event("memory", "curator_failed", status="error")

    events = [daemon_failure, memory_failure]

    assert visible_interactive_activity_events(events) == [daemon_failure]
    assert captured_interactive_activity_events(events) == [daemon_failure]


def test_registered_chat_lifecycle_events_are_visible() -> None:
    events = [
        _event("chat", "turn.started", status="started"),
        _event("chat", "turn.completed", status="completed"),
        _event("chat", "turn.reused", status="completed"),
        _event("chat", "turn.failed", status="error"),
    ]

    assert visible_interactive_activity_events(events) == events


def test_removed_chat_lifecycle_aliases_are_not_visible() -> None:
    events = [
        _event("chat", name, status="completed")
        for name in (
            "turn_started",
            "turn_completed",
            "turn_reused",
            "turn_failed",
        )
    ]

    assert visible_interactive_activity_events(events) == []


def test_live_send_drains_and_closes_daemon_subscription(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    event = _event("chat", "service_tool_called")
    pending = [event]
    closed: list[str] = []
    presented: list[LogEvent] = []

    def open_activity(
        _turn_id: str,
        *,
        project_root: Path | None = None,
    ) -> str:
        del project_root
        return "sub-1"

    monkeypatch.setattr(
        activity.client,
        "open_activity",
        open_activity,
    )

    def next_activity(*_args: object, **_kwargs: object) -> tuple[LogEvent, ...]:
        if not pending:
            return ()
        return (pending.pop(),)

    monkeypatch.setattr(activity.client, "next_activity", next_activity)

    def close_activity(
        subscription_id: str,
        *,
        project_root: Path | None = None,
    ) -> bool:
        del project_root
        closed.append(subscription_id)
        return True

    monkeypatch.setattr(activity.client, "close_activity", close_activity)

    def fail_file_read(
        project_root: Path | None,
        log_cursor: InteractiveLogCursor,
        *,
        turn_id: str | None = None,
    ) -> list[LogEvent]:
        del project_root, log_cursor, turn_id
        pytest.fail("daemon activity must not fall back while transport is healthy")

    def present(
        events: list[LogEvent],
        *,
        printed_logs: bool,
    ) -> bool:
        presented.extend(events)
        return printed_logs or bool(events)

    result, captured, printed = run_live_activity_send(
        _successful_send,
        "hello",
        "default",
        "turn-1",
        tmp_path,
        InteractiveLogCursor.from_project(tmp_path),
        printed_logs=False,
        daemon_activity=True,
        poll_interval_seconds=0,
        read_events=fail_file_read,
        present_events=present,
    )

    assert result.reply == "done"
    assert captured == [event]
    assert presented == [event]
    assert printed is True
    assert closed == ["sub-1"]


def test_live_send_falls_back_when_activity_open_fails(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    event = _event("chat", "turn_completed")
    reads = 0

    def fail_open(
        turn_id: str,
        *,
        project_root: Path | None = None,
    ) -> str:
        del turn_id, project_root
        raise activity.client.DaemonConnectionError(
            "activity unavailable",
            phase="connect",
            request_id="activity-open-1",
        )

    def read_events(
        project_root: Path | None,
        log_cursor: InteractiveLogCursor,
        *,
        turn_id: str | None = None,
    ) -> list[LogEvent]:
        del project_root, log_cursor, turn_id
        nonlocal reads
        reads += 1
        return [event] if reads == 1 else []

    monkeypatch.setattr(activity.client, "open_activity", fail_open)

    result, captured, _printed = run_live_activity_send(
        _successful_send,
        "hello",
        "default",
        "turn-1",
        tmp_path,
        InteractiveLogCursor.from_project(tmp_path),
        printed_logs=False,
        daemon_activity=True,
        poll_interval_seconds=0,
        read_events=read_events,
        present_events=_mark_presented,
    )

    assert result.code == 0
    assert captured == [event]
    degraded = read_log_events(
        project_root=tmp_path,
        component="chat",
    )[-1]
    assert degraded.event == "activity_transport_degraded"
    assert degraded.error == "activity unavailable"
    assert degraded.metadata == {
        "stage": "open",
        "error_kind": "connection",
        "has_subscription": False,
        "failure_phase": "connect",
        "retryable": True,
        "request_may_have_completed": False,
    }


def test_live_send_observes_poll_failure_and_uses_file_fallback(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    release = threading.Event()
    cursor = InteractiveLogCursor.from_project(tmp_path)
    delivered = write_log_event(
        "chat",
        "service_tool_called",
        "tool called",
        project_root=tmp_path,
        turn_id="turn-poll",
    )
    recovered = write_log_event(
        "chat",
        "turn_completed",
        "turn completed",
        project_root=tmp_path,
        turn_id="turn-poll",
    )
    polls = 0
    closed: list[str] = []

    def wait_send(
        _message: str,
        _thread_id: str,
        _turn_id: str | None,
    ) -> InteractiveChatResult:
        release.wait(1)
        return InteractiveChatResult(code=0, reply="done")

    def open_activity(
        turn_id: str,
        *,
        project_root: Path | None = None,
    ) -> str:
        del turn_id, project_root
        return "sub-poll"

    def fail_poll(
        *args: object,
        **kwargs: object,
    ) -> tuple[LogEvent, ...]:
        nonlocal polls
        del args, kwargs
        polls += 1
        if polls == 1:
            return (delivered,)
        release.set()
        raise activity.client.DaemonConnectionError(
            "poll timed out",
            phase="receive",
            request_id="activity-poll-1",
        )

    def close_activity(
        subscription_id: str,
        *,
        project_root: Path | None = None,
    ) -> bool:
        del project_root
        closed.append(subscription_id)
        return True

    monkeypatch.setattr(activity.client, "open_activity", open_activity)
    monkeypatch.setattr(activity.client, "next_activity", fail_poll)
    monkeypatch.setattr(activity.client, "close_activity", close_activity)

    result, captured, _printed = run_live_activity_send(
        wait_send,
        "hello",
        "default",
        "turn-poll",
        tmp_path,
        cursor,
        printed_logs=False,
        daemon_activity=True,
        poll_interval_seconds=0,
        read_events=read_interactive_activity_events,
        present_events=_mark_presented,
    )

    assert result.reply == "done"
    assert captured == [delivered, recovered]
    assert captured.count(delivered) == 1
    assert closed == ["sub-poll"]
    degraded = read_log_events(
        project_root=tmp_path,
        component="chat",
    )[-1]
    assert degraded.event == "activity_transport_degraded"
    assert degraded.metadata == {
        "stage": "poll",
        "error_kind": "connection",
        "has_subscription": True,
        "failure_phase": "receive",
        "retryable": True,
        "request_may_have_completed": True,
    }


def test_live_send_recovers_file_events_when_final_drain_fails(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    event = _event("chat", "turn_completed")
    closed: list[str] = []

    def open_activity(
        turn_id: str,
        *,
        project_root: Path | None = None,
    ) -> str:
        del turn_id, project_root
        return "sub-drain"

    def fail_drain(
        *args: object,
        **kwargs: object,
    ) -> tuple[LogEvent, ...]:
        del args
        if kwargs.get("limit") != 256:
            return ()
        raise activity.client.DaemonApplicationError(
            "subscription expired"
        )

    def close_activity(
        subscription_id: str,
        *,
        project_root: Path | None = None,
    ) -> bool:
        del project_root
        closed.append(subscription_id)
        return True

    def read_events(
        project_root: Path | None,
        log_cursor: InteractiveLogCursor,
        *,
        turn_id: str | None = None,
    ) -> list[LogEvent]:
        del project_root, log_cursor, turn_id
        return [event]

    monkeypatch.setattr(activity.client, "open_activity", open_activity)
    monkeypatch.setattr(activity.client, "next_activity", fail_drain)
    monkeypatch.setattr(activity.client, "close_activity", close_activity)

    result, captured, _printed = run_live_activity_send(
        _successful_send,
        "hello",
        "default",
        "turn-drain",
        tmp_path,
        InteractiveLogCursor.from_project(tmp_path),
        printed_logs=False,
        daemon_activity=True,
        poll_interval_seconds=0,
        read_events=read_events,
        present_events=_mark_presented,
    )

    assert result.reply == "done"
    assert captured == [event]
    assert closed == ["sub-drain"]
    degraded = read_log_events(
        project_root=tmp_path,
        component="chat",
    )[-1]
    assert degraded.event == "activity_transport_degraded"
    assert degraded.metadata == {
        "stage": "drain",
        "error_kind": "application",
        "has_subscription": True,
    }


def test_live_send_observes_close_failure_without_changing_result(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    def open_activity(
        turn_id: str,
        *,
        project_root: Path | None = None,
    ) -> str:
        del turn_id, project_root
        return "sub-close"

    def next_activity(
        *args: object,
        **kwargs: object,
    ) -> tuple[LogEvent, ...]:
        del args, kwargs
        return ()

    def fail_close(
        subscription_id: str,
        *,
        project_root: Path | None = None,
    ) -> bool:
        del subscription_id, project_root
        raise activity.client.DaemonConnectionError(
            "close disconnected",
            phase="send",
            request_id="activity-close-1",
        )

    monkeypatch.setattr(activity.client, "open_activity", open_activity)
    monkeypatch.setattr(activity.client, "next_activity", next_activity)
    monkeypatch.setattr(activity.client, "close_activity", fail_close)

    result, captured, printed = run_live_activity_send(
        _successful_send,
        "hello",
        "default",
        "turn-close",
        tmp_path,
        InteractiveLogCursor.from_project(tmp_path),
        printed_logs=False,
        daemon_activity=True,
        poll_interval_seconds=0,
        read_events=read_interactive_activity_events,
        present_events=_mark_presented,
    )

    assert result.reply == "done"
    assert captured == []
    assert printed is False
    degraded = read_log_events(
        project_root=tmp_path,
        component="chat",
    )[-1]
    assert degraded.event == "activity_transport_degraded"
    assert degraded.metadata == {
        "stage": "close",
        "error_kind": "connection",
        "has_subscription": True,
        "failure_phase": "send",
        "retryable": True,
        "request_may_have_completed": True,
    }


def test_activity_degradation_diagnostic_failure_cannot_block_chat(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    def fail_open(
        turn_id: str,
        *,
        project_root: Path | None = None,
    ) -> str:
        del turn_id, project_root
        raise activity.client.DaemonConnectionError(
            "activity unavailable",
            phase="connect",
        )

    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("diagnostic store unavailable")

    def read_nothing(
        project_root: Path | None,
        log_cursor: InteractiveLogCursor,
        *,
        turn_id: str | None = None,
    ) -> list[LogEvent]:
        del project_root, log_cursor, turn_id
        return []

    monkeypatch.setattr(activity.client, "open_activity", fail_open)
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
        result, captured, printed = run_live_activity_send(
            _successful_send,
            "hello",
            "default",
            "turn-open-warning",
            tmp_path,
            InteractiveLogCursor.from_project(tmp_path),
            printed_logs=False,
            daemon_activity=True,
            poll_interval_seconds=0,
            read_events=read_nothing,
            present_events=_mark_presented,
        )

    assert result.reply == "done"
    assert captured == []
    assert printed is False


def test_live_send_reports_callback_exception_without_escaping(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    def fail_send(
        message: str,
        thread_id: str,
        turn_id: str | None,
    ) -> InteractiveChatResult:
        del message, thread_id, turn_id
        raise ValueError("send exploded")

    def read_nothing(
        project_root: Path | None,
        log_cursor: InteractiveLogCursor,
        *,
        turn_id: str | None = None,
    ) -> list[LogEvent]:
        del project_root, log_cursor, turn_id
        return []

    result, captured, printed = run_live_activity_send(
        fail_send,
        "hello",
        "default",
        "turn-1",
        tmp_path,
        InteractiveLogCursor.from_project(tmp_path),
        printed_logs=False,
        daemon_activity=False,
        poll_interval_seconds=0,
        read_events=read_nothing,
        present_events=_mark_presented,
    )

    assert result.code == 1
    assert captured == []
    assert printed is False
    assert "chat turn failed: send exploded" in capsys.readouterr().err
    failure = read_log_events(
        project_root=tmp_path,
        component="chat",
    )[-1]
    assert failure.event == "interactive_send_failed"
    assert failure.level == "error"
    assert failure.status == "error"
    assert failure.error == "send exploded"
    assert failure.metadata == {}


def test_live_send_redacts_callback_exception_from_terminal_and_audit(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    secret = "sk-live-send-secret-value"

    def fail_send(
        message: str,
        thread_id: str,
        turn_id: str | None,
    ) -> InteractiveChatResult:
        del message, thread_id, turn_id
        raise ValueError(f"provider rejected api_key={secret}")

    def read_nothing(
        project_root: Path | None,
        log_cursor: InteractiveLogCursor,
        *,
        turn_id: str | None = None,
    ) -> list[LogEvent]:
        del project_root, log_cursor, turn_id
        return []

    result, _, _ = run_live_activity_send(
        fail_send,
        "hello",
        "default",
        "turn-sensitive",
        tmp_path,
        InteractiveLogCursor.from_project(tmp_path),
        printed_logs=False,
        daemon_activity=False,
        poll_interval_seconds=0,
        read_events=read_nothing,
        present_events=_mark_presented,
    )

    assert result.code == 1
    terminal = capsys.readouterr().err
    assert secret not in terminal
    assert "api_key=***" in terminal
    failure = read_log_events(
        project_root=tmp_path,
        component="chat",
    )[-1]
    assert failure.error is not None
    assert secret not in failure.error
    assert "api_key=***" in failure.error


def test_send_failure_diagnostic_storage_loss_keeps_repl_failure(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    def fail_send(
        message: str,
        thread_id: str,
        turn_id: str | None,
    ) -> InteractiveChatResult:
        del message, thread_id, turn_id
        raise ValueError("send exploded")

    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("diagnostic store unavailable")

    def read_nothing(
        project_root: Path | None,
        log_cursor: InteractiveLogCursor,
        *,
        turn_id: str | None = None,
    ) -> list[LogEvent]:
        del project_root, log_cursor, turn_id
        return []

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
        result, captured, printed = run_live_activity_send(
            fail_send,
            "hello",
            "default",
            "turn-send-warning",
            tmp_path,
            InteractiveLogCursor.from_project(tmp_path),
            printed_logs=False,
            daemon_activity=False,
            poll_interval_seconds=0,
            read_events=read_nothing,
            present_events=_mark_presented,
        )

    assert result.code == 1
    assert result.retryable is False
    assert captured == []
    assert printed is False
    assert "chat turn failed: send exploded" in capsys.readouterr().err


@pytest.mark.parametrize(
    "control",
    [
        KeyboardInterrupt("interrupt send"),
        SystemExit(7),
    ],
)
def test_send_control_exception_is_reraised_after_close_without_drain(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    control: BaseException,
) -> None:
    root_cause = RuntimeError("control root cause")
    closed: list[str] = []
    final_drain_called = False

    def fail_send(
        message: str,
        thread_id: str,
        turn_id: str | None,
    ) -> InteractiveChatResult:
        del message, thread_id, turn_id
        raise control from root_cause

    def open_activity(
        turn_id: str,
        *,
        project_root: Path | None = None,
    ) -> str:
        del turn_id, project_root
        return "sub-control"

    def next_activity(
        *args: object,
        **kwargs: object,
    ) -> tuple[LogEvent, ...]:
        nonlocal final_drain_called
        del args
        if kwargs.get("limit") == 256:
            final_drain_called = True
        return ()

    def close_activity(
        subscription_id: str,
        *,
        project_root: Path | None = None,
    ) -> bool:
        del project_root
        closed.append(subscription_id)
        return True

    monkeypatch.setattr(activity.client, "open_activity", open_activity)
    monkeypatch.setattr(activity.client, "next_activity", next_activity)
    monkeypatch.setattr(activity.client, "close_activity", close_activity)

    with pytest.raises(type(control)) as captured:
        run_live_activity_send(
            fail_send,
            "hello",
            "default",
            "turn-control",
            tmp_path,
            InteractiveLogCursor.from_project(tmp_path),
            printed_logs=False,
            daemon_activity=True,
            poll_interval_seconds=0,
            read_events=read_interactive_activity_events,
            present_events=_mark_presented,
        )

    assert captured.value is control
    assert captured.value.__cause__ is root_cause
    assert captured.value.__traceback__ is not None
    assert final_drain_called is False
    assert closed == ["sub-control"]
    assert read_log_events(
        project_root=tmp_path,
        component="chat",
    ) == []


def test_live_send_closes_subscription_on_unexpected_poll_failure(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    release = threading.Event()
    closed: list[str] = []

    def wait_send(
        _message: str,
        _thread_id: str,
        _turn_id: str | None,
    ) -> InteractiveChatResult:
        release.wait(1)
        return InteractiveChatResult(code=0)

    def fail_next(*_args: object, **_kwargs: object) -> tuple[LogEvent, ...]:
        release.set()
        raise ValueError("unexpected poll failure")

    def close_activity(
        subscription_id: str,
        *,
        project_root: Path | None = None,
    ) -> bool:
        del project_root
        closed.append(subscription_id)
        return True

    def open_activity(
        _turn_id: str,
        *,
        project_root: Path | None = None,
    ) -> str:
        del project_root
        return "sub-1"

    def read_nothing(
        project_root: Path | None,
        log_cursor: InteractiveLogCursor,
        *,
        turn_id: str | None = None,
    ) -> list[LogEvent]:
        del project_root, log_cursor, turn_id
        return []

    monkeypatch.setattr(activity.client, "open_activity", open_activity)
    monkeypatch.setattr(activity.client, "next_activity", fail_next)
    monkeypatch.setattr(activity.client, "close_activity", close_activity)

    with pytest.raises(ValueError, match="unexpected poll failure"):
        run_live_activity_send(
            wait_send,
            "hello",
            "default",
            "turn-1",
            tmp_path,
            InteractiveLogCursor.from_project(tmp_path),
            printed_logs=False,
            daemon_activity=True,
            poll_interval_seconds=0,
            read_events=read_nothing,
            present_events=_mark_presented,
        )

    assert closed == ["sub-1"]


def test_live_send_reaps_call_before_reraising_presenter_failure(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    release = threading.Event()
    finished = threading.Event()

    def wait_send(
        _message: str,
        _thread_id: str,
        _turn_id: str | None,
    ) -> InteractiveChatResult:
        release.wait(1)
        finished.set()
        return InteractiveChatResult(code=0)

    def next_activity(*_args: object, **_kwargs: object) -> tuple[LogEvent, ...]:
        return (_event("chat", "service_tool_called"),)

    def fail_present(
        events: list[LogEvent],
        *,
        printed_logs: bool,
    ) -> bool:
        del events, printed_logs
        release.set()
        raise RuntimeError("renderer unavailable")

    def open_activity(
        _turn_id: str,
        *,
        project_root: Path | None = None,
    ) -> str:
        del project_root
        return "sub-presenter"

    def close_activity(
        _subscription_id: str,
        *,
        project_root: Path | None = None,
    ) -> bool:
        del project_root
        return True

    monkeypatch.setattr(activity.client, "next_activity", next_activity)
    monkeypatch.setattr(activity.client, "open_activity", open_activity)
    monkeypatch.setattr(activity.client, "close_activity", close_activity)

    with pytest.raises(RuntimeError, match="renderer unavailable"):
        run_live_activity_send(
            wait_send,
            "hello",
            "default",
            "turn-presenter",
            tmp_path,
            InteractiveLogCursor.from_project(tmp_path),
            printed_logs=False,
            daemon_activity=True,
            poll_interval_seconds=0,
            read_events=read_interactive_activity_events,
            present_events=fail_present,
        )

    assert finished.is_set()


def test_live_send_closes_subscription_when_call_start_fails(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    closed: list[str] = []
    start_error = RuntimeError("thread unavailable")

    def open_activity(
        _turn_id: str,
        *,
        project_root: Path | None = None,
    ) -> str:
        del project_root
        return "sub-start"

    def close_activity(
        subscription_id: str,
        *,
        project_root: Path | None = None,
    ) -> bool:
        del project_root
        closed.append(subscription_id)
        return True

    def fail_start(_call: OwnedCall[InteractiveChatResult]) -> bool:
        raise start_error

    monkeypatch.setattr(activity.client, "open_activity", open_activity)
    monkeypatch.setattr(activity.client, "close_activity", close_activity)
    monkeypatch.setattr(activity.OwnedCall, "start", fail_start)

    with pytest.raises(RuntimeError) as captured:
        run_live_activity_send(
            _successful_send,
            "hello",
            "default",
            "turn-start",
            tmp_path,
            InteractiveLogCursor.from_project(tmp_path),
            printed_logs=False,
            daemon_activity=True,
            poll_interval_seconds=0,
            read_events=read_interactive_activity_events,
            present_events=_mark_presented,
        )

    assert captured.value is start_error
    assert closed == ["sub-start"]


def test_live_send_reaps_call_before_reraising_main_control(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    release = threading.Event()
    finished = threading.Event()
    control = KeyboardInterrupt("stop polling")

    def wait_send(
        _message: str,
        _thread_id: str,
        _turn_id: str | None,
    ) -> InteractiveChatResult:
        release.wait(1)
        finished.set()
        return InteractiveChatResult(code=0)

    def interrupt_poll(
        *_args: object,
        **_kwargs: object,
    ) -> tuple[LogEvent, ...]:
        release.set()
        raise control

    def open_activity(
        _turn_id: str,
        *,
        project_root: Path | None = None,
    ) -> str:
        del project_root
        return "sub-control"

    def close_activity(
        _subscription_id: str,
        *,
        project_root: Path | None = None,
    ) -> bool:
        del project_root
        return True

    monkeypatch.setattr(activity.client, "next_activity", interrupt_poll)
    monkeypatch.setattr(activity.client, "open_activity", open_activity)
    monkeypatch.setattr(activity.client, "close_activity", close_activity)

    with pytest.raises(KeyboardInterrupt) as captured:
        run_live_activity_send(
            wait_send,
            "hello",
            "default",
            "turn-control",
            tmp_path,
            InteractiveLogCursor.from_project(tmp_path),
            printed_logs=False,
            daemon_activity=True,
            poll_interval_seconds=0,
            read_events=read_interactive_activity_events,
            present_events=_mark_presented,
        )

    assert captured.value is control
    assert finished.is_set()


def test_live_send_reap_ignores_second_interrupt_during_cleanup(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    started = threading.Event()
    released = threading.Event()
    primary = KeyboardInterrupt("cancel turn")

    def send(
        _message: str,
        _thread_id: str,
        _turn_id: str | None,
    ) -> InteractiveChatResult:
        cancellation = current_cancellation()
        assert cancellation is not None
        cancellation.register(released.set)
        started.set()
        released.wait()
        return InteractiveChatResult(code=0)

    def interrupt_poll(*_args: object, **_kwargs: object) -> tuple[LogEvent, ...]:
        assert started.wait(timeout=1)
        raise primary

    original_wait = cast(
        Callable[
            [OwnedCall[InteractiveChatResult], float | None],
            bool,
        ],
        activity.OwnedCall.wait,  # pyright: ignore[reportUnknownMemberType]
    )
    wait_calls = 0

    def interrupt_first_cleanup_wait(
        self: activity.OwnedCall[InteractiveChatResult],
        timeout: float | None = None,
    ) -> bool:
        nonlocal wait_calls
        wait_calls += 1
        if wait_calls == 1:
            raise KeyboardInterrupt("second interrupt")
        return original_wait(self, timeout)

    monkeypatch.setattr(activity.client, "next_activity", interrupt_poll)
    monkeypatch.setattr(activity.OwnedCall, "wait", interrupt_first_cleanup_wait)

    def open_activity(
        turn_id: str,
        *,
        project_root: Path | None = None,
    ) -> str:
        del turn_id, project_root
        return "sub-control"

    def close_activity(
        subscription_id: str,
        *,
        project_root: Path | None = None,
    ) -> bool:
        del subscription_id, project_root
        return True

    monkeypatch.setattr(
        activity.client,
        "open_activity",
        open_activity,
    )
    monkeypatch.setattr(
        activity.client,
        "close_activity",
        close_activity,
    )

    with pytest.raises(KeyboardInterrupt) as captured:
        run_live_activity_send(
            send,
            "hello",
            "default",
            "turn-control",
            tmp_path,
            InteractiveLogCursor.from_project(tmp_path),
            printed_logs=False,
            daemon_activity=True,
            poll_interval_seconds=0,
            read_events=read_interactive_activity_events,
            present_events=_mark_presented,
        )

    assert captured.value is primary
    assert released.is_set()
    assert wait_calls >= 2


def test_live_send_closes_subscription_when_presenter_fails(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    closed: list[str] = []

    def open_activity(
        turn_id: str,
        *,
        project_root: Path | None = None,
    ) -> str:
        del turn_id, project_root
        return "sub-1"

    def next_activity(*_args: object, **_kwargs: object) -> tuple[LogEvent, ...]:
        return (_event("chat", "service_tool_called"),)

    def close_activity(
        subscription_id: str,
        *,
        project_root: Path | None = None,
    ) -> bool:
        del project_root
        closed.append(subscription_id)
        return True

    def fail_present(
        events: list[LogEvent],
        *,
        printed_logs: bool,
    ) -> bool:
        del events, printed_logs
        raise RuntimeError("renderer unavailable")

    monkeypatch.setattr(activity.client, "open_activity", open_activity)
    monkeypatch.setattr(activity.client, "next_activity", next_activity)
    monkeypatch.setattr(activity.client, "close_activity", close_activity)

    with pytest.raises(RuntimeError, match="renderer unavailable"):
        run_live_activity_send(
            _successful_send,
            "hello",
            "default",
            "turn-1",
            tmp_path,
            InteractiveLogCursor.from_project(tmp_path),
            printed_logs=False,
            daemon_activity=True,
            poll_interval_seconds=0,
            read_events=read_interactive_activity_events,
            present_events=fail_present,
        )

    assert closed == ["sub-1"]
