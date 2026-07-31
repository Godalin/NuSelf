"""Incremental activity projection for interactive CLI sessions."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal, Protocol

from nuself.cli.commands.output import print_ansi
from nuself.agent.chat.audit import report_chat_failure
from nuself.cli.repl.types import InteractiveChatResult
from nuself.cli.exit_codes import CliExitCode
from nuself.daemon import client
from nuself.logs import InteractiveLogCursor, LogEvent
from nuself.runtime.context import bind_runtime_context
from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.runtime.execution import OwnedCall
from nuself.tui.render import render_log_event

SendMessage = Callable[[str, str, str | None], InteractiveChatResult]
ActivityTransportStage = Literal["open", "poll", "drain", "close"]


class ActivityReader(Protocol):
    """Read unseen events for one optional turn."""

    def __call__(
        self,
        project_root: Path | None,
        log_cursor: InteractiveLogCursor,
        *,
        turn_id: str | None = None,
    ) -> list[LogEvent]: ...


class ActivityPresenter(Protocol):
    """Project delivered events and return updated output state."""

    def __call__(
        self,
        events: list[LogEvent],
        *,
        printed_logs: bool,
    ) -> bool: ...


def _report_activity_transport_degraded(
    exc: client.DaemonConnectionError | client.DaemonApplicationError,
    *,
    stage: ActivityTransportStage,
    project_root: Path | None,
    subscription_id: str | None,
) -> None:
    metadata: dict[str, object] = {
        "stage": stage,
        "has_subscription": subscription_id is not None,
        "error_kind": (
            "connection"
            if isinstance(exc, client.DaemonConnectionError)
            else "application"
        ),
    }
    if isinstance(exc, client.DaemonConnectionError):
        metadata.update(
            {
                "failure_phase": exc.phase,
                "retryable": exc.retryable,
                "request_may_have_completed": (
                    exc.request_may_have_completed
                ),
            }
        )
    report_chat_failure(
        exc,
        event="activity_transport_degraded",
        project_root=project_root,
        metadata=metadata,
    )


def run_live_activity_send(
    send_message: SendMessage,
    message: str,
    thread_id: str,
    turn_id: str | None,
    project_root: Path | None,
    log_cursor: InteractiveLogCursor,
    *,
    printed_logs: bool,
    daemon_activity: bool,
    poll_interval_seconds: float,
    read_events: ActivityReader,
    present_events: ActivityPresenter,
) -> tuple[InteractiveChatResult, list[LogEvent], bool]:
    """Run one bound send callback while collecting its live activity."""

    subscription_id = _open_activity_subscription(
        turn_id,
        project_root,
        enabled=daemon_activity,
    )
    send_call = OwnedCall(
        name="nuself-interactive-send",
        target=bind_runtime_context(
            lambda: send_message(message, thread_id, turn_id)
        ),
    )
    captured_events: list[LogEvent] = []
    new_events: list[LogEvent] = []
    try:
        send_call.start()
        try:
            while send_call.alive:
                if subscription_id is not None:
                    try:
                        new_events = list(
                            client.next_activity(
                                subscription_id,
                                project_root=project_root,
                                timeout_ms=int(poll_interval_seconds * 1000),
                            )
                        )
                    except (
                        client.DaemonConnectionError,
                        client.DaemonApplicationError,
                    ) as exc:
                        _report_activity_transport_degraded(
                            exc,
                            stage="poll",
                            project_root=project_root,
                            subscription_id=subscription_id,
                        )
                        close_activity_subscription(
                            subscription_id,
                            project_root,
                        )
                        subscription_id = None
                        new_events = read_events(
                            project_root,
                            log_cursor,
                            turn_id=turn_id,
                        )
                else:
                    time.sleep(poll_interval_seconds)
                    new_events = read_events(
                        project_root,
                        log_cursor,
                        turn_id=turn_id,
                    )
                if new_events:
                    log_cursor.mark_seen(new_events)
                    captured_events.extend(
                        captured_interactive_activity_events(new_events)
                    )
                    printed_logs = present_events(
                        new_events,
                        printed_logs=printed_logs,
                    )
        except BaseException:
            try:
                send_call.cancel()
            except Exception as cancellation_error:
                report_chat_failure(
                    cancellation_error,
                    event="interactive_send_failed",
                    project_root=project_root,
                )
            if not daemon_activity:
                print(
                    "\nInterrupt requested; waiting for the active local "
                    "operation to release its resources.",
                    file=sys.stderr,
                )
            _reap_cancelled_send(send_call)
            raise

        outcome = send_call.outcome()
        if outcome.error is not None and not isinstance(
            outcome.error,
            Exception,
        ):
            control = outcome.error
            raise control.with_traceback(control.__traceback__)

        new_events = _drain_final_activity(
            subscription_id,
            project_root,
            log_cursor,
            turn_id=turn_id,
            read_events=read_events,
        )
        log_cursor.mark_seen(new_events)
    finally:
        if subscription_id is not None:
            close_activity_subscription(
                subscription_id,
                project_root,
            )

    if new_events:
        captured_events.extend(captured_interactive_activity_events(new_events))
        printed_logs = present_events(
            new_events,
            printed_logs=printed_logs,
        )
    if isinstance(outcome.error, Exception):
        error = outcome.error
        report_chat_failure(
            error,
            event="interactive_send_failed",
            project_root=project_root,
        )
        print(
            "chat turn failed: "
            f"{diagnostic_exception_message(error)}",
            file=sys.stderr,
        )
        return (
            InteractiveChatResult(code=CliExitCode.FAILURE),
            captured_events,
            printed_logs,
        )
    return (
        (
            outcome.value
            if outcome.value is not None
            else InteractiveChatResult(code=CliExitCode.FAILURE)
        ),
        captured_events,
        printed_logs,
    )


def _reap_cancelled_send(
    send_call: OwnedCall[InteractiveChatResult],
) -> None:
    """Join one cancelled owner even if cleanup receives another Ctrl-C."""

    while True:
        try:
            if send_call.wait():
                return
        except KeyboardInterrupt:
            continue


def _open_activity_subscription(
    turn_id: str | None,
    project_root: Path | None,
    *,
    enabled: bool,
) -> str | None:
    if not enabled or turn_id is None:
        return None
    try:
        return client.open_activity(
            turn_id,
            project_root=project_root,
        )
    except (
        client.DaemonConnectionError,
        client.DaemonApplicationError,
    ) as exc:
        _report_activity_transport_degraded(
            exc,
            stage="open",
            project_root=project_root,
            subscription_id=None,
        )
        return None


def _drain_final_activity(
    subscription_id: str | None,
    project_root: Path | None,
    log_cursor: InteractiveLogCursor,
    *,
    turn_id: str | None,
    read_events: ActivityReader,
) -> list[LogEvent]:
    if subscription_id is None:
        return read_events(
            project_root,
            log_cursor,
            turn_id=turn_id,
        )
    try:
        return list(
            client.next_activity(
                subscription_id,
                project_root=project_root,
                timeout_ms=0,
                limit=256,
            )
        )
    except (
        client.DaemonConnectionError,
        client.DaemonApplicationError,
    ) as exc:
        _report_activity_transport_degraded(
            exc,
            stage="drain",
            project_root=project_root,
            subscription_id=subscription_id,
        )
        return read_events(
            project_root,
            log_cursor,
            turn_id=turn_id,
        )


def close_activity_subscription(
    subscription_id: str,
    project_root: Path | None,
) -> None:
    """Best-effort close one daemon activity subscription."""

    try:
        client.close_activity(
            subscription_id,
            project_root=project_root,
        )
    except (
        client.DaemonConnectionError,
        client.DaemonApplicationError,
    ) as exc:
        _report_activity_transport_degraded(
            exc,
            stage="close",
            project_root=project_root,
            subscription_id=subscription_id,
        )


def read_interactive_activity_events(
    project_root: Path | None,
    log_cursor: InteractiveLogCursor,
    *,
    turn_id: str | None = None,
) -> list[LogEvent]:
    """Read unseen activity, optionally scoped to one logical chat turn."""

    events = log_cursor.read_new_events(project_root)
    if turn_id is None:
        return events
    return [event for event in events if event.turn_id == turn_id]


def print_interactive_activity_events(events: list[LogEvent]) -> None:
    """Render activity events in their existing delivery order."""

    for event in events:
        print_ansi(render_log_event(event))


def visible_interactive_activity_events(
    events: list[LogEvent],
) -> list[LogEvent]:
    """Return events that belong in the live user-facing activity stream."""

    return [event for event in events if is_interactive_activity_log(event)]


def captured_interactive_activity_events(
    events: list[LogEvent],
) -> list[LogEvent]:
    """Return events retained for the current session transcript."""

    return [
        event
        for event in events
        if event.component in {"chat", "daemon", "persona"}
    ]


def is_interactive_activity_log(event: LogEvent) -> bool:
    """Return whether one event is visible while an interactive turn runs."""

    if event.component == "persona":
        return event.event in {
            "persona_summary",
            "host_discussion_decision",
            "persona_discussion",
            "persona_discussion_step",
            "persona_crafted",
            "persona_listed",
            "persona_think",
            "persona_think_failed",
        }
    if event.component == "chat":
        if event.event == "tool.activity":
            return event.status in {
                "pending",
                "decided",
                "completed",
                "failed",
            }
        if event.event == "service_tool_called":
            return True
        if event.event in {
            "turn.started",
            "turn.completed",
            "turn.reused",
            "turn_started",
            "turn_completed",
            "turn_reused",
            "turn_retry",
            "final_response_retry",
            "final_response_completed",
        }:
            return True
        return is_failure_activity_log(event)
    if event.component == "daemon":
        return is_failure_activity_log(event)
    return False


def is_failure_activity_log(event: LogEvent) -> bool:
    """Return whether an event represents a user-relevant turn failure."""

    if event.status in {"error", "failed", "failed_over", "exhausted"}:
        return True
    return event.event in {
        "chat_turn_failed",
        "daemon_chat_failed",
        "final_response_failed",
        "llm_endpoint_failed_over",
        "llm_endpoint_unavailable",
        "turn.failed",
        "turn_failed",
    }
