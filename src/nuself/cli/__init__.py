"""Command-line interface for NuSelf."""

from __future__ import annotations

import argparse
import sys
import time
import warnings
from collections.abc import Callable, Sequence
from pathlib import Path
from uuid import uuid4

_original_warn = warnings.warn

TYPEWRITER_DELAY_SECONDS = 0.01
TYPEWRITER_REFRESH_PER_SECOND = 30


def _suppress_startup_warning(
    message: Warning | str,
    category: type[Warning] | None = None,
    stacklevel: int = 1,
    source: object | None = None,
) -> None:
    if "The default value of `allowed_objects` will change in a future version." in str(
        message
    ):
        return
    _original_warn(message, category=category, stacklevel=stacklevel, source=source)


warnings.warn = _suppress_startup_warning
try:
    from nuself import __version__
    from nuself.agent.chat import ChatAgent, ThreadState, ThreadStore
    from nuself.cli.commands.daemon import (
        format_status as _format_status,
    )
    from nuself.cli.commands.output import (
        print_ansi as _print_ansi,
    )
    from nuself.cli.repl.activity import (
        print_interactive_activity_events as _print_interactive_activity_events,
    )
    from nuself.cli.repl.activity import (
        read_interactive_activity_events as _interactive_activity_events,
    )
    from nuself.cli.repl.activity import (
        run_live_activity_send as _run_live_activity_send,
    )
    from nuself.cli.repl.activity import (
        visible_interactive_activity_events as _visible_interactive_activity_events,
    )
    from nuself.cli.commands.reflections import (
        handle_reflection_archive as handle_reflection_archive,
    )
    from nuself.cli.commands.reflections import (
        handle_reflection_dismiss as handle_reflection_dismiss,
    )
    from nuself.cli.commands.reflections import (
        handle_reflection_list as handle_reflection_list,
    )
    from nuself.cli.commands.reflections import (
        handle_reflection_show as handle_reflection_show,
    )
    from nuself.cli.handlers import dispatch_cli
    from nuself.cli.parser import (
        InteractiveHandlers,
    )
    from nuself.cli.parser import (
        build_parser as _build_parser,
    )
    from nuself.cli.repl.commands import (
        handle_interactive_reason_watch as _handle_interactive_reason_watch,
    )
    from nuself.cli.repl.dispatcher import (
        handle_interactive_command as _handle_interactive_command,
    )
    from nuself.cli.repl.input import (
        InteractiveCompleter as _InteractiveCompleter,
    )
    from nuself.cli.repl.runtime import (
        ReplCallbacks,
        run_interactive_loop,
    )
    from nuself.cli.repl.session import (
        InteractiveSession as InteractiveSession,
    )
    from nuself.cli.repl.transcript import (
        auto_save_interactive_transcripts as _auto_save_interactive_transcripts,
    )
    from nuself.cli.repl.transcript import (
        render_chat_transcript as _render_chat_transcript,
    )
    from nuself.cli.repl.types import InteractiveChatResult
    from nuself.config import ConfigSystem
    from nuself.daemon import client, lifecycle
    from nuself.logs import (
        InteractiveLogCursor,
        LogEvent,
        write_log_event,
    )
    from nuself.memory.curator import MemoryCurator
    from nuself.runtime.context import (
        RuntimeContext,
        use_runtime_context,
    )
    from nuself.tui.render import TerminalTheme, render_session_header
finally:
    warnings.warn = _original_warn

__all__ = [
    "_InteractiveCompleter",
    "_render_chat_transcript",
    "build_parser",
    "main",
]

CHAT_REQUEST_TIMEOUT_SECONDS = 120.0
DEFAULT_MEMORY_PREVIEW_LIMIT = 8
INTERACTIVE_CHAT_ATTEMPTS = 2
INTERACTIVE_LOG_POLL_INTERVAL_SECONDS = 0.1


_theme = TerminalTheme()


def _maybe_show_session_update(
    project_root: Path | None,
    thread_id: str,
    session: InteractiveSession,
) -> None:
    status = _interactive_daemon_status(project_root) if project_root else "unknown"
    if session.should_render_header(
        thread_id=thread_id,
        daemon_status=status,
    ):
        _print_ansi(render_session_header(daemon_status=status, thread_id=thread_id))


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return dispatch_cli(args, parser)


def build_parser() -> argparse.ArgumentParser:
    return _build_parser(
        InteractiveHandlers(
            default_entrypoint=handle_default_entrypoint,
            chat=handle_chat,
            attach=handle_attach,
            open_thread=handle_open,
            reason_watch=handle_reason_watch,
        )
    )


def handle_default_entrypoint(args: argparse.Namespace) -> int:
    result = lifecycle.status(args.project_root)
    if result.running:
        if args.message is not None:
            print(f"Using current daemon: {_format_status(result)}")
    else:
        print("Starting NuSelf daemon...")
        result = lifecycle.start(args.project_root)
        if not result.running:
            print(f"Failed to start daemon: {_format_status(result)}", file=sys.stderr)
            return 1
        print(f"Daemon started: {_format_status(result)}")
    if args.message is not None:
        return _send_chat(args.message, args.project_root)
    return _interactive_loop(
        lambda message, thread_id, turn_id: _send_chat_interactive(
            message, args.project_root, thread_id, turn_id=turn_id
        ),
        args.project_root,
        daemon_activity=True,
    )


def handle_chat(args: argparse.Namespace) -> int:
    if lifecycle.status(args.project_root).running:
        if args.message is not None:
            return _send_chat(args.message, args.project_root)
        return _interactive_loop(
            lambda message, thread_id, turn_id: _send_chat_interactive(
                message, args.project_root, thread_id, turn_id=turn_id
            ),
            args.project_root,
            daemon_activity=True,
        )
    if args.require_daemon:
        print("NuSelf daemon is not running.", file=sys.stderr)
        return 1
    if args.message is not None:
        return _send_one_shot_chat(args.message, args.project_root)
    return _interactive_loop(
        lambda message, thread_id, turn_id: _send_one_shot_chat_interactive(
            message, args.project_root, thread_id, turn_id=turn_id
        ),
        args.project_root,
    )


def handle_attach(args: argparse.Namespace) -> int:
    if not lifecycle.status(args.project_root).running:
        print("NuSelf daemon is not running.", file=sys.stderr)
        return 1
    if args.message is not None:
        return _send_chat(args.message, args.project_root)
    return _interactive_loop(
        lambda message, thread_id, turn_id: _send_chat_interactive(
            message, args.project_root, thread_id, turn_id=turn_id
        ),
        args.project_root,
        daemon_activity=True,
    )


def handle_open(args: argparse.Namespace) -> int:
    store = ThreadStore(args.project_root)
    thread_id: str | None = args.thread_id

    if args.deep_link is not None:
        from nuself.notification.deep_link import DeepLink

        try:
            link = DeepLink.parse(args.deep_link)
        except ValueError as exc:
            print(f"Invalid deep link: {exc}", file=sys.stderr)
            return 1
        if link.action == "new_thread":
            thread_id = link.title or "new-thread"
            store.save(ThreadState.empty(thread_id))
            print(f"Created thread: {thread_id}")
            if args.message is None and link.message is not None:
                args.message = link.message
        else:
            thread_id = link.thread_id
            if args.message is None and link.message is not None:
                args.message = link.message

    if thread_id is None:
        print("Thread ID or --deep-link is required.", file=sys.stderr)
        return 1

    if thread_id not in store.list():
        if args.create:
            store.save(ThreadState.empty(thread_id))
            print(f"Created thread: {thread_id}")
        else:
            print(f"Thread not found: {thread_id}", file=sys.stderr)
            return 1
    if lifecycle.status(args.project_root).running:
        if args.message is not None:
            result = _send_chat(args.message, args.project_root, thread_id)
            if result != 0:
                return result
        return _interactive_loop(
            lambda message, tid, turn_id: _send_chat_interactive(
                message, args.project_root, tid, turn_id=turn_id
            ),
            args.project_root,
            initial_thread_id=thread_id,
            daemon_activity=True,
        )
    if args.message is not None:
        result = _send_one_shot_chat(args.message, args.project_root, thread_id)
        if result != 0:
            return result
    return _interactive_loop(
        lambda message, tid, turn_id: _send_one_shot_chat_interactive(
            message, args.project_root, tid, turn_id=turn_id
        ),
        args.project_root,
        initial_thread_id=thread_id,
    )


# ── Reason handlers ───────────────────────────────────────────────────


def handle_reason_watch(args: argparse.Namespace) -> int:
    _handle_interactive_reason_watch(
        args.project_root,
        interval=getattr(args, "interval", 5),
        thread_ref=getattr(args, "thread_id", None) or None,
    )
    return 0


def _send_chat(
    message: str, project_root: Path | None, thread_id: str = "default"
) -> int:
    result = _send_chat_interactive(message, project_root, thread_id)
    if result.reply is not None:
        _print_assistant_reply(result.reply)
    if result.memory_update is not None:
        _print_ansi(f"{_theme.tag('[memory]', 'memory')} {result.memory_update}")
    if result.error is not None:
        print(result.error, file=sys.stderr)
    return result.code


def _send_chat_interactive(
    message: str,
    project_root: Path | None,
    thread_id: str = "default",
    *,
    turn_id: str | None = None,
) -> InteractiveChatResult:
    timeout_seconds = _chat_request_timeout_seconds(project_root)
    try:
        response = client.chat(
            message,
            thread_id=thread_id,
            turn_id=turn_id,
            project_root=project_root,
            timeout=timeout_seconds,
        )
    except client.DaemonConnectionError as exc:
        error = f"daemon request failed: {exc}"
        print(error, file=sys.stderr)
        return InteractiveChatResult(code=1, retryable=True, error=error)
    except client.DaemonApplicationError as exc:
        error = str(exc)
        write_log_event(
            "chat",
            "daemon_chat_failed",
            "daemon chat request failed",
            project_root=project_root,
            level="error",
            thread_id=thread_id,
            turn_id=turn_id,
            source="client",
            status="error",
            error=error,
        )
        return InteractiveChatResult(code=1, error=error)
    write_log_event(
        "chat",
        "daemon_chat_completed",
        "daemon chat request completed",
        project_root=project_root,
        thread_id=response.thread_id,
        turn_id=turn_id,
        source="client",
        status="ok",
    )
    return InteractiveChatResult(
        code=0,
        reply=response.reply,
        memory_update=response.memory_update or None,
    )


def _chat_request_timeout_seconds(project_root: Path | None) -> float:
    return ConfigSystem.load(
        project_root=project_root
    ).chat.request_timeout_seconds


def _interactive_loop(
    send_message: Callable[[str, str, str | None], InteractiveChatResult],
    project_root: Path | None,
    *,
    initial_thread_id: str = "default",
    daemon_activity: bool = False,
) -> int:
    def send_turn(
        turn_sender: Callable[
            [str, str, str | None],
            InteractiveChatResult,
        ],
        turn_project_root: Path | None,
        thread_id: str,
        message: str,
        session: InteractiveSession,
    ) -> int:
        return _send_interactive_chat_turn(
            turn_sender,
            turn_project_root,
            thread_id,
            message,
            session,
            daemon_activity=daemon_activity,
        )

    return run_interactive_loop(
        send_message,
        project_root,
        ReplCallbacks(
            handle_command=_handle_interactive_command,
            send_turn=send_turn,
            auto_save=_auto_save_interactive_transcripts,
            run_curator=_run_memory_curator,
            show_session_update=_maybe_show_session_update,
            daemon_status=_interactive_daemon_status,
            brand_banner=_brand_banner,
        ),
        initial_thread_id=initial_thread_id,
    )


def _send_interactive_chat_turn(
    send_message: Callable[[str, str, str | None], InteractiveChatResult],
    project_root: Path | None,
    thread_id: str,
    message: str,
    session: InteractiveSession,
    *,
    daemon_activity: bool = False,
) -> int:
    log_cursor = InteractiveLogCursor.from_project(project_root)
    result = InteractiveChatResult(code=1)
    printed_logs = False
    turn_id = f"turn-{uuid4().hex}"
    for attempt in range(1, INTERACTIVE_CHAT_ATTEMPTS + 1):
        if attempt > 1:
            write_log_event(
                "chat",
                "turn_retry",
                "retrying chat turn after retryable transport failure",
                project_root=project_root,
                thread_id=thread_id,
                turn_id=turn_id,
                source="client",
                status="retry",
                metadata={
                    "attempt": attempt,
                    "max_attempts": INTERACTIVE_CHAT_ATTEMPTS,
                    "previous_error": result.error,
                },
            )
            print()
            print(
                f"Retrying message after failed attempt ({attempt}/{INTERACTIVE_CHAT_ATTEMPTS})..."
            )
        with use_runtime_context(
            RuntimeContext(
                thread_id=thread_id,
                turn_id=turn_id,
                source="client",
            )
        ):
            result, events, printed_logs = (
                _run_interactive_send_with_live_logs(
                    send_message,
                    message,
                    thread_id,
                    turn_id,
                    project_root,
                    log_cursor,
                    printed_logs=printed_logs,
                    daemon_activity=daemon_activity,
                )
            )
        previous_next_index = session.captured_next_indexes.get(
            thread_id, session.start_index_for(project_root, thread_id)
        )
        session.capture_new_messages(project_root, thread_id)
        current_next_index = session.captured_next_indexes.get(
            thread_id, previous_next_index
        )
        message_index = (
            current_next_index - 1 if current_next_index > previous_next_index else None
        )
        session.capture_log_events(thread_id, events, message_index=message_index)
        if result.memory_update is not None:
            if not printed_logs:
                print()
                _print_ansi(_theme.paint("Logs:", "93"))
                printed_logs = True
            _print_ansi(f"{_theme.tag('[memory]', 'memory')} {result.memory_update}")
        if result.reply is not None:
            print()
            _print_ansi(_theme.paint("NuSelf:", "96"))
            print()
            _print_assistant_reply(result.reply)
        if result.code == 0:
            return 0
        if not result.retryable:
            if result.error is not None and not _events_include_error(
                events, result.error
            ):
                print(result.error, file=sys.stderr)
            break
    if result.retryable:
        print("Message failed after retry; REPL remains open.", file=sys.stderr)
    return result.code


def _run_interactive_send_with_live_logs(
    send_message: Callable[[str, str, str | None], InteractiveChatResult],
    message: str,
    thread_id: str,
    turn_id: str | None,
    project_root: Path | None,
    log_cursor: InteractiveLogCursor,
    *,
    printed_logs: bool,
    daemon_activity: bool = False,
) -> tuple[InteractiveChatResult, list[LogEvent], bool]:
    return _run_live_activity_send(
        send_message,
        message,
        thread_id,
        turn_id,
        project_root,
        log_cursor,
        printed_logs=printed_logs,
        daemon_activity=daemon_activity,
        poll_interval_seconds=INTERACTIVE_LOG_POLL_INTERVAL_SECONDS,
        read_events=_interactive_activity_events,
        present_events=_print_visible_interactive_activity_events,
    )


def _print_visible_interactive_activity_events(
    events: list[LogEvent], *, printed_logs: bool
) -> bool:
    visible_events = _visible_interactive_activity_events(events)
    if not visible_events:
        return printed_logs
    return _print_live_interactive_activity_events(
        visible_events, printed_logs=printed_logs
    )


def _print_live_interactive_activity_events(
    events: list[LogEvent], *, printed_logs: bool
) -> bool:
    if not printed_logs:
        print()
        _print_ansi(_theme.paint("Logs:", "93"))
        printed_logs = True
    _print_interactive_activity_events(events)
    return printed_logs


def _events_include_error(events: list[LogEvent], error: str) -> bool:
    return any(event.error == error for event in events)


def _send_one_shot_chat(
    message: str, project_root: Path | None, thread_id: str = "default"
) -> int:
    result = _send_one_shot_chat_interactive(message, project_root, thread_id)
    if result.reply is not None:
        _print_assistant_reply(result.reply)
    return result.code


def _send_one_shot_chat_interactive(
    message: str,
    project_root: Path | None,
    thread_id: str = "default",
    *,
    turn_id: str | None = None,
) -> InteractiveChatResult:
    try:
        reply = _one_shot_reply(message, project_root, thread_id, turn_id=turn_id)
        write_log_event(
            "chat",
            "one_shot_chat_completed",
            "one-shot chat turn completed",
            project_root=project_root,
            thread_id=thread_id,
            turn_id=turn_id,
            source="client",
            status="ok",
        )
        _run_memory_curator(project_root)
        return InteractiveChatResult(code=0, reply=reply)
    except RuntimeError as exc:
        write_log_event(
            "chat",
            "one_shot_chat_failed",
            "one-shot chat turn failed",
            project_root=project_root,
            level="error",
            thread_id=thread_id,
            turn_id=turn_id,
            source="client",
            status="error",
            error=str(exc),
        )
        print(str(exc), file=sys.stderr)
        return InteractiveChatResult(code=1)


def _run_memory_curator(project_root: Path | None) -> None:
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
        _print_ansi(
            f"{_theme.tag('[memory]', 'memory')} curator failed: {exc}", file=sys.stderr
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
        _print_ansi(f"{_theme.tag('[memory]', 'memory')} {result.summary()}")


def _brand_banner() -> str:
    return "\n".join(
        [
            "        ┌────┐       ┌─┐  ┌────┐",
            "        │ ┌──┘       │ │  │ ┌──┘",
            "╭─╮ ╭─╮ │ └──┐ ┌───┐ │ │  │ └─┐ ",
            "│ │ │ │ └──┐ │ │┌─ │ │ │  │ ┌─┘ ",
            "╰─┴─╯ │ ┌──┘ │ │└──╯ │ └┐ │ │   ",
            "  ╰───╯ └────┘ ╰───╯ └──┘ └─┘   ",
        ]
    )


def _one_shot_reply(
    message: str,
    project_root: Path | None,
    thread_id: str = "default",
    *,
    turn_id: str | None = None,
) -> str:
    return (
        ChatAgent(project_root)
        .respond(message, thread_id=thread_id, turn_id=turn_id)
        .reply
    )


def _print_assistant_reply(text: str) -> None:
    if not sys.stdout.isatty():
        print(text)
        return
    _render_assistant_reply_rich(text)


def _render_assistant_reply_rich(text: str) -> None:
    from rich.console import Console
    from rich.live import Live
    from rich.markdown import Markdown

    console = Console()
    if text == "":
        console.print("")
        return

    visible_text = ""
    with Live(
        Markdown(""),
        console=console,
        refresh_per_second=TYPEWRITER_REFRESH_PER_SECOND,
        transient=False,
    ) as live:
        for character in text:
            visible_text += character
            live.update(Markdown(visible_text))
            time.sleep(TYPEWRITER_DELAY_SECONDS)


def _interactive_daemon_status(project_root: Path | None) -> str:
    status = lifecycle.status(project_root)
    return "running" if status.running else "one-shot"


if __name__ == "__main__":
    raise SystemExit(main())
