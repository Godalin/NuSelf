"""CLI adapters for daemon-backed and one-shot chat."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from nuself.agent.chat import ChatAgent
from nuself.cli.commands.output import print_ansi
from nuself.cli.repl.types import InteractiveChatResult
from nuself.config import ConfigSystem
from nuself.daemon import client
from nuself.logs import write_log_event
from nuself.memory.curator import MemoryCurator
from nuself.runtime.context import runtime_context
from nuself.tui.render import TerminalTheme

ReplyPrinter = Callable[[str], None]

_theme = TerminalTheme()


def send_daemon_chat(
    message: str,
    project_root: Path | None,
    thread_id: str = "default",
    *,
    print_reply: ReplyPrinter,
) -> int:
    """Send one daemon-backed message and present its one-shot result."""

    result = send_daemon_chat_interactive(
        message,
        project_root,
        thread_id,
    )
    if result.reply is not None:
        print_reply(result.reply)
    if result.memory_update is not None:
        print_ansi(
            f"{_theme.tag('[memory]', 'memory')} {result.memory_update}"
        )
    if result.error is not None:
        print(result.error, file=sys.stderr)
    return result.code


def send_daemon_chat_interactive(
    message: str,
    project_root: Path | None,
    thread_id: str = "default",
    *,
    turn_id: str | None = None,
) -> InteractiveChatResult:
    """Translate one typed daemon chat operation to the REPL result contract."""

    with runtime_context(
        thread_id=thread_id,
        turn_id=turn_id,
        source="client",
    ):
        try:
            response = client.chat(
                message,
                thread_id=thread_id,
                turn_id=turn_id,
                project_root=project_root,
                timeout=chat_request_timeout_seconds(project_root),
            )
        except client.DaemonConnectionError as exc:
            error = f"daemon request failed: {exc}"
            print(error, file=sys.stderr)
            return InteractiveChatResult(
                code=1,
                retryable=exc.retryable,
                error=error,
                failure_phase=exc.phase,
                request_id=exc.request_id,
                request_may_have_completed=(
                    exc.request_may_have_completed
                ),
            )
        except client.DaemonApplicationError as exc:
            error = str(exc)
            write_log_event(
                "chat",
                "daemon_chat_failed",
                "daemon chat request failed",
                project_root=project_root,
                level="error",
                status="error",
                error=error,
            )
            return InteractiveChatResult(code=1, error=error)
        with runtime_context(thread_id=response.thread_id):
            write_log_event(
                "chat",
                "daemon_chat_completed",
                "daemon chat request completed",
                project_root=project_root,
                status="ok",
            )
        return InteractiveChatResult(
            code=0,
            reply=response.reply,
            memory_update=response.memory_update or None,
        )


def chat_request_timeout_seconds(project_root: Path | None) -> float:
    """Return the configured daemon chat request timeout."""

    return ConfigSystem.load(
        project_root=project_root
    ).chat.request_timeout_seconds


def send_one_shot_chat(
    message: str,
    project_root: Path | None,
    thread_id: str = "default",
    *,
    print_reply: ReplyPrinter,
) -> int:
    """Run one local message and present its one-shot result."""

    result = send_one_shot_chat_interactive(
        message,
        project_root,
        thread_id,
    )
    if result.reply is not None:
        print_reply(result.reply)
    return result.code


def send_one_shot_chat_interactive(
    message: str,
    project_root: Path | None,
    thread_id: str = "default",
    *,
    turn_id: str | None = None,
) -> InteractiveChatResult:
    """Run one local chat operation and translate expected runtime failure."""

    with runtime_context(
        thread_id=thread_id,
        turn_id=turn_id,
        source="client",
    ):
        try:
            reply = one_shot_reply(
                message,
                project_root,
                thread_id,
                turn_id=turn_id,
            )
            write_log_event(
                "chat",
                "one_shot_chat_completed",
                "one-shot chat turn completed",
                project_root=project_root,
                status="ok",
            )
            run_memory_curator(project_root)
            return InteractiveChatResult(code=0, reply=reply)
        except RuntimeError as exc:
            write_log_event(
                "chat",
                "one_shot_chat_failed",
                "one-shot chat turn failed",
                project_root=project_root,
                level="error",
                status="error",
                error=str(exc),
            )
            print(str(exc), file=sys.stderr)
            return InteractiveChatResult(code=1)


def run_memory_curator(project_root: Path | None) -> None:
    """Run post-turn curation and present its optional status."""

    try:
        result = MemoryCurator(project_root).run_once()
    except RuntimeError as exc:
        write_log_event(
            "memory",
            "curator_failed",
            "memory curator failed",
            project_root=project_root,
            level="error",
            status="error",
            error=str(exc),
        )
        print_ansi(
            f"{_theme.tag('[memory]', 'memory')} curator failed: {exc}",
            file=sys.stderr,
        )
        return
    if result.changed:
        write_log_event(
            "memory",
            "curator_changed",
            "memory curator changed durable memory",
            project_root=project_root,
            status="changed",
            metadata={"summary": result.summary()},
        )
        print_ansi(
            f"{_theme.tag('[memory]', 'memory')} {result.summary()}"
        )


def one_shot_reply(
    message: str,
    project_root: Path | None,
    thread_id: str = "default",
    *,
    turn_id: str | None = None,
) -> str:
    """Invoke the local conversation runtime and return its reply text."""

    return (
        ChatAgent(project_root)
        .respond(message, thread_id=thread_id, turn_id=turn_id)
        .reply
    )
