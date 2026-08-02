"""Top-level interactive command routing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from nuself.conversation import ConversationState
from nuself.cli.application import cli_application
from nuself.cli.daemon_status import format_status, observe_daemon_status
from nuself.cli.memory_preview import format_memory_preview
from nuself.cli.output import print_ansi
from nuself.cli.repl.commands import (
    handle_interactive_history_command,
    handle_interactive_inbox_command,
    handle_interactive_memory_command,
    handle_interactive_notify_command,
    handle_interactive_notify_show_command,
    handle_interactive_notify_subcommand,
    handle_interactive_persona_command,
    handle_interactive_reason_command,
    handle_interactive_reflection_command,
    handle_interactive_reflection_show_command,
    handle_interactive_reflection_subcommand,
    handle_interactive_restart_command,
    handle_interactive_conversations_command,
    handle_interactive_trace_command,
    handle_interactive_watch_command,
    handle_interactive_whoami_command,
)
from nuself.cli.repl.input import interactive_help
from nuself.cli.reason_watch import watch_reason_steps
from nuself.cli.repl.registry import (
    command_names,
    resolve_command,
)
from nuself.cli.repl.session import InteractiveSession
from nuself.cli.repl.transcript import (
    auto_save_interactive_transcripts,
    handle_interactive_export_command,
)
from nuself.logs import read_log_events
from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.runtime.handlers import HandlerRegistry
from nuself.tui.render import render_log_event

type InteractiveCommandResult = tuple[str, str]
type ReplCommandHandler = Callable[
    [str, "ReplCommandContext"],
    InteractiveCommandResult,
]
type ReplCommandRegistry = HandlerRegistry[
    str,
    [str, "ReplCommandContext"],
    InteractiveCommandResult,
]


@dataclass(frozen=True)
class ReplCommandContext:
    command: str
    project_root: Path | None
    current_conversation_id: str
    session: InteractiveSession


class ReplCommandDispatcher:
    """Resolve and dispatch REPL commands through one sealed registry."""

    def __init__(self) -> None:
        self._registry = _build_repl_command_registry()

    def handle(
        self,
        command: str,
        project_root: Path | None,
        current_conversation_id: str,
        session: InteractiveSession,
    ) -> InteractiveCommandResult:
        resolved = resolve_command(command)
        context = ReplCommandContext(
            command=command,
            project_root=project_root,
            current_conversation_id=current_conversation_id,
            session=session,
        )
        if resolved is None:
            return _unknown_command(context)
        return self._registry.dispatch(
            resolved.name,
            resolved.body,
            context,
        )


def _build_repl_command_registry() -> ReplCommandRegistry:
    registry: ReplCommandRegistry = HandlerRegistry()
    handlers: tuple[tuple[str, ReplCommandHandler], ...] = (
        ("q", _handle_quit),
        ("history", _handle_history),
        ("whoami", _handle_whoami),
        ("inbox", _handle_inbox),
        ("help", _handle_help),
        ("retry", _handle_retry),
        ("dev", _handle_dev),
        ("export", _handle_export),
        ("mem", _handle_memory),
        ("conversation", _handle_conversation),
        ("reason", _handle_reason),
        ("trace", _handle_trace),
        ("persona", _handle_persona),
        ("restart", _handle_restart),
        ("rename", _handle_rename),
        ("branch", _handle_branch),
        ("archive", _handle_archive),
        ("unarchive", _handle_unarchive),
        ("archived", _handle_archived),
        ("delete", _handle_delete),
    )
    for name, handler in handlers:
        registry.register(name, handler)
    return registry.seal(expected_keys=command_names())


def _unknown_command(
    context: ReplCommandContext,
) -> InteractiveCommandResult:
    print()
    print(interactive_help(context.command))
    return ("", context.current_conversation_id)


def _reject_nonempty_body(
    body: str,
    context: ReplCommandContext,
) -> InteractiveCommandResult | None:
    if body == "":
        return None
    return _unknown_command(context)


def _handle_quit(
    body: str,
    context: ReplCommandContext,
) -> InteractiveCommandResult:
    rejected = _reject_nonempty_body(body, context)
    if rejected is not None:
        return rejected
    auto_save_interactive_transcripts(
        context.project_root,
        context.session,
    )
    return ("exit", context.current_conversation_id)


def _handle_retry(
    body: str,
    context: ReplCommandContext,
) -> InteractiveCommandResult:
    rejected = _reject_nonempty_body(body, context)
    if rejected is not None:
        return rejected
    if context.session.retry_offer is None:
        print()
        print("No retryable chat turn is available.")
        return ("", context.current_conversation_id)
    context.session.retry_requested = True
    return ("retry", context.current_conversation_id)


def _handle_history(
    body: str,
    context: ReplCommandContext,
) -> InteractiveCommandResult:
    rejected = _reject_nonempty_body(body, context)
    if rejected is not None:
        return rejected
    print()
    print_ansi(
        handle_interactive_history_command(
            context.project_root,
            context.current_conversation_id,
        )
    )
    return ("", context.current_conversation_id)


def _handle_whoami(
    body: str,
    context: ReplCommandContext,
) -> InteractiveCommandResult:
    rejected = _reject_nonempty_body(body, context)
    if rejected is not None:
        return rejected
    print()
    print_ansi(handle_interactive_whoami_command(context.project_root))
    return ("", context.current_conversation_id)


def _handle_inbox(
    body: str,
    context: ReplCommandContext,
) -> InteractiveCommandResult:
    _handle_inbox_command(
        body,
        context.command,
        context.project_root,
    )
    return ("", context.current_conversation_id)


def _handle_help(
    body: str,
    context: ReplCommandContext,
) -> InteractiveCommandResult:
    rejected = _reject_nonempty_body(body, context)
    if rejected is not None:
        return rejected
    print()
    print(interactive_help())
    return ("", context.current_conversation_id)


def _handle_dev(
    body: str,
    context: ReplCommandContext,
) -> InteractiveCommandResult:
    _handle_dev_command(body, context.project_root)
    return ("", context.current_conversation_id)


def _handle_export(
    body: str,
    context: ReplCommandContext,
) -> InteractiveCommandResult:
    print()
    canonical_command = ":export"
    if body:
        canonical_command = f"{canonical_command} {body}"
    print_ansi(
        handle_interactive_export_command(
            canonical_command,
            context.project_root,
            context.current_conversation_id,
            context.session,
        )
    )
    return ("", context.current_conversation_id)


def _handle_memory(
    body: str,
    context: ReplCommandContext,
) -> InteractiveCommandResult:
    print()
    if body == "":
        print_ansi(format_memory_preview(context.project_root))
    else:
        print_ansi(
            handle_interactive_memory_command(
                body,
                context.project_root,
            )
        )
    return ("", context.current_conversation_id)


def _handle_conversation(
    body: str,
    context: ReplCommandContext,
) -> InteractiveCommandResult:
    return _handle_conversation_switch(
        body,
        context.project_root,
        context.current_conversation_id,
    )


def _handle_reason(
    body: str,
    context: ReplCommandContext,
) -> InteractiveCommandResult:
    print()
    if body == "watch" or body.startswith("watch "):
        thread_ref = body.removeprefix("watch").strip()
        watch_reason_steps(
            context.project_root,
            thread_ref=thread_ref or None,
        )
    else:
        print_ansi(
            handle_interactive_reason_command(
                body,
                context.project_root,
            )
        )
    return ("", context.current_conversation_id)


def _handle_trace(
    body: str,
    context: ReplCommandContext,
) -> InteractiveCommandResult:
    print()
    print_ansi(
        handle_interactive_trace_command(
            body,
            context.project_root,
        )
    )
    return ("", context.current_conversation_id)


def _handle_persona(
    body: str,
    context: ReplCommandContext,
) -> InteractiveCommandResult:
    print()
    print_ansi(
        handle_interactive_persona_command(
            body or "list",
            context.project_root,
        )
    )
    return ("", context.current_conversation_id)


def _handle_restart(
    body: str,
    context: ReplCommandContext,
) -> InteractiveCommandResult:
    rejected = _reject_nonempty_body(body, context)
    if rejected is not None:
        return rejected
    print()
    print_ansi(handle_interactive_restart_command(context.project_root))
    return ("redraw_header", context.current_conversation_id)


def _handle_rename(
    body: str,
    context: ReplCommandContext,
) -> InteractiveCommandResult:
    return _handle_conversation_rename(
        body,
        context.project_root,
        context.current_conversation_id,
    )


def _handle_branch(
    body: str,
    context: ReplCommandContext,
) -> InteractiveCommandResult:
    return _handle_conversation_branch(
        body,
        context.project_root,
        context.current_conversation_id,
    )


def _handle_archive(
    body: str,
    context: ReplCommandContext,
) -> InteractiveCommandResult:
    rejected = _reject_nonempty_body(body, context)
    if rejected is not None:
        return rejected
    return _handle_conversation_archive(
        context.project_root,
        context.current_conversation_id,
    )


def _handle_unarchive(
    body: str,
    context: ReplCommandContext,
) -> InteractiveCommandResult:
    return _handle_conversation_unarchive(
        body,
        context.project_root,
        context.current_conversation_id,
    )


def _handle_archived(
    body: str,
    context: ReplCommandContext,
) -> InteractiveCommandResult:
    rejected = _reject_nonempty_body(body, context)
    if rejected is not None:
        return rejected
    _print_archived_conversations(context.project_root)
    return ("", context.current_conversation_id)


def _handle_delete(
    body: str,
    context: ReplCommandContext,
) -> InteractiveCommandResult:
    rejected = _reject_nonempty_body(body, context)
    if rejected is not None:
        return rejected
    return _handle_conversation_delete(
        context.project_root,
        context.current_conversation_id,
    )


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
            print_ansi(
                handle_interactive_reflection_command(
                    project_root,
                    include_all=True,
                )
            )
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
            print_ansi(
                handle_interactive_notify_command(
                    project_root,
                    include_all=True,
                )
            )
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
        status = observe_daemon_status(project_root)
        if status is not None:
            print(format_status(status))
    elif body == "logs":
        events = read_log_events(project_root=project_root, tail=8)
        if not events:
            print("No recent activity logs.")
        else:
            for event in events:
                print_ansi(render_log_event(event))
    else:
        print(interactive_help(":dev"))


def _handle_conversation_switch(
    conversation_id: str,
    project_root: Path | None,
    current_conversation_id: str,
) -> InteractiveCommandResult:
    print()
    if conversation_id == "":
        print_ansi(handle_interactive_conversations_command(project_root))
        return ("", current_conversation_id)
    store = cli_application().conversations
    if conversation_id not in store.list():
        store.save(ConversationState.empty(conversation_id))
    print(f"Switched to conversation: {conversation_id}")
    return ("redraw_header", conversation_id)


def _handle_conversation_rename(
    new_id: str,
    project_root: Path | None,
    current_conversation_id: str,
) -> InteractiveCommandResult:
    print()
    if new_id == "":
        print(interactive_help(":rename"))
    else:
        try:
            cli_application().conversations.rename(
                current_conversation_id, new_id
            )
            print(f"Renamed conversation to: {new_id}")
        except ValueError as exc:
            print(f"Error: {diagnostic_exception_message(exc)}")
    return ("redraw_header", new_id or current_conversation_id)


def _handle_conversation_branch(
    body: str,
    project_root: Path | None,
    current_conversation_id: str,
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
            return ("", current_conversation_id)
    if new_id == "":
        print(interactive_help(":branch"))
    else:
        try:
            cli_application().conversations.branch(
                current_conversation_id, new_id, index
            )
            print(f"Branched to conversation: {new_id}")
        except ValueError as exc:
            print(f"Error: {diagnostic_exception_message(exc)}")
    return ("redraw_header", new_id or current_conversation_id)


def _handle_conversation_archive(
    project_root: Path | None,
    current_conversation_id: str,
) -> InteractiveCommandResult:
    print()
    try:
        cli_application().conversations.archive(current_conversation_id)
        print(f"Archived conversation: {current_conversation_id}")
    except ValueError as exc:
        print(f"Error: {diagnostic_exception_message(exc)}")
    return ("redraw_header", "default")


def _handle_conversation_unarchive(
    conversation_id: str,
    project_root: Path | None,
    current_conversation_id: str,
) -> InteractiveCommandResult:
    print()
    if conversation_id == "":
        print(interactive_help(":unarchive"))
    else:
        try:
            cli_application().conversations.unarchive(conversation_id)
            print(f"Unarchived conversation: {conversation_id}")
        except ValueError as exc:
            print(f"Error: {diagnostic_exception_message(exc)}")
    return ("", current_conversation_id)


def _print_archived_conversations(project_root: Path | None) -> None:
    print()
    ids = cli_application().conversations.list_archived()
    if not ids:
        print("No archived conversations.")
    else:
        for conversation_id in ids:
            print(conversation_id)


def _handle_conversation_delete(
    project_root: Path | None,
    current_conversation_id: str,
) -> InteractiveCommandResult:
    print()
    try:
        cli_application().conversations.delete(current_conversation_id)
        print(f"Deleted conversation: {current_conversation_id}")
    except ValueError as exc:
        print(f"Error: {diagnostic_exception_message(exc)}")
    return ("redraw_header", "default")
