"""Command-line interface for NuSelf."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import sys
import threading
import time
from uuid import uuid4
import warnings

_original_warn = warnings.warn

TYPEWRITER_DELAY_SECONDS = 0.01
TYPEWRITER_REFRESH_PER_SECOND = 30


def _suppress_startup_warning(
    message: Warning | str,
    category: type[Warning] | None = None,
    stacklevel: int = 1,
    source: object | None = None,
) -> None:
    if "The default value of `allowed_objects` will change in a future version." in str(message):
        return
    _original_warn(message, category=category, stacklevel=stacklevel, source=source)


warnings.warn = _suppress_startup_warning
try:
    from nuself import __version__
    from nuself.cli.parser import (
        InteractiveHandlers,
        build_parser as _build_parser,
    )
    from nuself.cli.repl.types import InteractiveChatResult
    from nuself.cli.repl.session import (
        InteractiveSession as InteractiveSession,
    )
    from nuself.cli.repl.commands import (
        handle_interactive_history_command as _handle_interactive_history_command,
        handle_interactive_inbox_command as _handle_interactive_inbox_command,
        handle_interactive_memory_command as _handle_interactive_memory_command,
        handle_interactive_notify_command as _handle_interactive_notify_command,
        handle_interactive_notify_list_command as _handle_interactive_notify_list_command,
        handle_interactive_notify_show_command as _handle_interactive_notify_show_command,
        handle_interactive_notify_subcommand as _handle_interactive_notify_subcommand,
        handle_interactive_persona_command as _handle_interactive_persona_command,
        handle_interactive_reason_command as _handle_interactive_reason_command,
        handle_interactive_reason_watch as _handle_interactive_reason_watch,
        handle_interactive_reflection_command as _handle_interactive_reflection_command,
        handle_interactive_reflection_list_command as _handle_interactive_reflection_list_command,
        handle_interactive_reflection_show_command as _handle_interactive_reflection_show_command,
        handle_interactive_reflection_subcommand as _handle_interactive_reflection_subcommand,
        handle_interactive_restart_command as _handle_interactive_restart_command,
        handle_interactive_threads_command as _handle_interactive_threads_command,
        handle_interactive_trace_command as _handle_interactive_trace_command,
        handle_interactive_watch_command as _handle_interactive_watch_command,
        handle_interactive_whoami_command as _handle_interactive_whoami_command,
    )
    from nuself.cli.repl.input import (
        InteractiveCompleter as _InteractiveCompleter,
        init_interactive_input as _init_interactive_input,
        interactive_help as _interactive_help,
        read_interactive_input as _read_interactive_input,
    )
    from nuself.cli.repl.transcript import (
        copy_text_to_clipboard as _copy_text_to_clipboard,
        export_interactive_transcript as _export_interactive_transcript,
        render_chat_transcript as _render_chat_transcript,
    )
    from nuself.agent.chat import ChatAgent, ThreadState, ThreadStore
    from nuself.daemon import client, lifecycle
    from nuself.daemon.protocol import JsonValue
    from nuself.cli.commands.daemon import (
        format_status as _format_status,
    )
    from nuself.cli.commands.output import (
        print_ansi as _print_ansi,
    )
    from nuself.cli.commands.reflections import (
        handle_reflection_archive as handle_reflection_archive,
        handle_reflection_dismiss as handle_reflection_dismiss,
        handle_reflection_list as handle_reflection_list,
        handle_reflection_show as handle_reflection_show,
    )
    from nuself.cli.commands.memory.entries import (
        format_memory_preview as _format_memory_preview,
    )
    from nuself.memory.curator import MemoryCurator
    from nuself.logs import (
        InteractiveLogCursor,
        LogEvent,
        read_log_events,
        write_log_event,
    )
    from nuself.config import ConfigSystem
    from nuself.tui.render import TerminalTheme, render_log_event, render_session_header
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
_last_header_thread: str = ""
_last_header_status: str = ""


def _maybe_show_session_update(project_root: Path | None, thread_id: str) -> None:
    global _last_header_thread, _last_header_status
    status = _interactive_daemon_status(project_root) if project_root else "unknown"
    if thread_id != _last_header_thread or status != _last_header_status:
        _print_ansi(render_session_header(daemon_status=status, thread_id=thread_id))
    _last_header_thread = thread_id
    _last_header_status = status






def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        help_parser = getattr(args, "help_parser", parser)
        help_parser.print_help()
        return 0
    return handler(args)


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
            lambda message, tid, turn_id: _send_chat_interactive(message, args.project_root, tid, turn_id=turn_id),
            args.project_root,
            initial_thread_id=thread_id,
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


def _send_chat(message: str, project_root: Path | None, thread_id: str = "default") -> int:
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
    payload: dict[str, JsonValue] = {"message": message, "thread_id": thread_id}
    if turn_id is not None:
        payload["turn_id"] = turn_id
    try:
        response = client.request(
            "chat",
            payload,
            project_root=project_root,
            timeout=timeout_seconds,
        )
    except client.DaemonConnectionError as exc:
        error = f"daemon request failed: {exc}"
        print(error, file=sys.stderr)
        return InteractiveChatResult(code=1, retryable=True, error=error)
    if response.status == "error":
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
            error=response.error or "daemon returned an error",
        )
        return InteractiveChatResult(code=1, error=response.error or "daemon returned an error")
    reply = response.payload.get("reply")
    if isinstance(reply, str):
        memory_update = response.payload.get("memory_update")
        write_log_event(
            "chat",
            "daemon_chat_completed",
            "daemon chat request completed",
            project_root=project_root,
            thread_id=_optional_payload_str(response.payload.get("thread_id")),
            turn_id=turn_id,
            source="client",
            status="ok",
        )
        return InteractiveChatResult(
            code=0,
            reply=reply,
            memory_update=memory_update if isinstance(memory_update, str) and memory_update != "" else None,
        )
    print("daemon response did not include a reply", file=sys.stderr)
    return InteractiveChatResult(code=1)


def _chat_request_timeout_seconds(project_root: Path | None) -> float:
    try:
        return ConfigSystem.load(project_root=project_root).chat.request_timeout_seconds
    except Exception:
        return CHAT_REQUEST_TIMEOUT_SECONDS


def _interactive_loop(
    send_message: Callable[[str, str, str | None], InteractiveChatResult],
    project_root: Path | None,
    *,
    initial_thread_id: str = "default",
) -> int:
    _init_interactive_input(project_root)
    current_thread_id = initial_thread_id
    session = InteractiveSession(connected_at=datetime.now(UTC))
    session.start_index_for(project_root, current_thread_id)
    print(_brand_banner())
    print("νSelf interactive mode. Type :help for commands, :q to quit.")
    _last_header_thread = current_thread_id
    _print_ansi(render_session_header(daemon_status=_interactive_daemon_status(project_root), thread_id=current_thread_id))
    try:
        while True:
            try:
                line = _read_interactive_input()
            except EOFError:
                print()
                _auto_save_interactive_transcripts(project_root, session)
                return 0
            except KeyboardInterrupt:
                print()
                continue
            message = line.strip()
            if message == "":
                continue
            if message.startswith(":"):
                command_result, current_thread_id = _handle_interactive_command(
                    message, project_root, current_thread_id, session
                )
                session.start_index_for(project_root, current_thread_id)
                if command_result == "exit":
                    return 0
                if command_result == "redraw_header":
                    _last_header_thread = current_thread_id
                    _print_ansi(render_session_header(daemon_status=_interactive_daemon_status(project_root), thread_id=current_thread_id))
                continue
            try:
                result = _send_interactive_chat_turn(
                    send_message,
                    project_root,
                    current_thread_id,
                    message,
                    session,
                )
            except KeyboardInterrupt:
                print("\nInterrupted.")
                continue
            _maybe_show_session_update(project_root, current_thread_id)
            if result != 0:
                continue
    finally:
        _auto_save_interactive_transcripts(project_root, session)
        _run_memory_curator(project_root)


def _send_interactive_chat_turn(
    send_message: Callable[[str, str, str | None], InteractiveChatResult],
    project_root: Path | None,
    thread_id: str,
    message: str,
    session: InteractiveSession,
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
            print(f"Retrying message after failed attempt ({attempt}/{INTERACTIVE_CHAT_ATTEMPTS})...")
        result, events, printed_logs = _run_interactive_send_with_live_logs(
            send_message,
            message,
            thread_id,
            turn_id,
            project_root,
            log_cursor,
            printed_logs=printed_logs,
        )
        previous_next_index = session.captured_next_indexes.get(
            thread_id, session.start_index_for(project_root, thread_id)
        )
        session.capture_new_messages(project_root, thread_id)
        current_next_index = session.captured_next_indexes.get(thread_id, previous_next_index)
        message_index = current_next_index - 1 if current_next_index > previous_next_index else None
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
            if result.error is not None and not _events_include_error(events, result.error):
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
) -> tuple[InteractiveChatResult, list[LogEvent], bool]:
    result_box: list[InteractiveChatResult] = []
    error_box: list[BaseException] = []

    def _target() -> None:
        try:
            result_box.append(send_message(message, thread_id, turn_id))
        except BaseException as exc:  # pragma: no cover - defensive thread boundary
            error_box.append(exc)

    send_thread = threading.Thread(target=_target, daemon=True)
    send_thread.start()
    captured_events: list[LogEvent] = []
    try:
        while send_thread.is_alive():
            time.sleep(INTERACTIVE_LOG_POLL_INTERVAL_SECONDS)
            new_events = _interactive_activity_events(project_root, log_cursor, turn_id=turn_id)
            if new_events:
                captured_events.extend(new_events)
                printed_logs = _print_visible_interactive_activity_events(new_events, printed_logs=printed_logs)
        send_thread.join()
    except KeyboardInterrupt:
        send_thread.join(timeout=0.5)
        raise
    new_events = _interactive_activity_events(project_root, log_cursor, turn_id=turn_id)
    if new_events:
        captured_events.extend(new_events)
        printed_logs = _print_visible_interactive_activity_events(new_events, printed_logs=printed_logs)
    if error_box:
        print(f"chat turn failed: {error_box[0]}", file=sys.stderr)
        return InteractiveChatResult(code=1), captured_events, printed_logs
    return result_box[0] if result_box else InteractiveChatResult(code=1), captured_events, printed_logs


def _print_visible_interactive_activity_events(events: list[LogEvent], *, printed_logs: bool) -> bool:
    visible_events = _visible_interactive_activity_events(events)
    if not visible_events:
        return printed_logs
    return _print_live_interactive_activity_events(visible_events, printed_logs=printed_logs)


def _print_live_interactive_activity_events(events: list[LogEvent], *, printed_logs: bool) -> bool:
    if not printed_logs:
        print()
        _print_ansi(_theme.paint("Logs:", "93"))
        printed_logs = True
    _print_interactive_activity_events(events)
    return printed_logs


def _events_include_error(events: list[LogEvent], error: str) -> bool:
    return any(event.error == error for event in events)




def _send_one_shot_chat(message: str, project_root: Path | None, thread_id: str = "default") -> int:
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
        _print_ansi(f"{_theme.tag('[memory]', 'memory')} curator failed: {exc}", file=sys.stderr)
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


def _handle_interactive_command(
    command: str,
    project_root: Path | None,
    current_thread_id: str,
    session: InteractiveSession,
) -> tuple[str, str]:
    if command in {":q", ":quit", ":exit"}:
        _auto_save_interactive_transcripts(project_root, session)
        return ("exit", current_thread_id)
    if command == ":history":
        print()
        _print_ansi(_handle_interactive_history_command(project_root, current_thread_id))
        return ("", current_thread_id)
    if command == ":whoami":
        print()
        _print_ansi(_handle_interactive_whoami_command(project_root))
        return ("", current_thread_id)
    if command in {":inbox", ":i"}:
        print()
        _print_ansi(_handle_interactive_inbox_command(project_root))
        return ("", current_thread_id)
    if command.startswith(":inbox reflection ") or command.startswith(":i reflection "):
        print()
        body = command.removeprefix(":inbox reflection").removeprefix(":i reflection").strip()
        parts = body.split(maxsplit=1)
        if not parts:
            print(_interactive_help(":inbox reflection"))
        elif parts[0] == "list":
            _print_ansi(_handle_interactive_reflection_list_command(project_root))
        elif parts[0] == "show" and len(parts) == 2:
            _print_ansi(_handle_interactive_reflection_show_command(project_root, parts[1]))
        elif len(parts) == 2:
            subcmd, entry_id = parts[0], parts[1]
            _print_ansi(_handle_interactive_reflection_subcommand(project_root, subcmd, entry_id))
        else:
            print(_interactive_help(":inbox reflection"))
        return ("", current_thread_id)
    if command in {":inbox reflection", ":i reflection"}:
        print()
        _print_ansi(_handle_interactive_reflection_command(project_root))
        return ("", current_thread_id)
    if command.startswith(":inbox notify ") or command.startswith(":i notify "):
        print()
        body = command.removeprefix(":inbox notify").removeprefix(":i notify").strip()
        parts = body.split(maxsplit=1)
        if not parts:
            print(_interactive_help(":inbox notify"))
        elif parts[0] == "list":
            _print_ansi(_handle_interactive_notify_list_command(project_root))
        elif parts[0] == "show" and len(parts) == 2:
            _print_ansi(_handle_interactive_notify_show_command(project_root, parts[1]))
        elif parts[0] == "watch":
            _handle_interactive_watch_command(project_root)
        elif len(parts) == 2:
            subcmd, entry_id = parts[0], parts[1]
            _print_ansi(_handle_interactive_notify_subcommand(project_root, subcmd, entry_id))
        else:
            print(_interactive_help(":inbox notify"))
        return ("", current_thread_id)
    if command in {":inbox notify", ":i notify"}:
        print()
        _print_ansi(_handle_interactive_notify_command(project_root))
        return ("", current_thread_id)
    if command == ":help":
        print()
        print(_interactive_help())
        return ("", current_thread_id)
    if command == ":dev status":
        print()
        print(_format_status(lifecycle.status(project_root)))
        return ("", current_thread_id)
    if command == ":dev logs":
        print()
        _print_recent_logs(project_root, limit=8)
        return ("", current_thread_id)
    if command == ":dev":
        print()
        print(_interactive_help(":dev"))
        return ("", current_thread_id)
    if command in {":export", ":e"} or command.startswith(":export ") or command.startswith(":e "):
        print()
        _print_ansi(_handle_interactive_export_command(command, project_root, current_thread_id, session))
        return ("", current_thread_id)
    if command in {":mem", ":m"}:
        print()
        _print_ansi(_format_memory_preview(project_root))
        return ("", current_thread_id)
    if command.startswith(":mem ") or command.startswith(":m "):
        print()
        body = command.removeprefix(":mem").removeprefix(":m").strip()
        _print_ansi(_handle_interactive_memory_command(body, project_root))
        return ("", current_thread_id)
    if command in {":thread", ":t"}:
        print()
        _print_ansi(_handle_interactive_threads_command(project_root))
        return ("", current_thread_id)
    if command.startswith(":thread ") or command.startswith(":t "):
        print()
        new_id = command.removeprefix(":thread").removeprefix(":t").strip()
        if new_id == "":
            print(_interactive_help(":thread"))
        else:
            store = ThreadStore(project_root)
            if new_id not in store.list():
                store.save(ThreadState.empty(new_id))
            print(f"Switched to thread: {new_id}")
        return ("redraw_header", new_id if new_id != "" else current_thread_id)
    if command.startswith(":reason watch"):
        print()
        body = command.removeprefix(":reason watch").strip()
        thread_ref = body if body else None
        _handle_interactive_reason_watch(project_root, thread_ref=thread_ref)
        return ("", current_thread_id)
    if command.startswith(":reason"):
        print()
        body = command.removeprefix(":reason").strip()
        _print_ansi(_handle_interactive_reason_command(body, project_root))
        return ("", current_thread_id)
    if command.startswith(":trace"):
        print()
        body = command.removeprefix(":trace").strip()
        _print_ansi(_handle_interactive_trace_command(body, project_root))
        return ("", current_thread_id)
    if command in {":persona", ":p"}:
        print()
        _print_ansi(_handle_interactive_persona_command("list", project_root))
        return ("", current_thread_id)
    if command.startswith(":persona ") or command.startswith(":p "):
        print()
        prefix = ":persona " if command.startswith(":persona ") else ":p "
        body = command.removeprefix(prefix).strip()
        _print_ansi(_handle_interactive_persona_command(body, project_root))
        return ("", current_thread_id)
    if command in {":restart", ":r"}:
        print()
        _print_ansi(_handle_interactive_restart_command(project_root))
        return ("redraw_header", current_thread_id)
    if command.startswith(":rename "):
        print()
        new_id = command[8:].strip()
        if new_id == "":
            print(_interactive_help(":rename"))
        else:
            try:
                ThreadStore(project_root).rename(current_thread_id, new_id)
                print(f"Renamed thread to: {new_id}")
            except ValueError as exc:
                print(f"Error: {exc}")
        return ("redraw_header", new_id if new_id != "" else current_thread_id)
    if command.startswith(":branch "):
        print()
        parts = command[8:].strip().split()
        new_id = parts[0] if parts else ""
        index: int | None = None
        if len(parts) >= 2:
            try:
                index = int(parts[1])
            except ValueError:
                print(f"Invalid index: {parts[1]}")
                return ("", current_thread_id)
        if new_id == "":
            print(_interactive_help(":branch"))
        else:
            try:
                ThreadStore(project_root).branch(current_thread_id, new_id, index)
                print(f"Branched to thread: {new_id}")
            except ValueError as exc:
                print(f"Error: {exc}")
        return ("redraw_header", new_id if new_id != "" else current_thread_id)
    if command == ":archive":
        print()
        try:
            ThreadStore(project_root).archive(current_thread_id)
            print(f"Archived thread: {current_thread_id}")
        except ValueError as exc:
            print(f"Error: {exc}")
        return ("redraw_header", "default")
    if command.startswith(":unarchive "):
        print()
        thread_id = command[11:].strip()
        if thread_id == "":
            print(_interactive_help(":unarchive"))
        else:
            try:
                ThreadStore(project_root).unarchive(thread_id)
                print(f"Unarchived thread: {thread_id}")
            except ValueError as exc:
                print(f"Error: {exc}")
        return ("", current_thread_id)
    if command == ":archived":
        print()
        store = ThreadStore(project_root)
        ids = store.list_archived()
        if not ids:
            print("No archived threads.")
        else:
            for thread_id in ids:
                print(thread_id)
        return ("", current_thread_id)
    if command == ":delete":
        print()
        try:
            ThreadStore(project_root).delete(current_thread_id)
            print(f"Deleted thread: {current_thread_id}")
        except ValueError as exc:
            print(f"Error: {exc}")
        return ("redraw_header", "default")
    print()
    print(_interactive_help(command))
    return ("", current_thread_id)




def _one_shot_reply(
    message: str,
    project_root: Path | None,
    thread_id: str = "default",
    *,
    turn_id: str | None = None,
) -> str:
    return ChatAgent(project_root).respond(message, thread_id=thread_id, turn_id=turn_id).reply


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


def _optional_payload_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _interactive_daemon_status(project_root: Path | None) -> str:
    status = lifecycle.status(project_root)
    return "running" if status.running else "one-shot"


def _print_recent_logs(project_root: Path | None, *, limit: int) -> None:
    events = read_log_events(project_root=project_root, tail=limit)
    if not events:
        print("No recent activity logs.")
        return
    for event in events:
        _print_ansi(render_log_event(event))


def _interactive_activity_events(
    project_root: Path | None,
    log_cursor: InteractiveLogCursor,
    *,
    turn_id: str | None = None,
) -> list[LogEvent]:
    events = log_cursor.read_new_events(project_root)
    if turn_id is None:
        return events
    return [event for event in events if event.turn_id == turn_id]


def _print_interactive_activity_events(events: list[LogEvent]) -> None:
    for event in events:
        _print_ansi(render_log_event(event))


def _visible_interactive_activity_events(events: list[LogEvent]) -> list[LogEvent]:
    return [event for event in events if _is_interactive_activity_log(event)]


def _is_interactive_activity_log(event: LogEvent) -> bool:
    if event.event == "approval_prompted":
        return True
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
        if event.event == "service_tool_called":
            return True
        if event.event in {
            "turn_started",
            "turn_completed",
            "turn_reused",
            "turn_retry",
            "final_response_retry",
            "final_response_completed",
        }:
            return True
        return _is_failure_activity_log(event)
    if event.component == "daemon":
        return _is_failure_activity_log(event)
    return False


def _is_failure_activity_log(event: LogEvent) -> bool:
    if event.status in {"error", "failed", "failed_over", "exhausted"}:
        return True
    return event.event in {
        "chat_turn_failed",
        "daemon_chat_failed",
        "final_response_failed",
        "llm_endpoint_failed_over",
        "llm_endpoint_unavailable",
        "turn_failed",
    }


def _handle_interactive_export_command(
    command: str,
    project_root: Path | None,
    thread_id: str,
    session: InteractiveSession,
) -> str:
    body = command.removeprefix(":export") if command.startswith(":export") else command.removeprefix(":e")
    args = body.strip().split()
    copy_requested = True
    include_all_logs = False
    if args:
        for arg in args:
            if arg == "all":
                include_all_logs = True
            elif arg == "noclip":
                copy_requested = False
            elif arg in {"--copy", "copy"}:
                copy_requested = True
            else:
                return _interactive_help(":export")

    exported_at = datetime.now(UTC)
    return _save_interactive_transcript(
        project_root,
        thread_id,
        session,
        include_all_logs=include_all_logs,
        copy_requested=copy_requested,
        exported_at=exported_at,
    )


def _auto_save_interactive_transcripts(project_root: Path | None, session: InteractiveSession) -> None:
    thread_ids = session.thread_ids_with_unexported_messages(project_root)
    if not thread_ids:
        return
    print()
    exported_at = datetime.now(UTC)
    for thread_id in thread_ids:
        print(
            _save_interactive_transcript(
                project_root,
                thread_id,
                session,
                include_all_logs=False,
                copy_requested=False,
                exported_at=exported_at,
            )
        )


def _save_interactive_transcript(
    project_root: Path | None,
    thread_id: str,
    session: InteractiveSession,
    *,
    include_all_logs: bool,
    copy_requested: bool,
    exported_at: datetime,
) -> str:
    try:
        start_index = session.start_index_for(project_root, thread_id)
        path, content = _export_interactive_transcript(
            project_root,
            thread_id=thread_id,
            start_index=start_index,
            connected_at=session.connected_at,
            exported_at=exported_at,
            messages=session.transcript_messages(project_root, thread_id),
            log_events=session.transcript_log_events(thread_id, include_all=include_all_logs),
            log_events_by_message=session.transcript_log_events_by_message(thread_id, include_all=include_all_logs),
            include_all_logs=include_all_logs,
        )
    except ValueError as exc:
        return f"Error: {exc}"

    session.mark_transcript_exported(project_root, thread_id)
    lines = [f"Saved transcript: {path}"]
    if copy_requested:
        copied, reason = _copy_text_to_clipboard(content)
        if copied:
            lines.append("Copied transcript to clipboard.")
        else:
            lines.append(f"Clipboard copy failed: {reason}")
    return "\n".join(lines)









if __name__ == "__main__":
    raise SystemExit(main())
