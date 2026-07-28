"""Top-level interactive command routing."""

from __future__ import annotations

from pathlib import Path

from nuself.agent.chat import ThreadState, ThreadStore
from nuself.cli.commands.daemon import format_status
from nuself.cli.commands.memory.entries import format_memory_preview
from nuself.cli.commands.output import print_ansi
from nuself.cli.repl.commands import (
    handle_interactive_history_command,
    handle_interactive_inbox_command,
    handle_interactive_memory_command,
    handle_interactive_notify_command,
    handle_interactive_notify_list_command,
    handle_interactive_notify_show_command,
    handle_interactive_notify_subcommand,
    handle_interactive_persona_command,
    handle_interactive_reason_command,
    handle_interactive_reason_watch,
    handle_interactive_reflection_command,
    handle_interactive_reflection_list_command,
    handle_interactive_reflection_show_command,
    handle_interactive_reflection_subcommand,
    handle_interactive_restart_command,
    handle_interactive_threads_command,
    handle_interactive_trace_command,
    handle_interactive_watch_command,
    handle_interactive_whoami_command,
)
from nuself.cli.repl.input import interactive_help
from nuself.cli.repl.registry import command_body, command_matches
from nuself.cli.repl.session import InteractiveSession
from nuself.cli.repl.transcript import (
    auto_save_interactive_transcripts,
    handle_interactive_export_command,
)
from nuself.daemon import lifecycle
from nuself.logs import read_log_events
from nuself.tui.render import render_log_event

InteractiveCommandResult = tuple[str, str]


def handle_interactive_command(
    command: str,
    project_root: Path | None,
    current_thread_id: str,
    session: InteractiveSession,
) -> InteractiveCommandResult:
    """Route one normalized REPL command and return its session action."""

    if command_matches(command, "q"):
        auto_save_interactive_transcripts(project_root, session)
        return ("exit", current_thread_id)
    if command_matches(command, "history"):
        print()
        print_ansi(
            handle_interactive_history_command(project_root, current_thread_id)
        )
        return ("", current_thread_id)
    if command_matches(command, "whoami"):
        print()
        print_ansi(handle_interactive_whoami_command(project_root))
        return ("", current_thread_id)
    inbox_body = command_body(command, "inbox")
    if inbox_body is not None:
        _handle_inbox_command(inbox_body, command, project_root)
        return ("", current_thread_id)
    if command_matches(command, "help"):
        print()
        print(interactive_help())
        return ("", current_thread_id)
    dev_body = command_body(command, "dev")
    if dev_body is not None:
        _handle_dev_command(dev_body, project_root)
        return ("", current_thread_id)
    if command_body(command, "export") is not None:
        print()
        print_ansi(
            handle_interactive_export_command(
                command,
                project_root,
                current_thread_id,
                session,
            )
        )
        return ("", current_thread_id)
    memory_body = command_body(command, "mem")
    if memory_body is not None:
        print()
        if memory_body == "":
            print_ansi(format_memory_preview(project_root))
        else:
            print_ansi(handle_interactive_memory_command(memory_body, project_root))
        return ("", current_thread_id)
    thread_body = command_body(command, "thread")
    if thread_body is not None:
        return _handle_thread_switch(thread_body, project_root, current_thread_id)
    reason_body = command_body(command, "reason")
    if reason_body is not None:
        print()
        if reason_body == "watch" or reason_body.startswith("watch "):
            body = reason_body.removeprefix("watch").strip()
            handle_interactive_reason_watch(
                project_root,
                thread_ref=body or None,
            )
        else:
            print_ansi(handle_interactive_reason_command(reason_body, project_root))
        return ("", current_thread_id)
    trace_body = command_body(command, "trace")
    if trace_body is not None:
        print()
        print_ansi(handle_interactive_trace_command(trace_body, project_root))
        return ("", current_thread_id)
    persona_body = command_body(command, "persona")
    if persona_body is not None:
        print()
        print_ansi(
            handle_interactive_persona_command(
                persona_body or "list",
                project_root,
            )
        )
        return ("", current_thread_id)
    if command_matches(command, "restart"):
        print()
        print_ansi(handle_interactive_restart_command(project_root))
        return ("redraw_header", current_thread_id)
    rename_body = command_body(command, "rename")
    if rename_body is not None:
        return _handle_thread_rename(
            rename_body,
            project_root,
            current_thread_id,
        )
    branch_body = command_body(command, "branch")
    if branch_body is not None:
        return _handle_thread_branch(
            branch_body,
            project_root,
            current_thread_id,
        )
    if command_matches(command, "archive"):
        return _handle_thread_archive(project_root, current_thread_id)
    unarchive_body = command_body(command, "unarchive")
    if unarchive_body is not None:
        return _handle_thread_unarchive(
            unarchive_body,
            project_root,
            current_thread_id,
        )
    if command_matches(command, "archived"):
        _print_archived_threads(project_root)
        return ("", current_thread_id)
    if command_matches(command, "delete"):
        return _handle_thread_delete(project_root, current_thread_id)
    print()
    print(interactive_help(command))
    return ("", current_thread_id)


def _handle_inbox_command(
    body: str,
    original_command: str,
    project_root: Path | None,
) -> None:
    print()
    if body == "":
        print_ansi(handle_interactive_inbox_command(project_root))
    elif body == "reflection":
        print_ansi(handle_interactive_reflection_command(project_root))
    elif body.startswith("reflection "):
        parts = body.removeprefix("reflection ").split(maxsplit=1)
        if parts[0] == "list":
            print_ansi(handle_interactive_reflection_list_command(project_root))
        elif parts[0] == "show" and len(parts) == 2:
            print_ansi(
                handle_interactive_reflection_show_command(
                    project_root,
                    parts[1],
                )
            )
        elif len(parts) == 2:
            print_ansi(
                handle_interactive_reflection_subcommand(
                    project_root,
                    parts[0],
                    parts[1],
                )
            )
        else:
            print(interactive_help(":inbox reflection"))
    elif body == "notify":
        print_ansi(handle_interactive_notify_command(project_root))
    elif body.startswith("notify "):
        parts = body.removeprefix("notify ").split(maxsplit=1)
        if parts[0] == "list":
            print_ansi(handle_interactive_notify_list_command(project_root))
        elif parts[0] == "show" and len(parts) == 2:
            print_ansi(
                handle_interactive_notify_show_command(
                    project_root,
                    parts[1],
                )
            )
        elif parts[0] == "watch":
            handle_interactive_watch_command(project_root)
        elif len(parts) == 2:
            print_ansi(
                handle_interactive_notify_subcommand(
                    project_root,
                    parts[0],
                    parts[1],
                )
            )
        else:
            print(interactive_help(":inbox notify"))
    else:
        print(interactive_help(original_command))


def _handle_dev_command(body: str, project_root: Path | None) -> None:
    print()
    if body == "status":
        print(format_status(lifecycle.status(project_root)))
    elif body == "logs":
        events = read_log_events(project_root=project_root, tail=8)
        if not events:
            print("No recent activity logs.")
        else:
            for event in events:
                print_ansi(render_log_event(event))
    else:
        print(interactive_help(":dev"))


def _handle_thread_switch(
    thread_id: str,
    project_root: Path | None,
    current_thread_id: str,
) -> InteractiveCommandResult:
    print()
    if thread_id == "":
        print_ansi(handle_interactive_threads_command(project_root))
        return ("", current_thread_id)
    store = ThreadStore(project_root)
    if thread_id not in store.list():
        store.save(ThreadState.empty(thread_id))
    print(f"Switched to thread: {thread_id}")
    return ("redraw_header", thread_id)


def _handle_thread_rename(
    new_id: str,
    project_root: Path | None,
    current_thread_id: str,
) -> InteractiveCommandResult:
    print()
    if new_id == "":
        print(interactive_help(":rename"))
    else:
        try:
            ThreadStore(project_root).rename(current_thread_id, new_id)
            print(f"Renamed thread to: {new_id}")
        except ValueError as exc:
            print(f"Error: {exc}")
    return ("redraw_header", new_id or current_thread_id)


def _handle_thread_branch(
    body: str,
    project_root: Path | None,
    current_thread_id: str,
) -> InteractiveCommandResult:
    print()
    parts = body.split()
    new_id = parts[0] if parts else ""
    index: int | None = None
    if len(parts) >= 2:
        try:
            index = int(parts[1])
        except ValueError:
            print(f"Invalid index: {parts[1]}")
            return ("", current_thread_id)
    if new_id == "":
        print(interactive_help(":branch"))
    else:
        try:
            ThreadStore(project_root).branch(current_thread_id, new_id, index)
            print(f"Branched to thread: {new_id}")
        except ValueError as exc:
            print(f"Error: {exc}")
    return ("redraw_header", new_id or current_thread_id)


def _handle_thread_archive(
    project_root: Path | None,
    current_thread_id: str,
) -> InteractiveCommandResult:
    print()
    try:
        ThreadStore(project_root).archive(current_thread_id)
        print(f"Archived thread: {current_thread_id}")
    except ValueError as exc:
        print(f"Error: {exc}")
    return ("redraw_header", "default")


def _handle_thread_unarchive(
    thread_id: str,
    project_root: Path | None,
    current_thread_id: str,
) -> InteractiveCommandResult:
    print()
    if thread_id == "":
        print(interactive_help(":unarchive"))
    else:
        try:
            ThreadStore(project_root).unarchive(thread_id)
            print(f"Unarchived thread: {thread_id}")
        except ValueError as exc:
            print(f"Error: {exc}")
    return ("", current_thread_id)


def _print_archived_threads(project_root: Path | None) -> None:
    print()
    ids = ThreadStore(project_root).list_archived()
    if not ids:
        print("No archived threads.")
    else:
        for thread_id in ids:
            print(thread_id)


def _handle_thread_delete(
    project_root: Path | None,
    current_thread_id: str,
) -> InteractiveCommandResult:
    print()
    try:
        ThreadStore(project_root).delete(current_thread_id)
        print(f"Deleted thread: {current_thread_id}")
    except ValueError as exc:
        print(f"Error: {exc}")
    return ("redraw_header", "default")
