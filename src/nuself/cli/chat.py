"""CLI adapters for daemon-backed and one-shot chat."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from nuself.application.chat import compose_conversation_runtime
from nuself.application.curator import compose_memory_curator
from nuself.cli.composition import compose_cli_application
from nuself.agent.chat.audit import (
    report_chat_failure,
    write_chat_audit,
)
from nuself.cli.commands.output import print_ansi
from nuself.cli.exit_codes import CliExitCode
from nuself.cli.repl.types import InteractiveChatResult
from nuself.config import ConfigSystem
from nuself.daemon import client
from nuself.memory.audit import report_memory_failure
from nuself.runtime.context import runtime_context
from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.runtime.execution import current_cancellation
from nuself.tui.render import TerminalTheme
from nuself.tui.approval import TerminalApprovalPort

ReplyPrinter = Callable[[str], None]

_theme = TerminalTheme()


def send_daemon_chat(
    message: str,
    project_root: Path | None,
    conversation_id: str = "default",
    *,
    print_reply: ReplyPrinter,
) -> int:
    """Send one daemon-backed message and present its one-shot result."""

    result = send_daemon_chat_interactive(
        message,
        project_root,
        conversation_id,
    )
    if result.reply is not None:
        print_reply(result.reply)
    if result.error is not None:
        print(result.error, file=sys.stderr)
    return result.code


def send_daemon_chat_interactive(
    message: str,
    project_root: Path | None,
    conversation_id: str = "default",
    *,
    turn_id: str | None = None,
) -> InteractiveChatResult:
    """Translate one typed daemon chat operation to the REPL result contract."""

    with runtime_context(
        conversation_id=conversation_id,
        turn_id=turn_id,
        source="client",
    ):
        try:
            response = client.chat(
                message,
                conversation_id=conversation_id,
                turn_id=turn_id,
                project_root=project_root,
                timeout=chat_request_timeout_seconds(project_root),
            )
        except client.DaemonConnectionError as exc:
            cancellation = current_cancellation()
            if cancellation is not None and cancellation.cancelled:
                return InteractiveChatResult(
                    code=CliExitCode.INTERRUPTED,
                )
            error = (
                "daemon request failed: "
                f"{diagnostic_exception_message(exc)}"
            )
            print(error, file=sys.stderr)
            return InteractiveChatResult(
                code=(
                    CliExitCode.TEMPORARY_FAILURE
                    if exc.retryable
                    else CliExitCode.FAILURE
                ),
                retryable=exc.retryable,
                error=error,
                failure_phase=exc.phase,
                request_id=exc.request_id,
                request_may_have_completed=(
                    exc.request_may_have_completed
                ),
            )
        except client.DaemonApplicationError as exc:
            error = diagnostic_exception_message(exc)
            report_chat_failure(
                exc,
                event="daemon_chat_failed",
                project_root=project_root,
            )
            return InteractiveChatResult(
                code=CliExitCode.FAILURE,
                error=error,
            )
        with runtime_context(conversation_id=response.conversation_id):
            write_chat_audit(
                "daemon_chat_completed",
                project_root=project_root,
            )
        return InteractiveChatResult(
            code=CliExitCode.SUCCESS,
            reply=response.reply,
        )


def chat_request_timeout_seconds(project_root: Path | None) -> float:
    """Return the configured daemon chat request timeout."""

    return ConfigSystem.load(
        project_root=project_root
    ).chat.request_timeout_seconds


def send_one_shot_chat(
    message: str,
    project_root: Path | None,
    conversation_id: str = "default",
    *,
    print_reply: ReplyPrinter,
) -> int:
    """Run one local message and present its one-shot result."""

    result = send_one_shot_chat_interactive(
        message,
        project_root,
        conversation_id,
    )
    if result.reply is not None:
        print_reply(result.reply)
        _run_after_reply(result.after_reply)
    return result.code


def send_one_shot_chat_interactive(
    message: str,
    project_root: Path | None,
    conversation_id: str = "default",
    *,
    turn_id: str | None = None,
) -> InteractiveChatResult:
    """Run one local chat operation and translate expected runtime failure."""

    with runtime_context(
        conversation_id=conversation_id,
        turn_id=turn_id,
        source="client",
    ):
        try:
            reply = one_shot_reply(
                message,
                project_root,
                conversation_id,
                turn_id=turn_id,
            )
            write_chat_audit(
                "one_shot_chat_completed",
                project_root=project_root,
            )
            run_memory_curator(project_root, conversation_id)
            return InteractiveChatResult(
                code=CliExitCode.SUCCESS,
                reply=reply,
                after_reply=lambda: _compress_after_reply(
                    conversation_id,
                    project_root,
                ),
            )
        except RuntimeError as exc:
            error = diagnostic_exception_message(exc)
            report_chat_failure(
                exc,
                event="one_shot_chat_failed",
                project_root=project_root,
            )
            print(error, file=sys.stderr)
            return InteractiveChatResult(code=CliExitCode.FAILURE)


def run_memory_curator(
    project_root: Path | None,
    conversation_id: str = "default",
) -> None:
    """Run post-turn curation and present its optional status."""

    try:
        result = compose_memory_curator(
            compose_cli_application(project_root)
        ).run_once(conversation_id)
    except RuntimeError as exc:
        error = diagnostic_exception_message(exc)
        report_memory_failure(
            exc,
            event="curator_failed",
            project_root=project_root,
        )
        print_ansi(
            f"{_theme.tag('[memory]', 'memory')} curator failed: {error}",
            file=sys.stderr,
        )
        return
    if result.changed:
        print_ansi(
            f"{_theme.tag('[memory]', 'memory')} {result.summary()}"
        )


def one_shot_reply(
    message: str,
    project_root: Path | None,
    conversation_id: str = "default",
    *,
    turn_id: str | None = None,
) -> str:
    """Invoke the local conversation runtime and return its reply text."""

    return (
        compose_conversation_runtime(
            compose_cli_application(project_root),
            approval_port=TerminalApprovalPort(),
        )
        .respond(message, conversation_id=conversation_id, turn_id=turn_id)
        .reply
    )


def _run_after_reply(callback: Callable[[], None] | None) -> None:
    if callback is not None:
        callback()


def _compress_after_reply(
    conversation_id: str,
    project_root: Path | None,
) -> None:
    try:
        compose_conversation_runtime(
            compose_cli_application(project_root),
            approval_port=TerminalApprovalPort(),
        ).compress_conversation(conversation_id)
    except Exception as exc:
        report_chat_failure(
            exc,
            event="compression_fallback",
            project_root=project_root,
        )
