"""Top-level CLI parser construction."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from nuself import __version__
from nuself.cli.commands.daemon import (
    handle_daemon_health,
    handle_daemon_list,
    handle_daemon_restart,
    handle_daemon_start,
    handle_daemon_status,
    handle_daemon_stop,
)
from nuself.cli.commands.dev import (
    handle_dev_db_schema,
    handle_dev_migrate,
    handle_dev_storage,
)
from nuself.cli.commands.eval import handle_eval
from nuself.cli.commands.memory.parser import add_memory_parser
from nuself.cli.commands.notifications import (
    handle_notify_clear,
    handle_notify_dismiss,
    handle_notify_list,
    handle_notify_send,
    handle_notify_show,
    handle_notify_stats,
    handle_notify_watch,
)
from nuself.cli.commands.pack import (
    handle_pack_export,
    handle_pack_import,
    handle_pack_inspect,
    handle_pack_list,
)
from nuself.cli.commands.persona import (
    handle_persona_create,
    handle_persona_delete,
    handle_persona_disable,
    handle_persona_enable,
    handle_persona_list,
    handle_persona_show,
)
from nuself.cli.commands.reason import (
    REASON_VERBS,
    handle_reason_delete,
    handle_reason_list,
    handle_reason_show,
    handle_reason_start,
    handle_reason_thread_action,
)
from nuself.cli.commands.reflections import (
    handle_reflection_archive,
    handle_reflection_dismiss,
    handle_reflection_list,
    handle_reflection_organize,
    handle_reflection_promote,
    handle_reflection_show,
)
from nuself.cli.commands.system import (
    handle_config,
    handle_health,
    handle_logs,
    handle_status,
)
from nuself.cli.commands.threads import (
    handle_thread_archive,
    handle_thread_archived,
    handle_thread_branch,
    handle_thread_create,
    handle_thread_delete,
    handle_thread_list,
    handle_thread_rename,
    handle_thread_show,
    handle_thread_unarchive,
)
from nuself.cli.commands.trace import (
    handle_trace_list,
    handle_trace_reindex,
    handle_trace_related,
    handle_trace_search,
    handle_trace_show,
)
from nuself.cli.handlers import CliHandler, CliHandlerBindings
from nuself.cli.repl.commands import handle_reason_watch
from nuself.logs import LOG_COMPONENTS
from nuself.trace.domain import TRACE_KINDS


@dataclass(frozen=True)
class EntrypointHandlers:
    default_entrypoint: CliHandler
    chat: CliHandler
    attach: CliHandler
    open_thread: CliHandler


def _add_log_arguments(
    parser: argparse.ArgumentParser,
    bindings: CliHandlerBindings,
) -> None:
    parser.add_argument("--component", choices=list(LOG_COMPONENTS), default=None)
    parser.add_argument("--tail", type=int, default=50)
    parser.add_argument("--follow", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-color", action="store_true")
    bindings.bind(parser, handle_logs)


def build_parser(handlers: EntrypointHandlers) -> argparse.ArgumentParser:
    bindings = CliHandlerBindings()
    bind_handler = bindings.bind
    bind_help = bindings.bind_help
    parser = argparse.ArgumentParser(prog="nuself")
    parser.add_argument("--version", action="version", version=f"nuself {__version__}")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--message", "-m", default=None)
    bind_handler(parser, handlers.default_entrypoint)
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    daemon_parser = subparsers.add_parser(
        "daemon",
        help="Manage the NuSelf background daemon.",
        description="Manage the NuSelf background daemon.",
    )
    bind_help(daemon_parser)
    daemon_subparsers = daemon_parser.add_subparsers(
        dest="daemon_command", metavar="<command>"
    )
    bind_handler(
        daemon_subparsers.add_parser("start", help="Start the background daemon."),
        handle_daemon_start,
    )
    bind_handler(
        daemon_subparsers.add_parser("stop", help="Stop the background daemon."),
        handle_daemon_stop,
    )
    bind_handler(
        daemon_subparsers.add_parser("restart", help="Restart the background daemon."),
        handle_daemon_restart,
    )
    bind_handler(
        daemon_subparsers.add_parser("status", help="Show daemon status."),
        handle_daemon_status,
    )
    bind_handler(
        daemon_subparsers.add_parser("health", help="Show background worker health."),
        handle_daemon_health,
    )
    bind_handler(
        daemon_subparsers.add_parser("list", help="List daemon status in table form."),
        handle_daemon_list,
    )
    daemon_logs_parser = daemon_subparsers.add_parser("logs", help="Show daemon logs.")
    _add_log_arguments(daemon_logs_parser, bindings)
    daemon_attach_parser = daemon_subparsers.add_parser(
        "attach", help="Attach chat to the running daemon."
    )
    daemon_attach_parser.add_argument("--message", "-m", default=None)
    bind_handler(daemon_attach_parser, handlers.attach)

    chat_parser = subparsers.add_parser(
        "chat",
        help="Start chat, using the daemon when available.",
        description="Start chat, using the daemon when available.",
    )
    chat_parser.add_argument("--message", "-m", default=None)
    chat_parser.add_argument("--require-daemon", action="store_true")
    bind_handler(chat_parser, handlers.chat)

    attach_parser = subparsers.add_parser(
        "attach",
        help="Attach to a running daemon chat session.",
        description="Attach to a running daemon chat session.",
    )
    attach_parser.add_argument("--message", "-m", default=None)
    bind_handler(attach_parser, handlers.attach)

    add_memory_parser(subparsers, bindings)

    thread_parser = subparsers.add_parser(
        "thread",
        help="Manage conversation threads.",
        description="Manage conversation threads.",
    )
    bind_help(thread_parser)
    thread_subparsers = thread_parser.add_subparsers(
        dest="thread_command", metavar="<command>"
    )
    bind_handler(
        thread_subparsers.add_parser("list", help="List conversation threads."),
        handle_thread_list,
    )
    thread_show_parser = thread_subparsers.add_parser(
        "show", help="Show one conversation thread."
    )
    thread_show_parser.add_argument("thread_id")
    bind_handler(thread_show_parser, handle_thread_show)
    thread_create_parser = thread_subparsers.add_parser(
        "new", help="Create an empty conversation thread."
    )
    thread_create_parser.add_argument("thread_id")
    bind_handler(thread_create_parser, handle_thread_create)
    thread_open_parser = thread_subparsers.add_parser(
        "open", help="Open or create a thread for chat."
    )
    thread_open_parser.add_argument("thread_id", nargs="?", default=None)
    thread_open_parser.add_argument("--message", "-m", default=None)
    thread_open_parser.add_argument("--create", action="store_true")
    thread_open_parser.add_argument("--deep-link", default=None)
    bind_handler(thread_open_parser, handlers.open_thread)
    thread_rename_parser = thread_subparsers.add_parser(
        "rename", help="Rename a conversation thread."
    )
    thread_rename_parser.add_argument("old_thread_id")
    thread_rename_parser.add_argument("new_thread_id")
    bind_handler(thread_rename_parser, handle_thread_rename)
    thread_branch_parser = thread_subparsers.add_parser(
        "branch", help="Create a thread branch from an existing thread."
    )
    thread_branch_parser.add_argument("source_thread_id")
    thread_branch_parser.add_argument("new_thread_id")
    thread_branch_parser.add_argument("--index", type=int, default=None)
    bind_handler(thread_branch_parser, handle_thread_branch)
    thread_archive_parser = thread_subparsers.add_parser(
        "archive", help="Archive a conversation thread."
    )
    thread_archive_parser.add_argument("thread_id")
    bind_handler(thread_archive_parser, handle_thread_archive)
    thread_delete_parser = thread_subparsers.add_parser(
        "delete", help="Delete a conversation thread."
    )
    thread_delete_parser.add_argument("thread_id")
    bind_handler(thread_delete_parser, handle_thread_delete)
    thread_unarchive_parser = thread_subparsers.add_parser(
        "unarchive", help="Restore an archived conversation thread."
    )
    thread_unarchive_parser.add_argument("thread_id")
    bind_handler(thread_unarchive_parser, handle_thread_unarchive)
    bind_handler(
        thread_subparsers.add_parser(
            "archived", help="List archived conversation threads."
        ),
        handle_thread_archived,
    )

    inbox_parser = subparsers.add_parser(
        "inbox",
        help="Manage proactive reflection and notification items.",
        description="Manage proactive reflection and notification items.",
    )
    bind_help(inbox_parser)
    inbox_subparsers = inbox_parser.add_subparsers(
        dest="inbox_command", metavar="<command>"
    )
    reflection_parser = inbox_subparsers.add_parser(
        "reflection",
        help="Review reflection candidates.",
        description="Review reflection candidates.",
    )
    bind_help(reflection_parser)
    reflection_subparsers = reflection_parser.add_subparsers(
        dest="reflection_command", metavar="<command>"
    )
    reflection_list_parser = reflection_subparsers.add_parser(
        "list", help="List reflection entries."
    )
    reflection_list_parser.add_argument("--tail", type=int, default=20)
    reflection_list_parser.add_argument(
        "--status", choices=["pending", "dismissed", "archived"], default=None
    )
    reflection_list_parser.add_argument(
        "--json", action="store_true", default=False, dest="as_json"
    )
    bind_handler(reflection_list_parser, handle_reflection_list)
    reflection_show_parser = reflection_subparsers.add_parser(
        "show", help="Show one reflection entry."
    )
    reflection_show_parser.add_argument("entry_id")
    reflection_show_parser.add_argument(
        "--json", action="store_true", default=False, dest="as_json"
    )
    bind_handler(reflection_show_parser, handle_reflection_show)
    reflection_dismiss_parser = reflection_subparsers.add_parser(
        "dismiss", help="Dismiss one reflection entry."
    )
    reflection_dismiss_parser.add_argument("entry_id")
    bind_handler(reflection_dismiss_parser, handle_reflection_dismiss)
    reflection_archive_parser = reflection_subparsers.add_parser(
        "archive", help="Archive one reflection entry."
    )
    reflection_archive_parser.add_argument("entry_id")
    bind_handler(reflection_archive_parser, handle_reflection_archive)
    reflection_promote_parser = reflection_subparsers.add_parser(
        "promote", help="Promote one reflection into a reason thread."
    )
    reflection_promote_parser.add_argument("entry_id")
    bind_handler(reflection_promote_parser, handle_reflection_promote)
    bind_handler(
        reflection_subparsers.add_parser(
            "organize", help="Merge similar pending reflection entries."
        ),
        handle_reflection_organize,
    )

    notify_parser = inbox_subparsers.add_parser(
        "notify",
        help="Manage notification outbox entries.",
        description="Manage notification outbox entries.",
    )
    bind_help(notify_parser)
    notify_subparsers = notify_parser.add_subparsers(
        dest="notify_command", metavar="<command>"
    )
    notify_list_parser = notify_subparsers.add_parser(
        "list", help="List notification entries."
    )
    notify_list_parser.add_argument(
        "--status", choices=["pending", "sent", "failed", "dismissed"], default=None
    )
    bind_handler(notify_list_parser, handle_notify_list)
    notify_show_parser = notify_subparsers.add_parser(
        "show", help="Show one notification entry."
    )
    notify_show_parser.add_argument("entry_id")
    bind_handler(notify_show_parser, handle_notify_show)
    notify_send_parser = notify_subparsers.add_parser(
        "send", help="Send one pending notification now."
    )
    notify_send_parser.add_argument("entry_id")
    bind_handler(notify_send_parser, handle_notify_send)
    notify_dismiss_parser = notify_subparsers.add_parser(
        "dismiss", help="Dismiss one notification entry."
    )
    notify_dismiss_parser.add_argument("entry_id")
    bind_handler(notify_dismiss_parser, handle_notify_dismiss)
    bind_handler(
        notify_subparsers.add_parser(
            "stats", help="Show notification outbox statistics."
        ),
        handle_notify_stats,
    )
    notify_watch_parser = notify_subparsers.add_parser(
        "watch", help="Watch for pending notifications."
    )
    notify_watch_parser.add_argument(
        "--interval", type=int, default=5, help="Poll interval in seconds"
    )
    bind_handler(notify_watch_parser, handle_notify_watch)
    bind_handler(
        notify_subparsers.add_parser(
            "clear", help="Clear sent, failed, and dismissed notifications."
        ),
        handle_notify_clear,
    )

    reason_parser = subparsers.add_parser(
        "reason",
        help="Manage long-run reasoning threads.",
        description="Manage long-run reasoning threads.",
    )
    bind_help(reason_parser)
    reason_subparsers = reason_parser.add_subparsers(
        dest="reason_command", metavar="<command>"
    )
    reason_list_parser = reason_subparsers.add_parser(
        "list", help="List reasoning threads."
    )
    reason_list_parser.add_argument(
        "--status",
        choices=("active", "paused", "resolved", "archived", "all"),
        default="all",
    )
    reason_list_parser.add_argument(
        "--json", action="store_true", default=False, dest="as_json"
    )
    bind_handler(reason_list_parser, handle_reason_list)
    reason_show_parser = reason_subparsers.add_parser(
        "show", help="Show a reasoning thread and its steps."
    )
    reason_show_parser.add_argument("thread_id")
    reason_show_parser.add_argument("--full", "-f", action="store_true", default=False)
    reason_show_parser.add_argument(
        "--json", action="store_true", default=False, dest="as_json"
    )
    bind_handler(reason_show_parser, handle_reason_show)
    reason_start_parser = reason_subparsers.add_parser(
        "start", help="Start a new reasoning thread."
    )
    reason_start_parser.add_argument("topic")
    reason_start_parser.add_argument(
        "--priority", choices=("normal", "high"), default="normal"
    )
    reason_start_parser.add_argument(
        "--mandate",
        action="append",
        default=[],
        help="Required action the advancer must follow on every advance (repeatable)",
    )
    bind_handler(reason_start_parser, handle_reason_start)
    for action_name in REASON_VERBS:
        p = reason_subparsers.add_parser(
            action_name, help=f"{action_name.title()} one reasoning thread."
        )
        p.add_argument("thread_id")
        p.set_defaults(action=action_name)
        bind_handler(p, handle_reason_thread_action)
    reason_delete_parser = reason_subparsers.add_parser(
        "delete", help="Delete one reasoning thread."
    )
    reason_delete_parser.add_argument("thread_id")
    reason_delete_parser.add_argument("--yes", "-y", action="store_true", default=False)
    bind_handler(reason_delete_parser, handle_reason_delete)
    reason_watch_parser = reason_subparsers.add_parser(
        "watch", help="Watch reasoning threads for new steps."
    )
    reason_watch_parser.add_argument(
        "thread_id",
        nargs="?",
        default=None,
        help="Thread id or index to watch (default: all threads)",
    )
    reason_watch_parser.add_argument(
        "--interval", type=int, default=5, help="Poll interval in seconds"
    )
    bind_handler(reason_watch_parser, handle_reason_watch)
    trace_parser = subparsers.add_parser(
        "trace",
        help="Inspect thought provenance records.",
        description="Inspect thought provenance records.",
    )
    bind_help(trace_parser)
    trace_subparsers = trace_parser.add_subparsers(
        dest="trace_command", metavar="<command>"
    )
    trace_list_parser = trace_subparsers.add_parser("list", help="List thought traces.")
    trace_list_parser.add_argument("--kind", choices=TRACE_KINDS, default=None)
    trace_list_parser.add_argument(
        "--visibility",
        choices=("private", "shareable", "internal", "all"),
        default=None,
    )
    trace_list_parser.add_argument(
        "--json", action="store_true", default=False, dest="as_json"
    )
    bind_handler(trace_list_parser, handle_trace_list)
    trace_show_parser = trace_subparsers.add_parser(
        "show", help="Show one thought trace."
    )
    trace_show_parser.add_argument("trace_id")
    trace_show_parser.add_argument(
        "--json", action="store_true", default=False, dest="as_json"
    )
    bind_handler(trace_show_parser, handle_trace_show)
    trace_search_parser = trace_subparsers.add_parser(
        "search", help="Search thought traces."
    )
    trace_search_parser.add_argument("query")
    trace_search_parser.add_argument("--kind", choices=TRACE_KINDS, default=None)
    trace_search_parser.add_argument(
        "--visibility",
        choices=("private", "shareable", "internal", "all"),
        default=None,
    )
    trace_search_parser.add_argument(
        "--json", action="store_true", default=False, dest="as_json"
    )
    bind_handler(trace_search_parser, handle_trace_search)
    trace_related_parser = trace_subparsers.add_parser(
        "related", help="List traces related to an artifact reference."
    )
    trace_related_parser.add_argument("artifact_ref")
    trace_related_parser.add_argument(
        "--visibility",
        choices=("private", "shareable", "internal", "all"),
        default=None,
    )
    trace_related_parser.add_argument(
        "--json", action="store_true", default=False, dest="as_json"
    )
    bind_handler(trace_related_parser, handle_trace_related)
    bind_handler(
        trace_subparsers.add_parser("reindex", help="Rebuild thought trace indexes."),
        handle_trace_reindex,
    )

    persona_parser = subparsers.add_parser(
        "persona",
        help="Manage synthesized persona snapshots.",
        description="Manage synthesized persona snapshots.",
    )
    bind_help(persona_parser)
    persona_subparsers = persona_parser.add_subparsers(
        dest="persona_command", metavar="<command>"
    )
    bind_handler(
        persona_subparsers.add_parser(
            "list", help="List synthesized persona snapshots."
        ),
        handle_persona_list,
    )
    persona_create_parser = persona_subparsers.add_parser(
        "create", help="Create a persona snapshot."
    )
    persona_create_parser.add_argument("name")
    persona_create_parser.add_argument("prompt")
    bind_handler(persona_create_parser, handle_persona_create)
    persona_show_parser = persona_subparsers.add_parser(
        "show", help="Show one persona snapshot."
    )
    persona_show_parser.add_argument("persona_id")
    bind_handler(persona_show_parser, handle_persona_show)
    persona_delete_parser = persona_subparsers.add_parser(
        "delete", help="Delete one persona snapshot."
    )
    persona_delete_parser.add_argument("persona_id")
    persona_delete_parser.add_argument(
        "--yes", "-y", action="store_true", default=False
    )
    bind_handler(persona_delete_parser, handle_persona_delete)
    persona_disable_parser = persona_subparsers.add_parser(
        "disable", help="Disable a persona snapshot."
    )
    persona_disable_parser.add_argument("persona_id")
    persona_disable_parser.add_argument(
        "--yes", "-y", action="store_true", default=False
    )
    bind_handler(persona_disable_parser, handle_persona_disable)
    persona_enable_parser = persona_subparsers.add_parser(
        "enable", help="Enable a persona snapshot."
    )
    persona_enable_parser.add_argument("persona_id")
    persona_enable_parser.add_argument(
        "--yes", "-y", action="store_true", default=False
    )
    bind_handler(persona_enable_parser, handle_persona_enable)

    dev_parser = subparsers.add_parser(
        "dev",
        help="Run diagnostics, logs, config inspection, and evals.",
        description="Run diagnostics, logs, config inspection, and evals.",
    )
    bind_help(dev_parser)
    dev_subparsers = dev_parser.add_subparsers(dest="dev_command", metavar="<command>")
    bind_handler(
        dev_subparsers.add_parser("status", help="Show runtime status summary."),
        handle_status,
    )
    bind_handler(
        dev_subparsers.add_parser("health", help="Run local health checks."),
        handle_health,
    )
    bind_handler(
        dev_subparsers.add_parser("config", help="Show effective configuration."),
        handle_config,
    )
    dev_logs_parser = dev_subparsers.add_parser("logs", help="Show structured logs.")
    _add_log_arguments(dev_logs_parser, bindings)
    dev_eval_parser = dev_subparsers.add_parser("eval", help="Run evaluation fixtures.")
    dev_eval_parser.add_argument("--fixtures", type=Path, default=None)
    dev_eval_parser.add_argument(
        "--component", choices=["conversations", "notifications", "all"], default="all"
    )
    bind_handler(dev_eval_parser, handle_eval)

    dev_migrate_parser = dev_subparsers.add_parser(
        "migrate", help="Migrate file-based data to private/nuself.sqlite."
    )
    bind_handler(dev_migrate_parser, handle_dev_migrate)

    bind_handler(
        dev_subparsers.add_parser("db-schema", help="Show SQLite database schema."),
        handle_dev_db_schema,
    )
    bind_handler(
        dev_subparsers.add_parser(
            "storage", help="Show which storage backend is active."
        ),
        handle_dev_storage,
    )

    pack_parser = subparsers.add_parser(
        "pack",
        help="Export, import, and inspect thought packs.",
        description="Export, import, and inspect thought packs (nuself.sqlite snapshots).",
    )
    bind_help(pack_parser)
    pack_subparsers = pack_parser.add_subparsers(
        dest="pack_command", metavar="<command>"
    )
    pack_export_parser = pack_subparsers.add_parser(
        "export", help="Export current thought pack to private/exports/."
    )
    pack_export_parser.add_argument(
        "name", type=str, help="Pack name (used as filename)"
    )
    bind_handler(pack_export_parser, handle_pack_export)
    pack_import_parser = pack_subparsers.add_parser(
        "import", help="Import a thought pack from a .sqlite file."
    )
    pack_import_parser.add_argument(
        "path", type=Path, help="Path to .sqlite file to import"
    )
    bind_handler(pack_import_parser, handle_pack_import)
    bind_handler(
        pack_subparsers.add_parser(
            "list", help="List imported and exported thought packs."
        ),
        handle_pack_list,
    )
    pack_inspect_parser = pack_subparsers.add_parser(
        "inspect", help="Show summary of a thought pack."
    )
    pack_inspect_parser.add_argument(
        "name",
        type=str,
        nargs="?",
        default=None,
        help="Pack name (resolves to imports/, then exports/, then literal path; default: main database)",
    )
    bind_handler(pack_inspect_parser, handle_pack_inspect)

    bindings.seal(parser)
    return parser
