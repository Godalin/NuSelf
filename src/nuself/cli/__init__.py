"""Command-line interface for NuSelf."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import sys
import threading
import time
from uuid import uuid4
import warnings

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.shortcuts import prompt as _prompt
from prompt_toolkit.styles import Style

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
    from nuself.cli.repl.transcript import (
        copy_text_to_clipboard as _copy_text_to_clipboard,
        export_interactive_transcript as _export_interactive_transcript,
        is_shareable_transcript_log as _is_shareable_transcript_log,
        render_chat_transcript as _render_chat_transcript,
        thread_messages_from_index as _thread_messages_from_index,
    )
    from nuself.config import ensure_runtime_dirs, runtime_paths
    from nuself.agent.chat import ChatAgent, ThreadState, ThreadStore
    from nuself.daemon import client, lifecycle
    from nuself.daemon.protocol import JsonValue
    from nuself.cli.commands.daemon import (
        format_status as _format_status,
    )
    from nuself.cli.commands.output import (
        print_ansi as _print_ansi,
    )
    from nuself.cli.commands.persona import (
        handle_persona_create,
        handle_persona_delete,
        handle_persona_disable,
        handle_persona_enable,
        resolve_persona_id as _resolve_persona_id,
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
    from nuself.memory.repository import (
        MemoryCandidateNotFound,
        MemoryCandidateRepository,
        MemoryEntryNotFound,
        MemoryEntryRepository,
    )
    from nuself.memory.source_repository import SourceDocumentNotFound, SourceRepository
    from nuself.profile.repository import ProfileItemRepository
    from nuself.trace.repository import TraceNotFound
    from nuself.trace.service import TraceQueryService
    from nuself.logs import (
        InteractiveLogCursor,
        LogEvent,
        read_log_events,
        write_log_event,
    )
    from nuself.config import ConfigSystem
    from nuself.tui.memory import (
        render_candidate_detail,
        render_candidate_row,
        render_memory_entry_detail,
        render_memory_entry_row,
        render_profile_row,
        render_source_detail,
        render_source_row,
    )
    from nuself.reason.service import ReasonService
    from nuself.reason.repository import ReasonNotFound
    from nuself.tui.reason import render_reason_detail, render_reason_row
    from nuself.tui.render import TerminalTheme, render_log_event, render_session_header
    from nuself.tui.trace import render_trace_detail, render_trace_row
    from nuself.persona.prompt_repo import PersonaPromptRepository
    from nuself.storage import auto_backend
finally:
    warnings.warn = _original_warn

__all__ = [
    "_render_chat_transcript",
    "build_parser",
    "main",
]

CHAT_REQUEST_TIMEOUT_SECONDS = 120.0
DEFAULT_MEMORY_PREVIEW_LIMIT = 8
INTERACTIVE_CHAT_ATTEMPTS = 2
INTERACTIVE_LOG_POLL_INTERVAL_SECONDS = 0.1

class _DedupFileHistory(FileHistory):
    """FileHistory that skips consecutive duplicate entries."""

    def append_string(self, string: str) -> None:
        loaded = self.get_strings()
        if loaded and loaded[-1] == string:
            return
        super().append_string(string)


_PROMPT_STYLE = Style.from_dict({
    "ansicyan": "ansicyan bold",
})

_PROMPT_TEXT = FormattedText([("class:ansicyan bold", "\nNuSelf> ")])

_history: FileHistory | None = None
_interactive_completer: _InteractiveCompleter | None = None
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


def _init_interactive_input(project_root: Path | None) -> None:
    global _history, _interactive_completer
    paths = runtime_paths(project_root)
    ensure_runtime_dirs(paths)
    history_path = paths.runtime_dir / "interactive_history"
    _history = _DedupFileHistory(str(history_path))
    _interactive_completer = _InteractiveCompleter(project_root)


def _read_interactive_input() -> str:
    """Read a line of input with prompt_toolkit (styled), falling back to input()."""
    try:
        if sys.stdin.isatty():
            assert _history is not None
            return _prompt(
                _PROMPT_TEXT,
                style=_PROMPT_STYLE,
                history=_history,
                completer=_interactive_completer,
            )
    except (AttributeError, OSError):
        pass
    line = input("NuSelf> ")
    _append_history(line)
    return line


def _append_history(line: str) -> None:
    if _history is not None and line:
        _history.append_string(line)


def empty_thread_start_indexes() -> dict[str, int]:
    return {}


def empty_captured_thread_messages() -> dict[str, list[tuple[int, str, str]]]:
    return {}


def empty_captured_log_events() -> dict[str, list[LogEvent]]:
    return {}


def empty_captured_log_events_by_message() -> dict[str, dict[int, list[LogEvent]]]:
    return {}


@dataclass
class InteractiveSession:
    """State that belongs to one interactive CLI connection."""

    connected_at: datetime
    thread_start_indexes: dict[str, int] = field(default_factory=empty_thread_start_indexes)
    captured_messages: dict[str, list[tuple[int, str, str]]] = field(default_factory=empty_captured_thread_messages)
    captured_next_indexes: dict[str, int] = field(default_factory=empty_thread_start_indexes)
    captured_log_events: dict[str, list[LogEvent]] = field(default_factory=empty_captured_log_events)
    captured_log_events_by_message: dict[str, dict[int, list[LogEvent]]] = field(
        default_factory=empty_captured_log_events_by_message
    )
    exported_next_indexes: dict[str, int] = field(default_factory=empty_thread_start_indexes)

    def start_index_for(self, project_root: Path | None, thread_id: str) -> int:
        if thread_id not in self.thread_start_indexes:
            next_index = ThreadStore(project_root).load(thread_id).next_message_index
            self.thread_start_indexes[thread_id] = next_index
            self.captured_next_indexes[thread_id] = next_index
        return self.thread_start_indexes[thread_id]

    def capture_new_messages(self, project_root: Path | None, thread_id: str) -> None:
        start_index = self.start_index_for(project_root, thread_id)
        capture_start = self.captured_next_indexes.get(thread_id, start_index)
        thread = ThreadStore(project_root).load(thread_id)
        new_messages = _thread_messages_from_index(thread, capture_start)
        if not new_messages:
            return
        self.captured_messages.setdefault(thread_id, []).extend(new_messages)
        self.captured_next_indexes[thread_id] = new_messages[-1][0] + 1

    def transcript_messages(self, project_root: Path | None, thread_id: str) -> list[tuple[int, str, str]]:
        self.capture_new_messages(project_root, thread_id)
        return list(self.captured_messages.get(thread_id, []))

    def capture_log_events(self, thread_id: str, events: list[LogEvent], *, message_index: int | None = None) -> None:
        if not events:
            return
        if message_index is not None:
            events_by_message = self.captured_log_events_by_message.setdefault(thread_id, {})
            events_by_message.setdefault(message_index, []).extend(events)
            return
        self.captured_log_events.setdefault(thread_id, []).extend(events)

    def transcript_log_events(self, thread_id: str, *, include_all: bool) -> list[LogEvent]:
        events = list(self.captured_log_events.get(thread_id, []))
        if include_all:
            return events
        return [event for event in events if _is_shareable_transcript_log(event)]

    def transcript_log_events_by_message(self, thread_id: str, *, include_all: bool) -> dict[int, list[LogEvent]]:
        result: dict[int, list[LogEvent]] = {}
        for message_index, events in self.captured_log_events_by_message.get(thread_id, {}).items():
            filtered_events = events if include_all else [event for event in events if _is_shareable_transcript_log(event)]
            if filtered_events:
                result[message_index] = list(filtered_events)
        return result

    def has_unexported_messages(self, project_root: Path | None, thread_id: str) -> bool:
        self.capture_new_messages(project_root, thread_id)
        next_index = self.captured_next_indexes.get(thread_id, self.start_index_for(project_root, thread_id))
        exported_index = self.exported_next_indexes.get(thread_id, self.start_index_for(project_root, thread_id))
        return next_index > exported_index

    def mark_transcript_exported(self, project_root: Path | None, thread_id: str) -> None:
        self.capture_new_messages(project_root, thread_id)
        self.exported_next_indexes[thread_id] = self.captured_next_indexes.get(
            thread_id, self.start_index_for(project_root, thread_id)
        )

    def thread_ids_with_unexported_messages(self, project_root: Path | None) -> list[str]:
        thread_ids = set(self.thread_start_indexes)
        thread_ids.update(self.captured_messages)
        result: list[str] = []
        for thread_id in sorted(thread_ids):
            if self.has_unexported_messages(project_root, thread_id):
                result.append(thread_id)
        return result


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


_INTERACTIVE_COMMANDS = [
    ":q",
    ":quit",
    ":exit",
    ":history",
    ":whoami",
    ":help",
    ":export",
    ":e",
    ":mem",
    ":m",
    ":inbox",
    ":i",
    ":thread",
    ":t",
    ":reason",
    ":trace",
    ":persona", ":p",
    ":restart",
    ":r",
    ":dev",
    ":rename",
    ":branch",
    ":archive",
    ":unarchive",
    ":archived",
    ":delete",
]


class _InteractiveCompleter(Completer):
    def __init__(self, project_root: Path | None) -> None:
        super().__init__()
        self._project_root = project_root

    def get_completions(self, document: Document, complete_event: object) -> Iterable[Completion]:
        text = document.text_before_cursor
        stripped = text.lstrip()
        word = text.split()[-1] if text.split() else ""

        if (stripped.startswith(":thread ") or stripped.startswith(":t ")) and word and not word.startswith(":"):
            yield from self._thread_completions(word)
            return
        if stripped.startswith(":unarchive ") and word and not word.startswith(":"):
            yield from self._archived_thread_completions(word)
            return
        if text.rstrip().endswith(":reason") or text.rstrip().endswith(":re"):
            # Cursor at :reason or :re — offer all subcommands
            for cmd, desc, _ in self._REASON_SUBCOMMANDS:
                yield Completion(f"{cmd} ", start_position=0, display=cmd, display_meta=desc)
            return
        if (stripped.startswith(":reason ") or stripped.startswith(":re ")) and word and not word.startswith(":"):
            yield from self._reason_subcommand_completions(stripped, word)
            return
        if word.startswith(":"):
            for cmd in _INTERACTIVE_COMMANDS:
                if cmd.startswith(word):
                    yield Completion(cmd, start_position=-len(word))

    _REASON_SUBCOMMANDS: list[tuple[str, str, bool]] = [
        ("list", "List active and paused reasoning threads", False),
        ("show", "Show details for a reasoning thread", True),
        ("start", "Create a new reasoning thread from a topic", False),
        ("advance", "Advance a thread with the next reasoning step", True),
        ("pause", "Pause a reasoning thread", True),
        ("resume", "Resume a paused reasoning thread", True),
        ("resolve", "Mark a reasoning thread as resolved", True),
        ("archive", "Archive a resolved or inactive thread", True),
        ("delete", "Permanently delete a reasoning thread", True),
        ("watch", "Watch for new reasoning steps in real-time", False),
    ]

    def _reason_subcommand_completions(self, stripped: str, word: str) -> Iterable[Completion]:
        prefix = stripped.removeprefix(":reason ").removeprefix(":re ")
        subcmd = prefix.split()[0] if prefix.strip() else ""
        # After a subcommand that takes a thread id, offer thread completions
        needs_id = any(cmd == subcmd for cmd, _, needs in self._REASON_SUBCOMMANDS if needs)
        if subcmd and needs_id and prefix.strip() != subcmd:
            thread_words = prefix.removeprefix(subcmd).strip()
            for tid in self._all_thread_ids_with_status():
                if thread_words == "" or tid.startswith(thread_words):
                    yield Completion(tid, start_position=-len(thread_words) if thread_words else 0)
            return
        # Offer subcommand completions with descriptions
        for cmd, desc, _ in self._REASON_SUBCOMMANDS:
            if cmd.startswith(word):
                yield Completion(f"{cmd} ", start_position=-len(word), display=cmd, display_meta=desc)

    def _all_thread_ids_with_status(self) -> list[str]:
        try:
            from nuself.reason.repository import ReasonRepository
            repo = ReasonRepository(self._project_root)
            return [f"{t.id} ({t.status}, {t.topic[:40]})" for t in repo.list_threads(status="all")]
        except Exception:
            return []

    def _thread_completions(self, word: str) -> Iterable[Completion]:
        try:
            threads = ThreadStore(self._project_root).list()
        except Exception:
            return ()
        for t in threads:
            if t.startswith(word):
                yield Completion(t, start_position=-len(word))

    def _archived_thread_completions(self, word: str) -> Iterable[Completion]:
        try:
            threads = ThreadStore(self._project_root).list_archived()
        except Exception:
            return ()
        for t in threads:
            if t.startswith(word):
                yield Completion(t, start_position=-len(word))


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


def _interactive_command_hints(partial: str) -> list[str]:
    return [cmd for cmd in _INTERACTIVE_COMMANDS if cmd.startswith(partial) and cmd != partial]


def _interactive_help(command: str | None = None) -> str:
    lines: list[str] = []
    if command is not None:
        lines.append(f"Unknown interactive command: {command}")
        hints = _interactive_command_hints(command)
        if hints:
            lines.append(f"Did you mean: {', '.join(hints)}?")
    lines.extend(
        [
            "Interactive commands:",
            "  :q         exit",
            "  :quit      exit",
            "  :exit      exit",
            "  :history   show recent thread messages",
            "  :whoami    show core profile",
            "  :inbox, :i                    list pending reflections and notifications",
            "  :inbox reflection             list pending reflection ideas",
            "  :inbox reflection list        list reflection ideas",
            "  :inbox reflection show <id>   show one reflection idea",
            "  :inbox reflection dismiss <id> dismiss a reflection idea",
            "  :inbox reflection archive <id> archive a reflection idea",
            "  :inbox reflection promote <id> promote a reflection into reason",
            "  :inbox notify                 list pending notifications",
            "  :inbox notify list            list all notifications",
            "  :inbox notify show <id>       show one notification",
            "  :inbox notify send <id>       send a notification",
            "  :inbox notify dismiss <id>    dismiss a notification",
            "  :inbox notify watch           watch outbox for new entries",
            "  :help      show this help",
            "  :dev status                   show daemon and thread status",
            "  :dev logs                     show recent activity logs",
            "  :export [all] [noclip]    save and copy this connection's transcript",
            "  :e [all] [noclip]         shorthand for :export",
            "  :mem, :m                  preview memory entries",
            "  :mem search <query>       search memory entries",
            "  :mem show <entry-id>      show one memory entry",
            "  :mem review               list pending memory review items",
            "  :mem review <id>          show one memory review item",
            "  :mem profile <query>      search profile items",
            "  :mem sources              list imported sources",
            "  :mem source <source-id>   show one source",
            "  :thread, :t               list active threads",
            "  :thread <id>, :t <id>     switch to or create a thread",
            "  :reason                   long-run reasoning commands",
            "  :persona, :p             list/manage custom personas",
            "  :trace                    list thought trace records",
            "  :trace show <id|index>    show one thought trace",
            "  :trace search <query>     search thought trace records",
            "  :restart, :r              restart daemon and reconnect",
            "  :rename <new-id>          rename the current thread",
            "  :branch <new-id> [index]  branch current thread at index",
            "  :archive                  archive the current thread",
            "  :unarchive <id>           restore an archived thread",
            "  :archived                 list archived threads",
            "  :delete                   delete the current thread",
        ]
    )
    return "\n".join(lines)


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


def _indent_lines(lines: list[str], prefix: str) -> list[str]:
    return [f"{prefix}{line}" if line else "" for line in lines]


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




def _handle_interactive_memory_search(query: str, project_root: Path | None) -> str:
    entries = MemoryEntryRepository(project_root).search(query)
    if not entries:
        return "No matching memory entries."
    return "\n".join(render_memory_entry_row(entry) for entry in entries)


def _handle_interactive_memory_command(command: str, project_root: Path | None) -> str:
    if command == "why":
        return "No memory-context trace is available for the last answer yet."
    if command.startswith("search "):
        query = command.removeprefix("search ").strip()
        return _handle_interactive_memory_search(query, project_root)
    if command.startswith("show "):
        entry_id = command.removeprefix("show ").strip()
        if entry_id.isdigit():
            entries = MemoryEntryRepository(project_root).list()
            index = int(entry_id)
            if 0 <= index < len(entries):
                entry_id = entries[index].id
        try:
            entry = MemoryEntryRepository(project_root).get(entry_id)
        except MemoryEntryNotFound:
            return f"Memory entry not found: {entry_id}"
        return render_memory_entry_detail(entry)
    if command == "review":
        candidates = MemoryCandidateRepository(project_root).list()
        if not candidates:
            return "No memory candidates."
        return "\n".join(render_candidate_row(candidate, index=index) for index, candidate in enumerate(candidates))
    if command.startswith("review "):
        candidate_id = command.removeprefix("review ").strip()
        if candidate_id.isdigit():
            candidates = MemoryCandidateRepository(project_root).list()
            index = int(candidate_id)
            if 0 <= index < len(candidates):
                candidate_id = candidates[index].id
        try:
            candidate = MemoryCandidateRepository(project_root).get(candidate_id)
        except MemoryCandidateNotFound:
            return f"Memory candidate not found: {candidate_id}"
        return render_candidate_detail(candidate)
    if command.startswith("profile "):
        query = command.removeprefix("profile ").strip()
        items = ProfileItemRepository(project_root).search(query)
        if not items:
            return "No matching profile items."
        return "\n".join(render_profile_row(item) for item in items)
    if command == "sources":
        repo = SourceRepository(project_root)
        documents = repo.list_documents()
        if not documents:
            return "No source documents."
        return "\n".join(
            render_source_row(document, index=index, chunk_count=len(repo.list_chunks(document.id)))
            for index, document in enumerate(documents)
        )
    if command.startswith("source "):
        source_id = command.removeprefix("source ").strip()
        repo = SourceRepository(project_root)
        if source_id.isdigit():
            documents = repo.list_documents()
            index = int(source_id)
            if 0 <= index < len(documents):
                source_id = documents[index].id
        try:
            document = repo.get_document(source_id)
        except SourceDocumentNotFound:
            return f"Source document not found: {source_id}"
        return render_source_detail(document, chunk_count=len(repo.list_chunks(document.id)))
    return _interactive_memory_help(command)


def _handle_interactive_reason_command(command: str, project_root: Path | None) -> str:
    service = ReasonService(project_root)
    if command == "":
        return _interactive_reason_help()
    if command == "list":
        threads = service.list_threads(status="all")
        if not threads:
            return "No reason threads."
        return "\n".join(render_reason_row(thread, index=index) for index, thread in enumerate(threads))
    if command.startswith("show "):
        thread_id = command.removeprefix("show ").strip()
        try:
            thread = service.show_thread(thread_id)
        except ReasonNotFound:
            return f"Reason thread not found: {thread_id}"
        steps = service.list_steps(thread.id)
        return render_reason_detail(thread, steps)
    if command.startswith("start "):
        question = command.removeprefix("start ").strip()
        try:
            thread = service.start_thread(question)
        except RuntimeError as exc:
            return f"Error: {exc}"
        return f"Started reason thread: {thread.id}\n{render_reason_detail(thread)}"
    if command.startswith("advance "):
        thread_id = command.removeprefix("advance ").strip()
        from nuself.llm import configured_langchain_chat_models
        from nuself.reason.advancer import ReasonAdvancer
        from nuself.workspace import PrivateWorkspaceStore

        advancer = ReasonAdvancer(project_root=project_root, workspace_store=PrivateWorkspaceStore(project_root, scope="reason"), langchain_models=configured_langchain_chat_models(project_root))
        service = ReasonService(project_root, advancer=advancer)
        try:
            thread = service.advance_thread(thread_id)
        except (ReasonNotFound, RuntimeError) as exc:
            return f"Error: {exc}"
        return f"Advanced reason thread: {thread.id}\n{render_reason_detail(thread, service.list_steps(thread.id))}"
    if command.startswith("pause "):
        thread_id = command.removeprefix("pause ").strip()
        try:
            thread = service.pause_thread(thread_id)
        except (ReasonNotFound, RuntimeError) as exc:
            return f"Error: {exc}"
        return f"Paused reason thread: {thread.id}\n{render_reason_detail(thread)}"
    if command.startswith("resume "):
        thread_id = command.removeprefix("resume ").strip()
        try:
            thread = service.resume_thread(thread_id)
        except (ReasonNotFound, RuntimeError) as exc:
            return f"Error: {exc}"
        return f"Resumed reason thread: {thread.id}\n{render_reason_detail(thread)}"
    if command.startswith("resolve "):
        thread_id = command.removeprefix("resolve ").strip()
        try:
            thread = service.resolve_thread(thread_id)
        except (ReasonNotFound, RuntimeError) as exc:
            return f"Error: {exc}"
        return f"Resolved reason thread: {thread.id}\n{render_reason_detail(thread)}"
    if command.startswith("archive "):
        thread_id = command.removeprefix("archive ").strip()
        try:
            thread = service.archive_thread(thread_id)
        except (ReasonNotFound, RuntimeError) as exc:
            return f"Error: {exc}"
        return f"Archived reason thread: {thread.id}\n{render_reason_detail(thread)}"
    if command.startswith("delete "):
        thread_id = command.removeprefix("delete ").strip()
        try:
            tid = service.delete_thread(thread_id)
        except (ReasonNotFound, RuntimeError) as exc:
            return f"Error: {exc}"
        return f"Deleted reason thread: {tid}"
    return _interactive_reason_help(command)


def _interactive_reason_help(command: str | None = None) -> str:
    lines: list[str] = []
    if command is not None:
        lines.append(f"Unknown reason command: :reason {command}")
    lines.extend(
        [
            "Reason commands:",
            "  :reason",
            "  :reason list",
            "  :reason show <id|index>",
            "  :reason start <topic>",
            "  :reason advance <id|index>",
            "  :reason pause <id|index>",
            "  :reason resume <id|index>",
            "  :reason resolve <id|index>",
            "  :reason archive <id|index>",
            "  :reason delete <id|index>",
            "  :reason watch              watch for new reasoning steps (Ctrl+C to stop)",
        ]
    )
    return "\n".join(lines)


def _handle_interactive_reason_watch(project_root: Path | None, interval: int = 2, thread_ref: str | None = None) -> None:
    """Watch for new reasoning steps and print them.

    If *thread_ref* is given (id or index), watch only that thread.
    """
    import time

    from nuself.reason.service import ReasonService
    from nuself.reason.repository import ReasonNotFound
    from nuself.tui.reason import render_reason_detail, render_step_watch_entry

    service = ReasonService(project_root)
    threads = service.list_threads(status="all")
    if thread_ref is not None:
        try:
            thread = service.show_thread(thread_ref)
        except ReasonNotFound:
            print(f"Reason thread not found: {thread_ref}", file=sys.stderr)
            return
        threads = [thread]
        _print_ansi(render_reason_detail(thread))
        for step in service.list_steps(thread.id):
            _print_ansi(render_step_watch_entry(step))
    else:
        for index, thread in enumerate(threads):
            _print_ansi(render_reason_detail(thread))
            _print_ansi(_theme.muted(f"(index: {index})"))
            for step in service.list_steps(thread.id):
                _print_ansi(render_step_watch_entry(step))
    print()
    print("Watching for new reasoning steps. Press Ctrl+C to stop.")

    # Track step count per thread for polling.
    counts: dict[str, int] = {}
    for thread in threads:
        counts[thread.id] = len(service.list_steps(thread.id))

    try:
        while True:
            time.sleep(interval)
            for thread in threads:
                steps = service.list_steps(thread.id)
                if len(steps) > counts.get(thread.id, 0):
                    for step in steps[counts[thread.id]:]:
                        _print_ansi(render_step_watch_entry(step))
                    counts[thread.id] = len(steps)
    except KeyboardInterrupt:
        print("\nStopped watching.")


def _handle_interactive_trace_command(command: str, project_root: Path | None) -> str:
    service = TraceQueryService(project_root)
    if command in {"", "list"}:
        traces = service.list_traces()
        if not traces:
            return "No trace records."
        return "\n".join(render_trace_row(trace, index=index) for index, trace in enumerate(traces))
    if command.startswith("show "):
        trace_id = command.removeprefix("show ").strip()
        try:
            trace = service.show_trace(trace_id)
        except TraceNotFound:
            return f"Trace not found: {trace_id}"
        return render_trace_detail(trace, service.links_for(trace.id))
    if command.startswith("search "):
        query = command.removeprefix("search ").strip()
        traces = service.search_traces(query)
        if not traces:
            return "No matching trace records."
        return "\n".join(render_trace_row(trace, index=index) for index, trace in enumerate(traces))
    if command.startswith("related "):
        artifact_ref = command.removeprefix("related ").strip()
        traces = service.traces_for_artifact(artifact_ref)
        links = service.links_for_artifact(artifact_ref)
        if not traces and not links:
            return f"No trace records or links related to: {artifact_ref}"
        lines = [render_trace_row(trace, index=index) for index, trace in enumerate(traces)]
        if links:
            if lines:
                lines.append("")
            lines.append("Related links:")
            lines.extend(f"  {link.relation}: {link.source_id} -> {link.target_id} ({link.summary})" for link in links)
        return "\n".join(lines)
    return _interactive_trace_help(command)


def _handle_interactive_persona_command(command: str, project_root: Path | None) -> str:
    try:
        from nuself.tui.persona import render_persona_detail, render_persona_row

        repo = PersonaPromptRepository(backend=auto_backend(project_root))
        if command in {"", "list"}:
            prompts = repo.list()
            if not prompts:
                return f"{_theme.tag('[persona]', 'persona')} {_theme.muted('No custom personas yet')}"
            blocks: list[str] = [f"{_theme.tag('[persona]', 'persona')} Custom personas (dynamic):"]
            for i, p in enumerate(prompts):
                blocks.append(render_persona_row(p, index=i))
            return "\n".join(blocks)
        if command.startswith("show "):
            persona_id = command.removeprefix("show ").strip()
            args = argparse.Namespace(persona_id=persona_id, project_root=project_root)
            resolved = _resolve_persona_id(args)
            if resolved is None:
                return f"{_theme.tag('[persona]', 'persona')} {_theme.error('Not found')}: {persona_id}"
            prompt = repo.get(resolved)
            if prompt is None:
                return f"{_theme.tag('[persona]', 'persona')} {_theme.error('Not found')}: {persona_id}"
            return render_persona_detail(prompt)
        if command.startswith("delete "):
            persona_id = command.removeprefix("delete ").strip()
            args = argparse.Namespace(persona_id=persona_id, project_root=project_root, yes=False)
            handle_persona_delete(args)
            return ""
        if command.startswith("disable "):
            persona_id = command.removeprefix("disable ").strip()
            args = argparse.Namespace(persona_id=persona_id, project_root=project_root, yes=False)
            handle_persona_disable(args)
            return ""
        if command.startswith("enable "):
            persona_id = command.removeprefix("enable ").strip()
            args = argparse.Namespace(persona_id=persona_id, project_root=project_root, yes=False)
            handle_persona_enable(args)
            return ""
        if command.startswith("create "):
            rest = command.removeprefix("create ").strip()
            parts = rest.split(" ", 1)
            if len(parts) < 2:
                return f"{_theme.tag('[persona]', 'persona')} {_theme.error('Usage')}: :persona create <name> <prompt>"
            name, prompt_text = parts
            args = argparse.Namespace(name=name, prompt=prompt_text, project_root=project_root)
            handle_persona_create(args)
            return ""
        return _interactive_persona_help(command)
    except Exception as exc:
        return f"{_theme.tag('[persona]', 'persona')} {_theme.error(str(exc))}"


def _handle_interactive_restart_command(project_root: Path | None) -> str:
    write_log_event("daemon", "restart_requested", "daemon restart requested", project_root=project_root)
    stop_result = lifecycle.stop(project_root)
    if stop_result.running:
        return f"Failed to stop daemon: {_format_status(stop_result)}"
    start_result = lifecycle.start(project_root)
    write_log_event(
        "daemon",
        "restart_completed",
        f"daemon restart {'completed' if start_result.running else 'failed'}",
        project_root=project_root,
        status="running" if start_result.running else "stopped",
        metadata={"pid": start_result.pid, "socket": str(start_result.socket_path)},
    )
    if not start_result.running:
        return f"Failed to restart daemon: {_format_status(start_result)}"
    return f"Restarted daemon: {_format_status(start_result)}"


def _interactive_persona_help(command: str | None = None) -> str:
    lines: list[str] = []
    if command is not None:
        lines.append(f"Unknown persona command: :persona {command}")
    lines.extend(
        [
            "Persona commands:",
            "  :persona",
            "  :persona list",
            "  :persona show <id|index>",
            "  :persona create <name> <prompt>",
            "  :persona delete <id|index>",
            "  :persona disable <id|index>",
            "  :persona enable <id|index>",
        ]
    )
    return "\n".join(lines)


def _interactive_trace_help(command: str | None = None) -> str:
    lines: list[str] = []
    if command is not None:
        lines.append(f"Unknown trace command: :trace {command}")
    lines.extend(
        [
            "Trace commands:",
            "  :trace",
            "  :trace list",
            "  :trace show <id|index>",
            "  :trace search <query>",
            "  :trace related <artifact_ref>",
        ]
    )
    return "\n".join(lines)


def _interactive_memory_help(command: str | None = None) -> str:
    lines: list[str] = []
    if command is not None:
        lines.append(f"Unknown memory command: :mem {command}")
    lines.extend(
        [
            "Memory commands:",
            "  :mem search <query>",
            "  :mem show <entry-id|index>",
            "  :mem review",
            "  :mem review <candidate-id|index>",
            "  :mem profile <query>",
            "  :mem sources",
            "  :mem source <source-id|index>",
            "  :mem why",
        ]
    )
    return "\n".join(lines)


def _handle_interactive_history_command(project_root: Path | None, thread_id: str) -> str:
    from nuself.agent.chat import ThreadStore

    try:
        state = ThreadStore(project_root).load(thread_id)
    except Exception:
        return "No thread state available."
    if not state.messages:
        return "No messages in this thread."
    lines = [f"Recent messages in '{thread_id}':"]
    for msg in state.messages[-10:]:
        prefix = ">" if msg.role == "user" else "<"
        content = msg.content[:120]
        if len(msg.content) > 120:
            content += "..."
        lines.append(f"  {prefix} {content}")
    return "\n".join(lines)


def _handle_interactive_whoami_command(project_root: Path | None) -> str:
    repo = ProfileItemRepository(project_root)
    items = repo.list()
    if not items:
        return "No profile items yet."
    lines = ["Core profile:"]
    for item in items[:6]:
        lines.append(f"  {item.id}: {item.body[:80]}")
    if len(items) > 6:
        lines.append(f"  ... and {len(items) - 6} more")
    return "\n".join(lines)


def _handle_interactive_reflection_command(project_root: Path | None) -> str:
    from nuself.reflection.repository import ReflectionRepository
    from nuself.tui.render import render_reflection_entry_summary

    entries = ReflectionRepository(project_root).list(status="pending")
    if not entries:
        return "No pending reflection ideas."
    lines = ["Pending reflection ideas:"]
    for idx, entry in enumerate(entries):
        lines.extend(_indent_lines(render_reflection_entry_summary(entry, index=idx).splitlines(), "  "))
    return "\n".join(lines)


def _handle_interactive_inbox_command(project_root: Path | None) -> str:
    sections = [
        _handle_interactive_reflection_command(project_root),
        _handle_interactive_notify_command(project_root),
    ]
    return "\n\n".join(sections)


def _handle_interactive_reflection_list_command(project_root: Path | None) -> str:
    from nuself.reflection.repository import ReflectionRepository
    from nuself.tui.render import render_reflection_entry_summary

    entries = ReflectionRepository(project_root).list()
    if not entries:
        return "No reflection ideas."
    lines = ["All reflection ideas:"]
    for idx, entry in enumerate(entries):
        lines.extend(_indent_lines(render_reflection_entry_summary(entry, index=idx).splitlines(), "  "))
    return "\n".join(lines)


def _handle_interactive_reflection_show_command(project_root: Path | None, entry_id: str) -> str:
    from nuself.reflection.repository import ReflectionEntryNotFound, ReflectionRepository
    from nuself.tui.render import render_reflection_entry_detail

    try:
        entry = ReflectionRepository(project_root).get(entry_id)
    except ReflectionEntryNotFound:
        return f"Reflection entry not found: {entry_id}"
    return render_reflection_entry_detail(entry)


def _handle_interactive_reflection_subcommand(project_root: Path | None, subcmd: str, entry_id: str) -> str:
    from nuself.reflection.repository import ReflectionEntryNotFound, ReflectionRepository

    repo = ReflectionRepository(project_root)
    try:
        repo.get(entry_id)
    except ReflectionEntryNotFound:
        return f"Reflection entry not found: {entry_id}"
    if subcmd == "dismiss":
        repo.dismiss(entry_id)
        return f"Dismissed: {entry_id}"
    if subcmd == "archive":
        repo.archive(entry_id)
        return f"Archived: {entry_id}"
    if subcmd == "promote":
        from nuself.reflection.service import ReflectionService

        try:
            thread = ReflectionService(project_root, repository=repo).promote_to_reason(entry_id)
        except RuntimeError as exc:
            return f"Error: {exc}"
        return f"Promoted reflection to reason thread: {thread.id}\n{render_reason_detail(thread)}"
    return f"Unknown :inbox reflection subcommand: {subcmd}"


def _handle_interactive_notify_command(project_root: Path | None) -> str:
    from nuself.notification import NotificationOutbox
    from nuself.tui.render import render_outbox_summary

    entries = NotificationOutbox(project_root).list(status="pending")
    if not entries:
        return "No pending notifications."
    lines = ["Pending notifications:"]
    for index, entry in enumerate(entries):
        lines.append("  " + render_outbox_summary(entry, index=index))
    return "\n".join(lines)


def _handle_interactive_notify_list_command(project_root: Path | None) -> str:
    from nuself.notification import NotificationOutbox
    from nuself.tui.render import render_outbox_summary

    entries = NotificationOutbox(project_root).list()
    if not entries:
        return "No notifications."
    lines = ["All notifications:"]
    for index, entry in enumerate(entries):
        lines.append("  " + render_outbox_summary(entry, index=index))
    return "\n".join(lines)


def _handle_interactive_notify_show_command(project_root: Path | None, entry_id: str) -> str:
    from nuself.notification import NotificationOutbox, OutboxEntryNotFound
    from nuself.tui.render import render_outbox_detail

    try:
        entry = NotificationOutbox(project_root).get(entry_id)
    except OutboxEntryNotFound:
        return f"Outbox entry not found: {entry_id}"
    return render_outbox_detail(entry)


def _handle_interactive_notify_subcommand(project_root: Path | None, subcmd: str, entry_id: str) -> str:
    from nuself.notification import NotificationOutbox, LogOnlyNotificationAdapter, OutboxEntryNotFound

    outbox = NotificationOutbox(project_root)
    try:
        entry = outbox.get(entry_id)
    except OutboxEntryNotFound:
        return f"Outbox entry not found: {entry_id}"
    if subcmd == "send":
        adapter = LogOnlyNotificationAdapter(project_root)
        if adapter.send(entry):
            outbox.mark_sent(entry_id)
            return f"Sent: {entry_id}"
        outbox.mark_failed(entry_id)
        return f"Failed to send: {entry_id}"
    if subcmd == "dismiss":
        outbox.dismiss(entry_id)
        return f"Dismissed: {entry_id}"
    return f"Unknown :inbox notify subcommand: {subcmd}"


def _handle_interactive_watch_command(project_root: Path | None) -> None:
    import time

    from nuself.notification import NotificationOutbox
    from nuself.tui.render import render_outbox_summary

    outbox = NotificationOutbox(project_root)
    seen: set[str] = set()
    for entry in outbox.list():
        seen.add(entry.id)

    print("Watching outbox. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(2)
            for entry in outbox.list():
                if entry.id not in seen:
                    seen.add(entry.id)
                    _print_ansi(render_outbox_summary(entry))
    except KeyboardInterrupt:
        print("\nStopped watching.")


def _handle_interactive_threads_command(project_root: Path | None) -> str:
    store = ThreadStore(project_root)
    ids = store.list()
    if not ids:
        return "No active threads."
    return "Active threads:\n" + "\n".join(f"  {tid}" for tid in ids)





if __name__ == "__main__":
    raise SystemExit(main())
