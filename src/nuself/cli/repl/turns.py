"""One logical interactive chat turn."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from nuself.cli.output import print_ansi
from nuself.cli.repl.activity import (
    ActivityReader,
    run_live_activity_send,
    visible_interactive_activity_events,
)
from nuself.cli.exit_codes import CliExitCode
from nuself.cli.repl.notices import (
    print_interactive_notices,
    turn_interactive_notices,
)
from nuself.cli.repl.session import InteractiveSession
from nuself.cli.repl.types import InteractiveChatResult
from nuself.agent.chat.audit import write_chat_audit
from nuself.logs import InteractiveLogCursor, LogEvent
from nuself.runtime.context import RuntimeContext, use_runtime_context
from nuself.tui.render import TerminalTheme

SendMessage = Callable[[str, str, str | None], InteractiveChatResult]
ActivityPrinter = Callable[[list[LogEvent]], None]
ReplyPrinter = Callable[[str], None]

_theme = TerminalTheme()


def send_interactive_chat_turn(
    send_message: SendMessage,
    project_root: Path | None,
    conversation_id: str,
    message: str,
    session: InteractiveSession,
    *,
    daemon_activity: bool,
    max_attempts: int,
    poll_interval_seconds: float,
    read_activity_events: ActivityReader,
    print_activity_events: ActivityPrinter,
    print_reply: ReplyPrinter,
) -> int:
    """Run one stable-id turn and associate its output with the session."""

    log_cursor = InteractiveLogCursor.from_project(project_root)
    result = InteractiveChatResult(code=CliExitCode.FAILURE)
    printed_logs = False
    presented_notice_codes: set[str] = set()
    turn_id = session.prepare_turn(
        message=message,
        conversation_id=conversation_id,
        new_turn_id=f"turn-{uuid4().hex}",
    )

    def present_events(
        events: list[LogEvent],
        *,
        printed_logs: bool,
    ) -> bool:
        return _present_activity_events(
            events,
            printed_logs=printed_logs,
            print_activity_events=print_activity_events,
        )

    for attempt in range(1, max_attempts + 1):
        with use_runtime_context(
            RuntimeContext(
                conversation_id=conversation_id,
                turn_id=turn_id,
                source="client",
            )
        ):
            if attempt > 1:
                write_chat_audit(
                    "turn_retry",
                    project_root=project_root,
                    request_id=result.request_id,
                    metadata={
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "failure_phase": (
                            result.failure_phase or "unknown"
                        ),
                        "request_may_have_completed": (
                            result.request_may_have_completed
                        ),
                    },
                )
                print()
                print(
                    f"Retrying message after failed attempt "
                    f"({attempt}/{max_attempts})..."
                )
            result, events, printed_logs = run_live_activity_send(
                send_message,
                message,
                conversation_id,
                turn_id,
                project_root,
                log_cursor,
                printed_logs=printed_logs,
                daemon_activity=daemon_activity,
                poll_interval_seconds=poll_interval_seconds,
                read_events=read_activity_events,
                present_events=present_events,
            )
        _capture_turn_output(
            session,
            project_root,
            conversation_id,
            events,
        )
        notices = tuple(
            notice
            for notice in turn_interactive_notices(events)
            if notice.code not in presented_notice_codes
        )
        if notices:
            print_interactive_notices(notices)
            presented_notice_codes.update(
                notice.code for notice in notices
            )
        if result.reply is not None:
            print()
            print_ansi(_theme.paint("NuSelf:", "96"))
            print()
            print_reply(result.reply)
            if result.after_reply is not None:
                result.after_reply()
        if result.code == 0:
            session.clear_retry()
            return CliExitCode.SUCCESS
        if not result.retryable:
            session.clear_retry()
            if result.error is not None and not _events_include_error(
                events,
                result.error,
            ):
                print(result.error, file=sys.stderr)
            break
    if result.retryable:
        session.offer_retry(
            message=message,
            conversation_id=conversation_id,
            turn_id=turn_id,
            request_may_have_completed=result.request_may_have_completed,
        )
        completion_note = (
            " The previous request may already have completed."
            if result.request_may_have_completed
            else ""
        )
        print(
            "Message failed after retry; the REPL remains open."
            f"{completion_note} Use :retry to retry the same turn safely.",
            file=sys.stderr,
        )
    return result.code


def _present_activity_events(
    events: list[LogEvent],
    *,
    printed_logs: bool,
    print_activity_events: ActivityPrinter,
) -> bool:
    visible_events = visible_interactive_activity_events(events)
    if not visible_events:
        return printed_logs
    if not printed_logs:
        print()
        print_ansi(_theme.paint("Logs:", "93"))
        printed_logs = True
    print_activity_events(visible_events)
    return printed_logs


def _capture_turn_output(
    session: InteractiveSession,
    project_root: Path | None,
    conversation_id: str,
    events: list[LogEvent],
) -> None:
    previous_next_index = session.captured_next_indexes.get(
        conversation_id,
        session.start_index_for(project_root, conversation_id),
    )
    session.capture_new_messages(project_root, conversation_id)
    current_next_index = session.captured_next_indexes.get(
        conversation_id,
        previous_next_index,
    )
    message_index = (
        current_next_index - 1
        if current_next_index > previous_next_index
        else None
    )
    session.capture_log_events(
        conversation_id,
        events,
        message_index=message_index,
    )


def _events_include_error(events: list[LogEvent], error: str) -> bool:
    return any(event.error == error for event in events)
