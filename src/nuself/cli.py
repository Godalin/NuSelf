"""Command-line interface for NuSelf."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path
import sys
import warnings

try:
    import readline
except ImportError:  # pragma: no cover - platform fallback
    readline = None  # type: ignore[assignment]

_original_warn = warnings.warn


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
    from nuself.config import ensure_runtime_dirs, runtime_paths
    from nuself.agent.chat import ChatAgent, ThreadState, ThreadStore
    from nuself.daemon import client, lifecycle
    from nuself.domain.memory import (
        MemoryEntry,
        PrivacyLevel,
        default_memory_type_registry,
        default_relation_descriptor_registry,
    )
    from nuself.domain.source import SourceChunk
    from nuself.memory.curator import MemoryCurator
    from nuself.memory.intake import MemoryIntakeAgent
    from nuself.memory.optimizer import MemoryOptimizer, MemoryOptimizerSettings
    from nuself.memory.repository import (
        MemoryCandidateNotFound,
        MemoryCandidateRepository,
        MemoryEntryNotFound,
        MemoryEntryRepository,
        MemoryRelationFilters,
        MemoryRelationIndexRecord,
        MemoryStats,
        MemorySearchFilters,
        SymbolicGraphEdge,
        SymbolicGraphEdgeFilters,
        SymbolicGraphNode,
        SymbolicGraphNodeFilters,
        memory_stats,
    )
    from nuself.memory.source_repository import SourceChunkMatch, SourceDocumentNotFound, SourceRepository
    from nuself.profile.repository import ProfileItemNotFound, ProfileItemRepository, ProfileSearchFilters
    from nuself.logs import LOG_COMPONENTS, LogComponent, read_log_events, write_log_event
    from nuself.config_system import ConfigSystem
    from nuself.tui.memory import (
        render_candidate_detail,
        render_candidate_row,
        render_memory_entry_detail,
        render_memory_entry_row,
        render_profile_detail,
        render_profile_row,
        render_source_detail,
        render_source_row,
    )
    from nuself.tui.render import render_log_event, render_log_event_json, render_session_header
finally:
    warnings.warn = _original_warn

CHAT_REQUEST_TIMEOUT_SECONDS = 120.0
DEFAULT_MEMORY_PREVIEW_LIMIT = 8


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
    parser = argparse.ArgumentParser(prog="nuself")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--message", "-m", default=None)
    _add_handler(parser, handle_default_entrypoint)
    subparsers = parser.add_subparsers(dest="command")

    daemon_parser = subparsers.add_parser("daemon")
    daemon_parser.set_defaults(handler=None, help_parser=daemon_parser)
    daemon_subparsers = daemon_parser.add_subparsers(dest="daemon_command")
    _add_handler(daemon_subparsers.add_parser("start"), handle_daemon_start)
    _add_handler(daemon_subparsers.add_parser("stop"), handle_daemon_stop)
    _add_handler(daemon_subparsers.add_parser("restart"), handle_daemon_restart)
    _add_handler(daemon_subparsers.add_parser("status"), handle_daemon_status)
    _add_handler(daemon_subparsers.add_parser("list"), handle_daemon_list)
    daemon_logs_parser = daemon_subparsers.add_parser("logs")
    _add_log_arguments(daemon_logs_parser)
    _add_handler(daemon_logs_parser, handle_logs)
    daemon_attach_parser = daemon_subparsers.add_parser("attach")
    daemon_attach_parser.add_argument("--message", "-m", default=None)
    _add_handler(daemon_attach_parser, handle_attach)

    chat_parser = subparsers.add_parser("chat")
    chat_parser.add_argument("--message", "-m", default=None)
    chat_parser.add_argument("--require-daemon", action="store_true")
    _add_handler(chat_parser, handle_chat)

    attach_parser = subparsers.add_parser("attach")
    attach_parser.add_argument("--message", "-m", default=None)
    _add_handler(attach_parser, handle_attach)

    status_parser = subparsers.add_parser("status")
    _add_handler(status_parser, handle_status)

    health_parser = subparsers.add_parser("health")
    _add_handler(health_parser, handle_health)

    config_parser = subparsers.add_parser("config")
    _add_handler(config_parser, handle_config)

    open_parser = subparsers.add_parser("open")
    open_parser.add_argument("thread_id", nargs="?", default=None)
    open_parser.add_argument("--message", "-m", default=None)
    open_parser.add_argument("--create", action="store_true")
    open_parser.add_argument("--deep-link", default=None)
    _add_handler(open_parser, handle_open)

    logs_parser = subparsers.add_parser("logs")
    _add_log_arguments(logs_parser)

    eval_parser = subparsers.add_parser("eval")
    eval_parser.add_argument("--fixtures", type=Path, default=None)
    eval_parser.add_argument("--component", choices=["conversations", "notifications", "all"], default="all")
    _add_handler(eval_parser, handle_eval)

    notify_parser = subparsers.add_parser("notify")
    notify_parser.set_defaults(handler=None, help_parser=notify_parser)
    notify_subparsers = notify_parser.add_subparsers(dest="notify_command")
    notify_list_parser = notify_subparsers.add_parser("list")
    notify_list_parser.add_argument("--status", choices=["pending", "sent", "failed", "dismissed"], default=None)
    _add_handler(notify_list_parser, handle_notify_list)
    notify_show_parser = notify_subparsers.add_parser("show")
    notify_show_parser.add_argument("entry_id")
    _add_handler(notify_show_parser, handle_notify_show)
    notify_send_parser = notify_subparsers.add_parser("send")
    notify_send_parser.add_argument("entry_id")
    _add_handler(notify_send_parser, handle_notify_send)
    notify_dismiss_parser = notify_subparsers.add_parser("dismiss")
    notify_dismiss_parser.add_argument("entry_id")
    _add_handler(notify_dismiss_parser, handle_notify_dismiss)
    _add_handler(notify_subparsers.add_parser("stats"), handle_notify_stats)
    notify_watch_parser = notify_subparsers.add_parser("watch")
    notify_watch_parser.add_argument("--interval", type=int, default=5, help="Poll interval in seconds")
    _add_handler(notify_watch_parser, handle_notify_watch)
    _add_handler(notify_subparsers.add_parser("clear"), handle_notify_clear)

    reflection_parser = subparsers.add_parser("reflection")
    reflection_parser.set_defaults(handler=None, help_parser=reflection_parser)
    reflection_subparsers = reflection_parser.add_subparsers(dest="reflection_command")
    reflection_list_parser = reflection_subparsers.add_parser("list")
    reflection_list_parser.add_argument("--tail", type=int, default=20)
    reflection_list_parser.add_argument("--include-started", action="store_true", default=False)
    reflection_list_parser.add_argument("--json", action="store_true", default=False, dest="as_json")
    _add_handler(reflection_list_parser, handle_reflection_list)
    reflection_show_parser = reflection_subparsers.add_parser("show")
    reflection_show_parser.add_argument("event_index", type=int, help="Index from 'reflection list' (0-based)")
    reflection_show_parser.add_argument("--json", action="store_true", default=False, dest="as_json")
    _add_handler(reflection_show_parser, handle_reflection_show)

    memory_parser = subparsers.add_parser("memory")
    memory_parser.set_defaults(handler=None, help_parser=memory_parser)
    memory_subparsers = memory_parser.add_subparsers(dest="memory_command")
    list_parser = memory_subparsers.add_parser("list")
    list_parser.add_argument("--sort-by", choices=["updated_at", "importance", "type"], default="updated_at")
    list_parser.add_argument("--review-state", choices=["draft", "reviewed", "rejected", "quarantined"], default=None)
    _add_handler(list_parser, handle_memory_list)
    preview_parser = memory_subparsers.add_parser("preview")
    preview_parser.add_argument("--limit", type=int, default=DEFAULT_MEMORY_PREVIEW_LIMIT)
    _add_handler(preview_parser, handle_memory_preview)
    show_parser = memory_subparsers.add_parser("show")
    show_parser.add_argument("entry_id")
    _add_handler(show_parser, handle_memory_show)
    add_parser = memory_subparsers.add_parser("add")
    add_parser.add_argument("--type", choices=_memory_type_choices())
    add_parser.add_argument("--title", default=None)
    add_parser.add_argument("--body", "--text", required=True)
    add_parser.add_argument("--tag", action="append", default=[])
    add_parser.add_argument("--importance", type=float, default=None)
    _add_handler(add_parser, handle_memory_add)
    edit_parser = memory_subparsers.add_parser("edit")
    edit_parser.add_argument("entry_id")
    edit_parser.add_argument("--title", default=None)
    edit_parser.add_argument("--body", "--text", default=None)
    edit_parser.add_argument("--tag", action="append", default=None)
    edit_parser.add_argument("--importance", type=float, default=None)
    _add_handler(edit_parser, handle_memory_edit)
    delete_parser = memory_subparsers.add_parser("delete")
    delete_parser.add_argument("entry_id")
    _add_handler(delete_parser, handle_memory_delete)
    search_parser = memory_subparsers.add_parser("search")
    search_parser.add_argument("query", nargs="?", default="")
    search_parser.add_argument("--type", choices=_memory_type_choices(), default=None)
    search_parser.add_argument("--tag", default=None)
    search_parser.add_argument("--review-state", choices=["draft", "reviewed", "rejected", "quarantined"], default=None)
    search_parser.add_argument("--observed-from", default=None)
    search_parser.add_argument("--observed-to", default=None)
    search_parser.add_argument("--valid-on", default=None)
    search_parser.add_argument("--min-importance", type=float, default=None)
    search_parser.add_argument("--sort-by", choices=["score", "updated_at", "importance"], default="score")
    _add_handler(search_parser, handle_memory_search)
    _add_handler(memory_subparsers.add_parser("stats"), handle_memory_stats)
    relations_parser = memory_subparsers.add_parser("relations")
    _relation_names = default_relation_descriptor_registry().names()
    relations_parser.add_argument("--relation", choices=_relation_names, default=None)
    relations_parser.add_argument("--source-id", default=None)
    relations_parser.add_argument("--target-id", default=None)
    _add_handler(relations_parser, handle_memory_relations)
    graph_parser = memory_subparsers.add_parser("graph")
    graph_parser.set_defaults(handler=None, help_parser=graph_parser)
    graph_subparsers = graph_parser.add_subparsers(dest="graph_command")
    graph_nodes_parser = graph_subparsers.add_parser("nodes")
    graph_nodes_parser.add_argument("--type", default=None)
    _add_handler(graph_nodes_parser, handle_memory_graph_nodes)
    graph_edges_parser = graph_subparsers.add_parser("edges")
    graph_edges_parser.add_argument("--relation", choices=_relation_names, default=None)
    graph_edges_parser.add_argument("--source-id", default=None)
    graph_edges_parser.add_argument("--target-id", default=None)
    _add_handler(graph_edges_parser, handle_memory_graph_edges)
    graph_search_parser = graph_subparsers.add_parser("search")
    graph_search_parser.add_argument("query")
    graph_search_parser.add_argument("--type", default=None)
    graph_search_parser.add_argument("--limit", type=int, default=8)
    graph_search_parser.add_argument("--depth", type=int, default=1)
    _add_handler(graph_search_parser, handle_memory_graph_search)
    graph_path_parser = graph_subparsers.add_parser("path")
    graph_path_parser.add_argument("from_id")
    graph_path_parser.add_argument("to_id")
    _add_handler(graph_path_parser, handle_memory_graph_path)
    graph_closure_parser = graph_subparsers.add_parser("closure")
    graph_closure_parser.add_argument("node_id")
    graph_closure_parser.add_argument("--relation", choices=_relation_names, default=None)
    _add_handler(graph_closure_parser, handle_memory_graph_closure)
    _add_handler(memory_subparsers.add_parser("update"), handle_memory_update)
    optimize_parser = memory_subparsers.add_parser("optimize")
    optimize_parser.add_argument("--limit", type=int, default=50)
    _add_handler(optimize_parser, handle_memory_optimize)
    export_parser = memory_subparsers.add_parser("export")
    export_parser.add_argument("--output", "-o", type=Path, required=True)
    _add_handler(export_parser, handle_memory_export)
    import_parser = memory_subparsers.add_parser("import")
    import_parser.add_argument("path", type=Path)
    _add_handler(import_parser, handle_memory_import)
    profile_parser = memory_subparsers.add_parser("profile")
    profile_parser.set_defaults(handler=None, help_parser=profile_parser)
    profile_subparsers = profile_parser.add_subparsers(dest="profile_command")
    profile_list_parser = profile_subparsers.add_parser("list")
    profile_list_parser.add_argument("--sort-by", choices=["updated_at", "importance", "type"], default="updated_at")
    _add_handler(profile_list_parser, handle_memory_profile_list)
    profile_search_parser = profile_subparsers.add_parser("search")
    profile_search_parser.add_argument("query", nargs="?", default="")
    profile_search_parser.add_argument("--type", default=None)
    profile_search_parser.add_argument("--tag", default=None)
    profile_search_parser.add_argument("--observed-from", default=None)
    profile_search_parser.add_argument("--observed-to", default=None)
    profile_search_parser.add_argument("--valid-on", default=None)
    _add_handler(profile_search_parser, handle_memory_profile_search)
    profile_show_parser = profile_subparsers.add_parser("show")
    profile_show_parser.add_argument("profile_id")
    _add_handler(profile_show_parser, handle_memory_profile_show)
    profile_delete_parser = profile_subparsers.add_parser("delete")
    profile_delete_parser.add_argument("profile_id")
    _add_handler(profile_delete_parser, handle_memory_profile_delete)
    _add_handler(profile_subparsers.add_parser("reindex"), handle_memory_profile_reindex)
    candidate_parser = memory_subparsers.add_parser("candidate")
    candidate_parser.set_defaults(handler=None, help_parser=candidate_parser)
    candidate_subparsers = candidate_parser.add_subparsers(dest="candidate_command")
    candidate_list_parser = candidate_subparsers.add_parser("list")
    candidate_list_parser.add_argument("--all", action="store_true")
    candidate_list_parser.add_argument("--review-state", choices=["pending", "accepted", "rejected"], default=None)
    candidate_list_parser.add_argument("--sort-by", choices=["updated_at", "importance", "type"], default="updated_at")
    _add_handler(candidate_list_parser, handle_memory_candidate_list)
    candidate_show_parser = candidate_subparsers.add_parser("show")
    candidate_show_parser.add_argument("candidate_id")
    _add_handler(candidate_show_parser, handle_memory_candidate_show)
    candidate_accept_parser = candidate_subparsers.add_parser("accept")
    candidate_accept_parser.add_argument("candidate_id")
    _add_handler(candidate_accept_parser, handle_memory_candidate_accept)
    candidate_reject_parser = candidate_subparsers.add_parser("reject")
    candidate_reject_parser.add_argument("candidate_id")
    _add_handler(candidate_reject_parser, handle_memory_candidate_reject)
    candidate_edit_parser = candidate_subparsers.add_parser("edit")
    candidate_edit_parser.add_argument("candidate_id")
    candidate_edit_parser.add_argument("--title", default=None)
    candidate_edit_parser.add_argument("--body", "--text", default=None)
    candidate_edit_parser.add_argument("--tag", action="append", default=None)
    candidate_edit_parser.add_argument("--importance", type=float, default=None)
    candidate_edit_parser.add_argument("--observed-at", default=None)
    candidate_edit_parser.add_argument("--valid-from", default=None)
    candidate_edit_parser.add_argument("--valid-until", default=None)
    candidate_edit_parser.add_argument("--temporal-note", default=None)
    _add_handler(candidate_edit_parser, handle_memory_candidate_edit)
    candidate_merge_parser = candidate_subparsers.add_parser("merge")
    candidate_merge_parser.add_argument("candidate_id")
    candidate_merge_parser.add_argument("entry_id")
    _add_handler(candidate_merge_parser, handle_memory_candidate_merge)
    types_parser = memory_subparsers.add_parser("types")
    types_parser.add_argument("--json", action="store_true")
    _add_handler(types_parser, handle_memory_types)
    _add_handler(memory_subparsers.add_parser("reindex"), handle_memory_reindex)
    unquarantine_parser = memory_subparsers.add_parser("unquarantine")
    unquarantine_parser.add_argument("entry_id")
    _add_handler(unquarantine_parser, handle_memory_unquarantine)

    source_parser = subparsers.add_parser("source")
    source_parser.set_defaults(handler=None, help_parser=source_parser)
    source_subparsers = source_parser.add_subparsers(dest="source_command")
    source_ingest_parser = source_subparsers.add_parser("ingest")
    source_ingest_parser.add_argument("path", type=Path)
    source_ingest_parser.add_argument("--tag", action="append", default=[])
    source_ingest_parser.add_argument("--privacy", choices=["private", "shareable"], default="private")
    _add_handler(source_ingest_parser, handle_memory_source_ingest)
    _add_handler(source_subparsers.add_parser("list"), handle_memory_source_list)
    source_show_parser = source_subparsers.add_parser("show")
    source_show_parser.add_argument("source_id")
    _add_handler(source_show_parser, handle_memory_source_show)
    source_delete_parser = source_subparsers.add_parser("delete")
    source_delete_parser.add_argument("source_id")
    _add_handler(source_delete_parser, handle_memory_source_delete)
    source_chunks_parser = source_subparsers.add_parser("chunks")
    source_chunks_parser.add_argument("source_id", nargs="?")
    _add_handler(source_chunks_parser, handle_memory_source_chunks)
    source_search_parser = source_subparsers.add_parser("search")
    source_search_parser.add_argument("query")
    source_search_parser.add_argument("--limit", type=int, default=8)
    _add_handler(source_search_parser, handle_memory_source_search)
    source_extract_parser = source_subparsers.add_parser("extract")
    source_extract_parser.add_argument("source_id")
    _add_handler(source_extract_parser, handle_memory_source_extract)

    thread_parser = subparsers.add_parser("thread")
    thread_parser.set_defaults(handler=None, help_parser=thread_parser)
    thread_subparsers = thread_parser.add_subparsers(dest="thread_command")
    _add_handler(thread_subparsers.add_parser("list"), handle_thread_list)
    thread_show_parser = thread_subparsers.add_parser("show")
    thread_show_parser.add_argument("thread_id")
    _add_handler(thread_show_parser, handle_thread_show)
    thread_create_parser = thread_subparsers.add_parser("create")
    thread_create_parser.add_argument("thread_id")
    _add_handler(thread_create_parser, handle_thread_create)
    thread_rename_parser = thread_subparsers.add_parser("rename")
    thread_rename_parser.add_argument("old_thread_id")
    thread_rename_parser.add_argument("new_thread_id")
    _add_handler(thread_rename_parser, handle_thread_rename)
    thread_branch_parser = thread_subparsers.add_parser("branch")
    thread_branch_parser.add_argument("source_thread_id")
    thread_branch_parser.add_argument("new_thread_id")
    thread_branch_parser.add_argument("--index", type=int, default=None)
    _add_handler(thread_branch_parser, handle_thread_branch)
    thread_archive_parser = thread_subparsers.add_parser("archive")
    thread_archive_parser.add_argument("thread_id")
    _add_handler(thread_archive_parser, handle_thread_archive)
    thread_delete_parser = thread_subparsers.add_parser("delete")
    thread_delete_parser.add_argument("thread_id")
    _add_handler(thread_delete_parser, handle_thread_delete)
    thread_unarchive_parser = thread_subparsers.add_parser("unarchive")
    thread_unarchive_parser.add_argument("thread_id")
    _add_handler(thread_unarchive_parser, handle_thread_unarchive)
    _add_handler(thread_subparsers.add_parser("archived"), handle_thread_archived)

    return parser


def _add_handler(parser: argparse.ArgumentParser, handler: object) -> None:
    parser.set_defaults(handler=handler)


def _add_log_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--component", choices=list(LOG_COMPONENTS), default=None)
    parser.add_argument("--tail", type=int, default=50)
    parser.add_argument("--follow", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-color", action="store_true")
    _add_handler(parser, handle_logs)


def handle_daemon_start(args: argparse.Namespace) -> int:
    write_log_event("daemon", "start_requested", "daemon start requested", project_root=args.project_root)
    result = lifecycle.start(args.project_root)
    write_log_event(
        "daemon",
        "start_completed",
        f"daemon start {'completed' if result.running else 'failed'}",
        project_root=args.project_root,
        status="running" if result.running else "stopped",
        metadata={"pid": result.pid, "socket": str(result.socket_path)},
    )
    print(_format_status(result))
    return 0 if result.running else 1


def handle_daemon_stop(args: argparse.Namespace) -> int:
    write_log_event("daemon", "stop_requested", "daemon stop requested", project_root=args.project_root)
    result = lifecycle.stop(args.project_root)
    write_log_event(
        "daemon",
        "stop_completed",
        f"daemon stop {'completed' if not result.running else 'failed'}",
        project_root=args.project_root,
        status="stopped" if not result.running else "running",
        metadata={"pid": result.pid, "socket": str(result.socket_path)},
    )
    print(_format_status(result))
    return 0 if not result.running else 1


def handle_daemon_restart(args: argparse.Namespace) -> int:
    write_log_event("daemon", "restart_requested", "daemon restart requested", project_root=args.project_root)
    stop_result = lifecycle.stop(args.project_root)
    if stop_result.running:
        print(f"Failed to stop daemon: {_format_status(stop_result)}", file=sys.stderr)
        return 1
    print(f"Stopped: {_format_status(stop_result)}")
    start_result = lifecycle.start(args.project_root)
    write_log_event(
        "daemon",
        "restart_completed",
        f"daemon restart {'completed' if start_result.running else 'failed'}",
        project_root=args.project_root,
        status="running" if start_result.running else "stopped",
        metadata={"pid": start_result.pid, "socket": str(start_result.socket_path)},
    )
    print(f"Started: {_format_status(start_result)}")
    return 0 if start_result.running else 1


def handle_daemon_status(args: argparse.Namespace) -> int:
    result = lifecycle.status(args.project_root)
    print(_format_status(result))
    return 0 if result.running else 1


def handle_daemon_list(args: argparse.Namespace) -> int:
    result = lifecycle.status(args.project_root)
    print(_format_daemon_list(result))
    return 0


def handle_default_entrypoint(args: argparse.Namespace) -> int:
    result = lifecycle.status(args.project_root)
    if result.running:
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
    print("Tip: type :help for commands, :q to quit, or start chatting.")
    return _interactive_loop(lambda message, thread_id: _send_chat(message, args.project_root, thread_id), args.project_root)


def handle_status(args: argparse.Namespace) -> int:
    daemon = lifecycle.status(args.project_root)
    threads = ThreadStore(args.project_root).list()
    from nuself.notification import NotificationOutbox

    pending = len(NotificationOutbox(args.project_root).list(status="pending"))
    print(f"daemon: {'running' if daemon.running else 'stopped'} pid={daemon.pid or '-'}")
    print(f"threads: {len(threads)}")
    print(f"pending notifications: {pending}")
    return 0


def handle_health(args: argparse.Namespace) -> int:
    issues: list[str] = []
    paths = runtime_paths(args.project_root)
    config_path = paths.private_root / "config.yaml"

    if not paths.private_root.exists():
        issues.append(f"private root missing: {paths.private_root}")
    if paths.private_root.exists() and not config_path.exists():
        issues.append(f"config file missing: {config_path}")

    daemon = lifecycle.status(args.project_root)
    if not daemon.running:
        issues.append("daemon is not running")

    if issues:
        print("Health issues:")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("All checks passed.")
    return 0


def handle_config(args: argparse.Namespace) -> int:
    paths = runtime_paths(args.project_root)
    config_path = paths.private_root / "config.yaml"
    print(f"project_root: {paths.project_root}")
    print(f"private_root: {paths.private_root}")
    print(f"socket_path: {paths.socket_path}")
    print(f"config_path: {config_path}")
    print(f"config_file: {'found' if config_path.exists() else 'not found (using defaults)'}")

    system_config = ConfigSystem.load(config_path, args.project_root)
    print("config_effective:")
    config_system = ConfigSystem()
    for key, value in sorted(config_system.as_flat_dict(system_config).items()):
        print(f"  {key}: {value}")
    return 0


def handle_logs(args: argparse.Namespace) -> int:
    component = _log_component_arg(args.component)
    tail = max(args.tail, 1)
    events = read_log_events(project_root=args.project_root, component=component, tail=tail)
    if not events:
        target = component or "any component"
        print(f"No logs found for {target}.")
        return 0
    for event in events:
        if args.json:
            print(render_log_event_json(event))
        else:
            print(render_log_event(event, color=False if args.no_color else None))
    if args.follow:
        print("Log follow is not streaming yet; showing current tail only.", file=sys.stderr)
    return 0


def handle_chat(args: argparse.Namespace) -> int:
    if lifecycle.status(args.project_root).running:
        if args.message is not None:
            return _send_chat(args.message, args.project_root)
        return _interactive_loop(lambda message, thread_id: _send_chat(message, args.project_root, thread_id), args.project_root)
    if args.require_daemon:
        print("NuSelf daemon is not running.", file=sys.stderr)
        return 1
    if args.message is not None:
        return _send_one_shot_chat(args.message, args.project_root)
    return _interactive_loop(lambda message, thread_id: _send_one_shot_chat(message, args.project_root, thread_id), args.project_root)


def handle_attach(args: argparse.Namespace) -> int:
    if not lifecycle.status(args.project_root).running:
        print("NuSelf daemon is not running.", file=sys.stderr)
        return 1
    if args.message is not None:
        return _send_chat(args.message, args.project_root)
    return _interactive_loop(lambda message, thread_id: _send_chat(message, args.project_root, thread_id), args.project_root)


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
            lambda message, tid: _send_chat(message, args.project_root, tid),
            args.project_root,
            initial_thread_id=thread_id,
        )
    if args.message is not None:
        result = _send_one_shot_chat(args.message, args.project_root, thread_id)
        if result != 0:
            return result
    return _interactive_loop(
        lambda message, tid: _send_one_shot_chat(message, args.project_root, tid),
        args.project_root,
        initial_thread_id=thread_id,
    )


def handle_memory_list(args: argparse.Namespace) -> int:
    repo = MemoryEntryRepository(args.project_root)
    entries = repo.list()
    if args.review_state is not None:
        entries = [e for e in entries if e.review_state == args.review_state]
    if not entries:
        print("No memory entries.")
        return 0
    sort_by = args.sort_by
    if sort_by == "importance":
        entries = sorted(entries, key=lambda e: (-e.importance, e.updated_at, e.id))
    elif sort_by == "type":
        entries = sorted(entries, key=lambda e: (e.type, e.updated_at, e.id))
    for entry in entries:
        print(render_memory_entry_row(entry))
    return 0


def handle_memory_preview(args: argparse.Namespace) -> int:
    print(_format_memory_preview(args.project_root, args.limit))
    return 0


def handle_memory_show(args: argparse.Namespace) -> int:
    repo = MemoryEntryRepository(args.project_root)
    try:
        entry = repo.get(args.entry_id)
    except MemoryEntryNotFound:
        print(f"Memory entry not found: {args.entry_id}", file=sys.stderr)
        return 1
    print(render_memory_entry_detail(entry))
    return 0


def handle_memory_add(args: argparse.Namespace) -> int:
    repo = MemoryEntryRepository(args.project_root)
    inferred = MemoryIntakeAgent(args.project_root).infer(
        body=args.body,
        title=args.title,
        memory_type=args.type,
        tags=list(args.tag),
    )
    entry = MemoryEntry(
        type=inferred.type,
        title=inferred.title,
        body=inferred.body,
        tags=list(inferred.tags),
        confidence=inferred.confidence,
        importance=args.importance if args.importance is not None else inferred.importance,
    )
    repo.save(entry)
    repo.reindex()
    print(render_memory_entry_row(entry))
    return 0


def handle_memory_edit(args: argparse.Namespace) -> int:
    repo = MemoryEntryRepository(args.project_root)
    try:
        entry = repo.get(args.entry_id)
    except MemoryEntryNotFound:
        print(f"Memory entry not found: {args.entry_id}", file=sys.stderr)
        return 1
    updated = entry.with_updates(
        title=args.title,
        body=args.body,
        tags=list(args.tag) if args.tag is not None else None,
        importance=args.importance,
    )
    repo.save(updated)
    repo.reindex()
    print(render_memory_entry_row(updated))
    return 0


def handle_memory_delete(args: argparse.Namespace) -> int:
    repo = MemoryEntryRepository(args.project_root)
    try:
        repo.delete(args.entry_id)
    except MemoryEntryNotFound:
        print(f"Memory entry not found: {args.entry_id}", file=sys.stderr)
        return 1
    repo.reindex()
    print(f"Deleted memory entry: {args.entry_id}")
    return 0


def handle_memory_search(args: argparse.Namespace) -> int:
    repo = MemoryEntryRepository(args.project_root)
    entries = repo.search(
        args.query,
        MemorySearchFilters(
            type=args.type,
            tag=args.tag,
            review_state=args.review_state,
            observed_from=args.observed_from,
            observed_to=args.observed_to,
            valid_on=args.valid_on,
            min_importance=args.min_importance,
        ),
    )
    if not entries:
        print("No matching memory entries.")
        return 0
    for entry in entries:
        print(render_memory_entry_row(entry))
    return 0


def handle_memory_stats(args: argparse.Namespace) -> int:
    print(_format_memory_stats(memory_stats(args.project_root)))
    return 0


def handle_memory_relations(args: argparse.Namespace) -> int:
    records = MemoryEntryRepository(args.project_root).list_relations(
        MemoryRelationFilters(
            relation=args.relation,
            source_id=args.source_id,
            target_id=args.target_id,
        )
    )
    if not records:
        print("No memory relations.")
        return 0
    for record in records:
        print(_format_memory_relation(record))
    return 0


def handle_memory_graph_nodes(args: argparse.Namespace) -> int:
    nodes = MemoryEntryRepository(args.project_root).list_graph_nodes(
        SymbolicGraphNodeFilters(type=args.type)
    )
    if not nodes:
        print("No symbolic graph nodes.")
        return 0
    for node in nodes:
        print(_format_symbolic_graph_node(node))
    return 0


def handle_memory_graph_edges(args: argparse.Namespace) -> int:
    edges = MemoryEntryRepository(args.project_root).list_graph_edges(
        SymbolicGraphEdgeFilters(
            relation=args.relation,
            source_id=args.source_id,
            target_id=args.target_id,
        )
    )
    if not edges:
        print("No symbolic graph edges.")
        return 0
    for edge in edges:
        print(_format_symbolic_graph_edge(edge))
    return 0


def handle_memory_graph_search(args: argparse.Namespace) -> int:
    result = MemoryEntryRepository(args.project_root).search_graph(
        args.query,
        node_type=args.type,
        limit=args.limit,
        depth=args.depth,
    )
    if not result.nodes:
        print("No symbolic graph matches.")
        return 0
    print("Nodes:")
    for node in result.nodes:
        print(_format_symbolic_graph_node(node))
    if result.edges:
        print("Edges:")
        for edge in result.edges:
            print(_format_symbolic_graph_edge(edge))
    return 0


def handle_memory_graph_path(args: argparse.Namespace) -> int:
    repo = MemoryEntryRepository(args.project_root)
    path = repo.find_path(args.from_id, args.to_id)
    if not path:
        print("No path found.")
        return 0
    print("Path:")
    for edge in path:
        print(_format_symbolic_graph_edge(edge))
    return 0


def handle_memory_graph_closure(args: argparse.Namespace) -> int:
    repo = MemoryEntryRepository(args.project_root)
    if args.relation is None:
        print("--relation is required for closure.")
        return 1
    result = repo.transitive_closure(args.node_id, args.relation)
    if not result.nodes:
        print("No closure nodes.")
        return 0
    print("Nodes:")
    for node in result.nodes:
        print(_format_symbolic_graph_node(node))
    if result.edges:
        print("Edges:")
        for edge in result.edges:
            print(_format_symbolic_graph_edge(edge))
    return 0


def handle_memory_types(args: argparse.Namespace) -> int:
    registry = default_memory_type_registry()
    if args.json:
        import json as _json

        output: list[dict[str, object]] = []
        for name in registry.names():
            example = registry.example(name)
            output.append(
                {
                    "type": name,
                    "description": registry.describe(name),
                    "default_importance": registry.importance(example) if example is not None else None,
                    "example": example.to_wire() if example is not None else None,
                }
            )
        print(_json.dumps(output, indent=2, ensure_ascii=False))
    else:
        for name in registry.names():
            example = registry.example(name)
            default_imp = registry.importance(example) if example is not None else 0.5
            print(f"{name}: {registry.describe(name)} (default importance {default_imp})")
    return 0


def handle_memory_reindex(args: argparse.Namespace) -> int:
    memory_repo = MemoryEntryRepository(args.project_root)
    memory_index_path = memory_repo.reindex()
    relation_index_path = memory_repo.reindex_relations()
    graph_index_path = memory_repo.reindex_symbolic_graph()
    source_index_path = SourceRepository(args.project_root).reindex()
    profile_index_path = ProfileItemRepository(args.project_root).reindex()
    print(f"Rebuilt memory index: {memory_index_path}")
    print(f"Rebuilt relation index: {relation_index_path}")
    print(f"Rebuilt symbolic graph: {graph_index_path}")
    print(f"Rebuilt source index: {source_index_path}")
    print(f"Rebuilt profile index: {profile_index_path}")
    return 0


def handle_memory_unquarantine(args: argparse.Namespace) -> int:
    repo = MemoryEntryRepository(args.project_root)
    try:
        repo.unquarantine(args.entry_id)
    except MemoryEntryNotFound:
        print(f"Memory entry not found: {args.entry_id}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Unquarantined memory entry: {args.entry_id}")
    return 0


def handle_thread_list(args: argparse.Namespace) -> int:
    store = ThreadStore(args.project_root)
    ids = store.list()
    if not ids:
        print("No active threads.")
        return 0
    for tid in ids:
        print(tid)
    return 0


def handle_thread_show(args: argparse.Namespace) -> int:
    store = ThreadStore(args.project_root)
    state = store.load(args.thread_id)
    if not state.messages and args.thread_id not in store.list():
        print(f"Thread not found: {args.thread_id}", file=sys.stderr)
        return 1
    print(f"Thread: {args.thread_id}")
    if state.summary:
        print(f"Summary: {state.summary}")
    print(f"Messages: {len(state.messages)}")
    for msg in state.messages:
        prefix = ">" if msg.role == "user" else "<"
        content = msg.content[:120]
        if len(msg.content) > 120:
            content += "..."
        print(f"  {prefix} {content}")
    return 0


def handle_thread_create(args: argparse.Namespace) -> int:
    store = ThreadStore(args.project_root)
    if args.thread_id in store.list():
        print(f"Thread already exists: {args.thread_id}", file=sys.stderr)
        return 1
    store.save(ThreadState.empty(args.thread_id))
    print(f"Created thread: {args.thread_id}")
    return 0


def handle_thread_rename(args: argparse.Namespace) -> int:
    store = ThreadStore(args.project_root)
    try:
        store.rename(args.old_thread_id, args.new_thread_id)
        print(f"Renamed thread: {args.old_thread_id} -> {args.new_thread_id}")
        return 0
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def handle_thread_branch(args: argparse.Namespace) -> int:
    store = ThreadStore(args.project_root)
    try:
        store.branch(args.source_thread_id, args.new_thread_id, args.index)
        print(f"Branched thread: {args.source_thread_id} -> {args.new_thread_id}")
        return 0
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def handle_thread_archive(args: argparse.Namespace) -> int:
    store = ThreadStore(args.project_root)
    try:
        store.archive(args.thread_id)
        print(f"Archived thread: {args.thread_id}")
        return 0
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def handle_thread_delete(args: argparse.Namespace) -> int:
    store = ThreadStore(args.project_root)
    try:
        store.delete(args.thread_id)
        print(f"Deleted thread: {args.thread_id}")
        return 0
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def handle_thread_unarchive(args: argparse.Namespace) -> int:
    store = ThreadStore(args.project_root)
    try:
        store.unarchive(args.thread_id)
        print(f"Unarchived thread: {args.thread_id}")
        return 0
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def handle_thread_archived(args: argparse.Namespace) -> int:
    store = ThreadStore(args.project_root)
    ids = store.list_archived()
    if not ids:
        print("No archived threads.")
        return 0
    for thread_id in ids:
        print(thread_id)
    return 0


def handle_eval(args: argparse.Namespace) -> int:
    import sys
    from nuself.eval import run_eval, load_fixtures

    component: str = args.component
    all_passed = 0
    all_total = 0

    if component in ("conversations", "all"):
        fixtures_dir = args.fixtures or (Path(__file__).parent.parent / "tests" / "fixtures" / "conversations")
        if fixtures_dir.exists():
            fixtures = load_fixtures(fixtures_dir)
            if fixtures:
                import tempfile
                with tempfile.TemporaryDirectory() as tmp:
                    results = run_eval(Path(tmp), fixtures_dir)
                passed = sum(1 for r in results if r.passed)
                total = len(results)
                all_passed += passed
                all_total += total
                print(f"== conversations: {passed}/{total} passed ==")
                for result in results:
                    status = "PASS" if result.passed else "FAIL"
                    print(f"  {status} {result.fixture_name} (score={result.score:.2f})")
                    for failure in result.failures:
                        print(f"    - {failure}")
            else:
                print("No conversation fixtures found.")
        else:
            print(f"Fixtures directory not found: {fixtures_dir}", file=sys.stderr)

    if component in ("notifications", "all"):
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_notification_eval_fixtures.py", "-v"],
            capture_output=True,
            text=True,
        )
        print("== notifications ==")
        print(result.stdout)
        if result.returncode == 0:
            all_passed += 3  # rough count; actual count from pytest output
            all_total += 3
        else:
            all_total += 3
            print(result.stderr, file=sys.stderr)

    print(f"\n{all_passed}/{all_total} passed")
    return 0 if all_passed == all_total and all_total > 0 else 1


def handle_notify_list(args: argparse.Namespace) -> int:
    from nuself.notification import NotificationOutbox
    from nuself.tui.render import render_outbox_summary

    outbox = NotificationOutbox(args.project_root)
    status = args.status
    entries = outbox.list(status=status)
    if not entries:
        filter_msg = f" with status '{status}'" if status else ""
        print(f"No outbox entries{filter_msg}.")
        return 0
    for entry in entries:
        print(render_outbox_summary(entry))
    return 0


def handle_notify_show(args: argparse.Namespace) -> int:
    from nuself.notification import NotificationOutbox, OutboxEntryNotFound
    from nuself.tui.render import render_outbox_detail

    try:
        entry = NotificationOutbox(args.project_root).get(args.entry_id)
    except OutboxEntryNotFound:
        print(f"Outbox entry not found: {args.entry_id}", file=sys.stderr)
        return 1
    print(render_outbox_detail(entry))
    return 0


def handle_notify_stats(args: argparse.Namespace) -> int:
    from nuself.notification import NotificationOutbox

    outbox = NotificationOutbox(args.project_root)
    entries = outbox.list()
    counts: dict[str, int] = {"pending": 0, "sent": 0, "failed": 0, "dismissed": 0}
    for entry in entries:
        counts[entry.status] = counts.get(entry.status, 0) + 1
    print(f"Total:      {len(entries)}")
    print(f"Pending:    {counts['pending']}")
    print(f"Sent:       {counts['sent']}")
    print(f"Failed:     {counts['failed']}")
    print(f"Dismissed:  {counts['dismissed']}")
    return 0


def handle_notify_watch(args: argparse.Namespace) -> int:
    import time

    from nuself.notification import NotificationOutbox
    from nuself.tui.render import render_outbox_summary

    outbox = NotificationOutbox(args.project_root)
    interval: float = max(1, args.interval)
    print(f"Watching outbox every {int(interval)}s. Press Ctrl+C or type 'q' + Enter to quit.")

    seen: set[str] = set()
    for entry in outbox.list():
        seen.add(entry.id)

    try:
        while True:
            time.sleep(interval)
            for entry in outbox.list():
                if entry.id not in seen:
                    seen.add(entry.id)
                    print(render_outbox_summary(entry))
            # Non-blocking check for 'q' is not possible with plain input();
            # rely on Ctrl+C for clean exit.
    except KeyboardInterrupt:
        print("\nStopped watching.")
        return 0


def handle_notify_send(args: argparse.Namespace) -> int:
    from nuself.notification import NotificationOutbox, LogOnlyNotificationAdapter, OutboxEntryNotFound

    outbox = NotificationOutbox(args.project_root)
    try:
        entry = outbox.get(args.entry_id)
    except OutboxEntryNotFound:
        print(f"Outbox entry not found: {args.entry_id}", file=sys.stderr)
        return 1
    adapter = LogOnlyNotificationAdapter(args.project_root)
    if adapter.send(entry):
        outbox.mark_sent(args.entry_id)
        print(f"Sent: {entry.id}")
        return 0
    outbox.mark_failed(args.entry_id)
    print(f"Failed to send: {entry.id}", file=sys.stderr)
    return 1


def handle_notify_dismiss(args: argparse.Namespace) -> int:
    from nuself.notification import NotificationOutbox, OutboxEntryNotFound

    try:
        NotificationOutbox(args.project_root).dismiss(args.entry_id)
        print(f"Dismissed: {args.entry_id}")
        return 0
    except OutboxEntryNotFound:
        print(f"Outbox entry not found: {args.entry_id}", file=sys.stderr)
        return 1


def handle_notify_clear(args: argparse.Namespace) -> int:
    from nuself.notification import NotificationOutbox

    count = NotificationOutbox(args.project_root).clear("dismissed")
    print(f"Cleared {count} dismissed notification(s).")
    return 0


def handle_reflection_list(args: argparse.Namespace) -> int:
    from nuself.tui.render import render_reflection_summary

    events = read_log_events(project_root=args.project_root, component="reflection", tail=args.tail)
    if not getattr(args, "include_started", False):
        events = [event for event in events if event.event != "cycle_started"]
    if not events:
        print("No reflection events.")
        return 0
    if args.as_json:
        import json

        for event in events:
            print(json.dumps(event.to_record(), sort_keys=True, ensure_ascii=True))
        return 0
    for idx, event in enumerate(events):
        print(f"[{idx:3d}] {render_reflection_summary(event)}")
    return 0


def handle_reflection_show(args: argparse.Namespace) -> int:
    from nuself.logs import LogEvent
    from nuself.tui.render import render_reflection_detail

    all_events: list[LogEvent] = read_log_events(project_root=args.project_root, component="reflection")
    if not all_events:
        print("No reflection events.", file=sys.stderr)
        return 1
    if args.event_index < 0 or args.event_index >= len(all_events):
        print(f"Invalid index {args.event_index}. Valid range: 0-{len(all_events) - 1}", file=sys.stderr)
        return 1
    selected = all_events[args.event_index]  # pyright: ignore[reportUnknownVariableType]
    if args.as_json:
        import json

        print(json.dumps(selected.to_record(), sort_keys=True, ensure_ascii=True))  # pyright: ignore[reportUnknownMemberType]
        return 0
    print(render_reflection_detail(selected))  # pyright: ignore[reportUnknownArgumentType]
    return 0


def handle_memory_update(args: argparse.Namespace) -> int:
    result = MemoryCurator(args.project_root).run_once()
    print(f"Memory curator: {result.summary()} log={result.log_path}")
    return 0


def handle_memory_optimize(args: argparse.Namespace) -> int:
    settings = MemoryOptimizerSettings(memory_limit=args.limit)
    result = MemoryOptimizer(args.project_root, settings=settings).run_once()
    print(f"Memory optimizer: {result.summary()} log={result.log_path}")
    return 0


def handle_memory_export(args: argparse.Namespace) -> int:
    import json

    repo = MemoryEntryRepository(args.project_root)
    entries = repo.list()
    data = [entry.to_wire() for entry in entries]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Exported {len(data)} memory entries to {args.output}")
    return 0


def handle_memory_import(args: argparse.Namespace) -> int:
    import json

    if not args.path.exists():
        print(f"Import file not found: {args.path}", file=sys.stderr)
        return 1
    raw: object = json.loads(args.path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        print("Import file must contain a JSON array of memory entries.", file=sys.stderr)
        return 1
    repo = MemoryEntryRepository(args.project_root)
    from typing import cast

    data = cast(list[object], raw)
    imported = 0
    for item in data:
        if not isinstance(item, dict):
            continue
        entry = MemoryEntry.from_wire(cast(dict[str, object], item))
        repo.save(entry)
        imported += 1
    repo.reindex()
    print(f"Imported {imported} memory entries from {args.path}")
    return 0


def handle_memory_candidate_list(args: argparse.Namespace) -> int:
    repo = MemoryCandidateRepository(args.project_root)
    candidates = repo.list(include_reviewed=args.all)
    if args.review_state is not None:
        candidates = [c for c in candidates if c.review_state == args.review_state]
    if not candidates:
        print("No memory candidates.")
        return 0
    sort_by = args.sort_by
    if sort_by == "importance":
        candidates = sorted(candidates, key=lambda c: (-c.importance, c.updated_at, c.id))
    elif sort_by == "type":
        candidates = sorted(candidates, key=lambda c: (c.type, c.updated_at, c.id))
    for i, candidate in enumerate(candidates):
        if i > 0:
            print()
        print(render_candidate_row(candidate))
    pending = [c for c in candidates if c.review_state == "pending"]
    if pending:
        print()
        print(f"{len(pending)} pending candidate(s). Accept: nuself memory candidate accept <id>")
    return 0


def handle_memory_candidate_show(args: argparse.Namespace) -> int:
    repo = MemoryCandidateRepository(args.project_root)
    try:
        candidate = repo.get(args.candidate_id)
    except MemoryCandidateNotFound:
        print(f"Memory candidate not found: {args.candidate_id}", file=sys.stderr)
        return 1
    print(render_candidate_detail(candidate))
    return 0


def handle_memory_candidate_accept(args: argparse.Namespace) -> int:
    repo = MemoryCandidateRepository(args.project_root)
    try:
        entry = repo.accept(args.candidate_id)
    except MemoryCandidateNotFound:
        print(f"Memory candidate not found: {args.candidate_id}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Accepted memory candidate: {args.candidate_id} -> {entry.id}")
    return 0


def handle_memory_candidate_reject(args: argparse.Namespace) -> int:
    repo = MemoryCandidateRepository(args.project_root)
    try:
        repo.reject(args.candidate_id)
    except MemoryCandidateNotFound:
        print(f"Memory candidate not found: {args.candidate_id}", file=sys.stderr)
        return 1
    print(f"Rejected memory candidate: {args.candidate_id}")
    return 0


def handle_memory_candidate_edit(args: argparse.Namespace) -> int:
    repo = MemoryCandidateRepository(args.project_root)
    try:
        updated = repo.edit(
            args.candidate_id,
            title=args.title,
            body=args.body,
            tags=list(args.tag) if args.tag is not None else None,
            importance=args.importance,
            observed_at=args.observed_at,
            valid_from=args.valid_from,
            valid_until=args.valid_until,
            temporal_note=args.temporal_note,
        )
    except MemoryCandidateNotFound:
        print(f"Memory candidate not found: {args.candidate_id}", file=sys.stderr)
        return 1
    print(render_candidate_row(updated))
    return 0


def handle_memory_candidate_merge(args: argparse.Namespace) -> int:
    repo = MemoryCandidateRepository(args.project_root)
    try:
        entry = repo.merge(args.candidate_id, args.entry_id)
    except MemoryCandidateNotFound:
        print(f"Memory candidate not found: {args.candidate_id}", file=sys.stderr)
        return 1
    except MemoryEntryNotFound:
        print(f"Memory entry not found: {args.entry_id}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Merged memory candidate: {args.candidate_id} -> {entry.id}")
    return 0


def handle_memory_source_ingest(args: argparse.Namespace) -> int:
    repo = SourceRepository(args.project_root)
    try:
        result = repo.ingest_path(args.path, tags=list(args.tag), privacy=_privacy_arg(args.privacy))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Source ingest: {result.summary()}")
    return 0


def handle_memory_source_list(args: argparse.Namespace) -> int:
    repo = SourceRepository(args.project_root)
    documents = repo.list_documents()
    if not documents:
        print("No source documents.")
        return 0
    for document in documents:
        print(render_source_row(document))
    return 0


def handle_memory_source_show(args: argparse.Namespace) -> int:
    repo = SourceRepository(args.project_root)
    try:
        document = repo.get_document(args.source_id)
    except SourceDocumentNotFound:
        print(f"Source document not found: {args.source_id}", file=sys.stderr)
        return 1
    print(render_source_detail(document, chunk_count=len(repo.list_chunks(document.id))))
    return 0


def handle_memory_source_delete(args: argparse.Namespace) -> int:
    source_repo = SourceRepository(args.project_root)
    profile_repo = ProfileItemRepository(args.project_root)
    try:
        source_repo.delete_document(args.source_id)
    except SourceDocumentNotFound:
        print(f"Source document not found: {args.source_id}", file=sys.stderr)
        return 1
    source_repo.reindex()
    profile_repo.reindex()
    print(f"Deleted source document: {args.source_id}")
    return 0


def handle_memory_source_chunks(args: argparse.Namespace) -> int:
    chunks = SourceRepository(args.project_root).list_chunks(args.source_id)
    if not chunks:
        print("No source chunks.")
        return 0
    for chunk in chunks:
        print(_format_source_chunk_summary(chunk))
    return 0


def handle_memory_source_search(args: argparse.Namespace) -> int:
    matches = SourceRepository(args.project_root).search(args.query, limit=args.limit)
    if not matches:
        print("No matching source chunks.")
        return 0
    for match in matches:
        print(_format_source_chunk_match(match))
    return 0


def handle_memory_source_extract(args: argparse.Namespace) -> int:
    source_repo = SourceRepository(args.project_root)
    candidate_repo = MemoryCandidateRepository(args.project_root)
    try:
        candidates = source_repo.extract_candidates(args.source_id)
    except SourceDocumentNotFound:
        print(f"Source document not found: {args.source_id}", file=sys.stderr)
        return 1
    if not candidates:
        print("No source chunks to extract.")
        return 0
    for candidate in candidates:
        candidate_repo.save(candidate)
    print(f"Extracted source candidates: source={args.source_id} candidates={len(candidates)}")
    return 0


def handle_memory_profile_list(args: argparse.Namespace) -> int:
    repo = ProfileItemRepository(args.project_root)
    items = repo.list()
    if not items:
        print("No profile items.")
        return 0
    sort_by = args.sort_by
    if sort_by == "importance":
        items = sorted(items, key=lambda i: (-i.importance, i.updated_at, i.id))
    elif sort_by == "type":
        items = sorted(items, key=lambda i: (i.type, i.updated_at, i.id))
    for item in items:
        print(render_profile_row(item))
    return 0


def handle_memory_profile_search(args: argparse.Namespace) -> int:
    repo = ProfileItemRepository(args.project_root)
    items = repo.search(
        args.query,
        ProfileSearchFilters(
            type=args.type,
            tag=args.tag,
            observed_from=args.observed_from,
            observed_to=args.observed_to,
            valid_on=args.valid_on,
        ),
    )
    if not items:
        print("No matching profile items.")
        return 0
    for item in items:
        print(render_profile_row(item))
    return 0


def handle_memory_profile_show(args: argparse.Namespace) -> int:
    repo = ProfileItemRepository(args.project_root)
    try:
        item = repo.get(args.profile_id)
    except ProfileItemNotFound:
        print(f"Profile item not found: {args.profile_id}", file=sys.stderr)
        return 1
    print(render_profile_detail(item))
    return 0


def handle_memory_profile_delete(args: argparse.Namespace) -> int:
    repo = ProfileItemRepository(args.project_root)
    try:
        repo.delete(args.profile_id)
    except ProfileItemNotFound:
        print(f"Profile item not found: {args.profile_id}", file=sys.stderr)
        return 1
    repo.reindex()
    print(f"Deleted profile item: {args.profile_id}")
    return 0


def handle_memory_profile_reindex(args: argparse.Namespace) -> int:
    profile_index_path = ProfileItemRepository(args.project_root).reindex()
    print(f"Rebuilt profile index: {profile_index_path}")
    return 0


def _send_chat(message: str, project_root: Path | None, thread_id: str = "default") -> int:
    try:
        response = client.request(
            "chat",
            {"message": message, "thread_id": thread_id},
            project_root=project_root,
            timeout=CHAT_REQUEST_TIMEOUT_SECONDS,
        )
    except client.DaemonConnectionError as exc:
        print(f"daemon request failed: {exc}", file=sys.stderr)
        return 1
    if response.status == "error":
        write_log_event(
            "chat",
            "daemon_chat_failed",
            "daemon chat request failed",
            project_root=project_root,
            level="error",
            status="error",
            error=response.error or "daemon returned an error",
        )
        print(response.error or "daemon returned an error", file=sys.stderr)
        return 1
    reply = response.payload.get("reply")
    if isinstance(reply, str):
        print(reply)
        memory_update = response.payload.get("memory_update")
        if isinstance(memory_update, str) and memory_update != "":
            print(f"[memory] {memory_update}")
        write_log_event(
            "chat",
            "daemon_chat_completed",
            "daemon chat request completed",
            project_root=project_root,
            thread_id=_optional_payload_str(response.payload.get("thread_id")),
            status="ok",
        )
        return 0
    print("daemon response did not include a reply", file=sys.stderr)
    return 1


def _interactive_loop(
    send_message: Callable[[str, str], int],
    project_root: Path | None,
    *,
    initial_thread_id: str = "default",
) -> int:
    history_path = _load_interactive_history(project_root)
    _setup_interactive_completer(project_root)
    current_thread_id = initial_thread_id
    print(_brand_banner())
    print("νSelf interactive mode. Type :q, :quit, or :exit to leave.")
    print(render_session_header(daemon_status=_interactive_daemon_status(project_root), thread_id=current_thread_id))
    try:
        while True:
            try:
                line = input("NuSelf> ")
            except EOFError:
                print()
                return 0
            message = line.strip()
            if message == "":
                continue
            _remember_interactive_input(message)
            if message.startswith(":"):
                command_result, current_thread_id = _handle_interactive_command(
                    message, project_root, current_thread_id
                )
                if command_result == "exit":
                    return 0
                if command_result == "redraw_header":
                    print(render_session_header(daemon_status=_interactive_daemon_status(project_root), thread_id=current_thread_id))
                continue
            print()
            event_offset = len(read_log_events(project_root=project_root))
            result = send_message(message, current_thread_id)
            _print_interactive_activity(project_root, event_offset)
            print()
            print(render_session_header(daemon_status=_interactive_daemon_status(project_root), thread_id=current_thread_id))
            if result != 0:
                return result
    finally:
        if history_path is not None:
            _write_interactive_history(history_path)
        _run_memory_curator(project_root)


_INTERACTIVE_COMMANDS = [
    ":q",
    ":quit",
    ":exit",
    ":history",
    ":sources",
    ":search",
    ":whoami",
    ":help",
    ":status",
    ":logs",
    ":memory",
    ":mem",
    ":notify",
    ":watch",
    ":threads",
    ":thread",
    ":rename",
    ":branch",
    ":archive",
    ":unarchive",
    ":archived",
    ":delete",
]


def _setup_interactive_completer(project_root: Path | None) -> None:
    if readline is None:
        return
    readline.parse_and_bind("tab: complete")
    readline.set_completer(_InteractiveCompleter(project_root))
    # Keep colon as part of the word so :command completions work
    delims = readline.get_completer_delims().replace(":", "")
    readline.set_completer_delims(delims)


class _InteractiveCompleter:
    def __init__(self, project_root: Path | None) -> None:
        self._project_root = project_root

    def __call__(self, text: str, state: int) -> str | None:
        if readline is None:
            return None
        line = readline.get_line_buffer()
        candidates = self._candidates(line, text)
        if state < len(candidates):
            return candidates[state]
        return None

    def _candidates(self, line: str, text: str) -> list[str]:
        stripped = line.lstrip()
        if stripped.startswith(":thread ") and text and not text.startswith(":"):
            return self._thread_candidates(text)
        if stripped.startswith(":unarchive ") and text and not text.startswith(":"):
            return self._archived_thread_candidates(text)
        if text.startswith(":"):
            return [cmd for cmd in _INTERACTIVE_COMMANDS if cmd.startswith(text)]
        return []

    def _thread_candidates(self, text: str) -> list[str]:
        try:
            threads = ThreadStore(self._project_root).list()
        except Exception:
            return []
        return [t for t in threads if t.startswith(text)]

    def _archived_thread_candidates(self, text: str) -> list[str]:
        try:
            threads = ThreadStore(self._project_root).list_archived()
        except Exception:
            return []
        return [t for t in threads if t.startswith(text)]


def _load_interactive_history(project_root: Path | None) -> Path | None:
    if readline is None:
        return None
    paths = runtime_paths(project_root)
    ensure_runtime_dirs(paths)
    history_path = paths.runtime_dir / "interactive_history"
    readline.clear_history()
    try:
        readline.read_history_file(str(history_path))
    except FileNotFoundError:
        pass
    except OSError:
        _load_plain_interactive_history(history_path)
    _dedupe_interactive_history()
    readline.set_history_length(1000)
    return history_path


def _load_plain_interactive_history(history_path: Path) -> None:
    if readline is None:
        return
    try:
        lines = history_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return
    for line in lines:
        if line != "":
            readline.add_history(line)


def _write_interactive_history(history_path: Path) -> None:
    if readline is None:
        return
    _dedupe_interactive_history()
    history_path.parent.mkdir(parents=True, exist_ok=True)
    readline.write_history_file(str(history_path))


def _remember_interactive_input(message: str) -> None:
    if readline is None:
        return
    history_length = readline.get_current_history_length()
    if history_length > 0 and readline.get_history_item(history_length) == message:
        return
    readline.add_history(message)


def _dedupe_interactive_history() -> None:
    if readline is None:
        return
    history: list[str] = []
    previous: str | None = None
    for index in range(1, readline.get_current_history_length() + 1):
        item = readline.get_history_item(index)
        if item == previous:
            continue
        history.append(item)
        previous = item
    readline.clear_history()
    for item in history:
        readline.add_history(item)


def _send_one_shot_chat(message: str, project_root: Path | None, thread_id: str = "default") -> int:
    try:
        print(_one_shot_reply(message, project_root, thread_id))
        write_log_event(
            "chat",
            "one_shot_chat_completed",
            "one-shot chat turn completed",
            project_root=project_root,
            thread_id=thread_id,
            status="ok",
        )
        _run_memory_curator(project_root)
        return 0
    except RuntimeError as exc:
        write_log_event(
            "chat",
            "one_shot_chat_failed",
            "one-shot chat turn failed",
            project_root=project_root,
            level="error",
            thread_id=thread_id,
            status="error",
            error=str(exc),
        )
        print(str(exc), file=sys.stderr)
        return 1


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
        print(f"[memory] curator failed: {exc}", file=sys.stderr)
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
        print(f"[memory] {result.summary()}")


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


def _handle_interactive_command(command: str, project_root: Path | None, current_thread_id: str) -> tuple[str, str]:
    if command in {":q", ":quit", ":exit"}:
        return ("exit", current_thread_id)
    if command == ":history":
        print()
        print(_handle_interactive_history_command(project_root, current_thread_id))
        print()
        return ("", current_thread_id)
    if command == ":sources":
        print()
        print(_handle_interactive_sources_command(project_root))
        print()
        return ("", current_thread_id)
    if command == ":whoami":
        print()
        print(_handle_interactive_whoami_command(project_root))
        print()
        return ("", current_thread_id)
    if command == ":notify":
        print()
        print(_handle_interactive_notify_command(project_root))
        print()
        return ("", current_thread_id)
    if command == ":watch":
        print()
        _handle_interactive_watch_command(project_root)
        print()
        return ("", current_thread_id)
    if command.startswith(":notify "):
        print()
        parts = command[8:].strip().split(maxsplit=1)
        if not parts:
            print(_interactive_help(":notify"))
        elif parts[0] == "list":
            print(_handle_interactive_notify_list_command(project_root))
        elif parts[0] == "show" and len(parts) == 2:
            print(_handle_interactive_notify_show_command(project_root, parts[1]))
        elif parts[0] == "watch":
            _handle_interactive_watch_command(project_root)
        elif len(parts) == 2:
            subcmd, entry_id = parts[0], parts[1]
            print(_handle_interactive_notify_subcommand(project_root, subcmd, entry_id))
        else:
            print(_interactive_help(":notify"))
        print()
        return ("", current_thread_id)
    if command == ":help":
        print()
        print(_interactive_help())
        print()
        return ("", current_thread_id)
    if command == ":status":
        print()
        print(_format_status(lifecycle.status(project_root)))
        print()
        return ("", current_thread_id)
    if command == ":logs":
        print()
        _print_recent_logs(project_root, limit=8)
        print()
        return ("", current_thread_id)
    if command in {":memory", ":mem"}:
        print()
        print(_format_memory_preview(project_root))
        print()
        return ("", current_thread_id)
    if command.startswith(":mem "):
        print()
        print(_handle_interactive_memory_command(command[5:].strip(), project_root))
        print()
        return ("", current_thread_id)
    if command.startswith(":search "):
        print()
        query = command[8:].strip()
        if query == "":
            print(_interactive_help(":search"))
        else:
            print(_handle_interactive_memory_search(query, project_root))
        print()
        return ("", current_thread_id)
    if command == ":threads":
        print()
        print(_handle_interactive_threads_command(project_root))
        print()
        return ("", current_thread_id)
    if command.startswith(":thread "):
        print()
        new_id = command[8:].strip()
        if new_id == "":
            print(_interactive_help(":thread"))
        else:
            store = ThreadStore(project_root)
            if new_id not in store.list():
                store.save(ThreadState.empty(new_id))
            print(f"Switched to thread: {new_id}")
        print()
        return ("redraw_header", new_id if new_id != "" else current_thread_id)
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
        print()
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
                print()
                return ("", current_thread_id)
        if new_id == "":
            print(_interactive_help(":branch"))
        else:
            try:
                ThreadStore(project_root).branch(current_thread_id, new_id, index)
                print(f"Branched to thread: {new_id}")
            except ValueError as exc:
                print(f"Error: {exc}")
        print()
        return ("redraw_header", new_id if new_id != "" else current_thread_id)
    if command == ":archive":
        print()
        try:
            ThreadStore(project_root).archive(current_thread_id)
            print(f"Archived thread: {current_thread_id}")
        except ValueError as exc:
            print(f"Error: {exc}")
        print()
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
        print()
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
        print()
        return ("", current_thread_id)
    if command == ":delete":
        print()
        try:
            ThreadStore(project_root).delete(current_thread_id)
            print(f"Deleted thread: {current_thread_id}")
        except ValueError as exc:
            print(f"Error: {exc}")
        print()
        return ("redraw_header", "default")
    print()
    print(_interactive_help(command))
    print()
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
            "  :sources   list imported source documents",
            "  :whoami    show core profile",
            "  :notify         list pending notifications",
            "  :notify list    list all notifications",
            "  :notify show <id>  show one notification",
            "  :notify send <id>  send a notification",
            "  :notify dismiss <id>  dismiss a notification",
            "  :watch                   watch outbox for new entries",
            "  :help      show this help",
            "  :status show daemon and thread status",
            "  :logs   show recent activity logs",
            "  :memory preview memory entries",
            "  :mem    preview memory entries",
            "  :search <query>           quick memory search",
            "  :mem search <query>       search memory entries",
            "  :mem show <entry-id>      show one memory entry",
            "  :mem candidates           list pending candidates",
            "  :mem candidate <id>       show one candidate",
            "  :mem profile <query>      search profile items",
            "  :mem sources              list imported sources",
            "  :mem source <source-id>   show one source",
            "  :threads                  list active threads",
            "  :thread <id>              switch to or create a thread",
            "  :rename <new-id>          rename the current thread",
            "  :branch <new-id> [index]  branch current thread at index",
            "  :archive                  archive the current thread",
            "  :unarchive <id>           restore an archived thread",
            "  :archived                 list archived threads",
            "  :delete                   delete the current thread",
        ]
    )
    return "\n".join(lines)


def _one_shot_reply(message: str, project_root: Path | None, thread_id: str = "default") -> str:
    return ChatAgent(project_root).respond(message, thread_id=thread_id).reply


def _log_component_arg(value: object) -> LogComponent | None:
    if value in LOG_COMPONENTS:
        return value
    return None


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
        print(render_log_event(event))


def _print_interactive_activity(project_root: Path | None, event_offset: int) -> None:
    events = read_log_events(project_root=project_root)
    for event in events[event_offset:]:
        print(render_log_event(event))


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
        try:
            entry = MemoryEntryRepository(project_root).get(entry_id)
        except MemoryEntryNotFound:
            return f"Memory entry not found: {entry_id}"
        return render_memory_entry_detail(entry)
    if command == "candidates":
        candidates = MemoryCandidateRepository(project_root).list()
        if not candidates:
            return "No memory candidates."
        return "\n".join(render_candidate_row(candidate) for candidate in candidates)
    if command.startswith("candidate "):
        candidate_id = command.removeprefix("candidate ").strip()
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
            render_source_row(document, chunk_count=len(repo.list_chunks(document.id))) for document in documents
        )
    if command.startswith("source "):
        source_id = command.removeprefix("source ").strip()
        repo = SourceRepository(project_root)
        try:
            document = repo.get_document(source_id)
        except SourceDocumentNotFound:
            return f"Source document not found: {source_id}"
        return render_source_detail(document, chunk_count=len(repo.list_chunks(document.id)))
    return _interactive_memory_help(command)


def _interactive_memory_help(command: str | None = None) -> str:
    lines: list[str] = []
    if command is not None:
        lines.append(f"Unknown memory command: :mem {command}")
    lines.extend(
        [
            "Memory commands:",
            "  :mem search <query>",
            "  :mem show <entry-id>",
            "  :mem candidates",
            "  :mem candidate <candidate-id>",
            "  :mem profile <query>",
            "  :mem sources",
            "  :mem source <source-id>",
            "  :mem why",
        ]
    )
    return "\n".join(lines)


def _handle_interactive_sources_command(project_root: Path | None) -> str:
    from nuself.memory.source_repository import SourceRepository

    repo = SourceRepository(project_root)
    documents = repo.list_documents()
    if not documents:
        return "No imported source documents."
    lines = ["Imported sources:"]
    for doc in documents:
        lines.append(f"  {doc.id}: {doc.title}")
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


def _handle_interactive_notify_command(project_root: Path | None) -> str:
    from nuself.notification import NotificationOutbox
    from nuself.tui.render import render_outbox_summary

    entries = NotificationOutbox(project_root).list(status="pending")
    if not entries:
        return "No pending notifications."
    lines = ["Pending notifications:"]
    for entry in entries:
        lines.append("  " + render_outbox_summary(entry))
    return "\n".join(lines)


def _handle_interactive_notify_list_command(project_root: Path | None) -> str:
    from nuself.notification import NotificationOutbox
    from nuself.tui.render import render_outbox_summary

    entries = NotificationOutbox(project_root).list()
    if not entries:
        return "No notifications."
    lines = ["All notifications:"]
    for entry in entries:
        lines.append("  " + render_outbox_summary(entry))
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
    return f"Unknown :notify subcommand: {subcmd}"


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
                    print(render_outbox_summary(entry))
    except KeyboardInterrupt:
        print("\nStopped watching.")


def _handle_interactive_threads_command(project_root: Path | None) -> str:
    store = ThreadStore(project_root)
    ids = store.list()
    if not ids:
        return "No active threads."
    return "Active threads:\n" + "\n".join(f"  {tid}" for tid in ids)


def _format_status(status: lifecycle.DaemonStatus) -> str:
    state = "running" if status.running else "stopped"
    pid = status.pid if status.pid is not None else "-"
    return f"daemon {state} pid={pid} socket={status.socket_path}"


def _format_daemon_list(status: lifecycle.DaemonStatus) -> str:
    state = "running" if status.running else "stopped"
    pid = status.pid if status.pid is not None else "-"
    return "\n".join(
        [
            "name status pid socket",
            f"local {state} {pid} {status.socket_path}",
        ]
    )



def _format_memory_stats(stats: MemoryStats) -> str:
    lines = [
        f"entries_total: {stats.entries_total}",
        f"candidates_total: {stats.candidates_total}",
        f"pending_candidates: {stats.pending_candidates}",
        f"entries_with_observed_at: {stats.entries_with_observed_at}",
        f"entries_with_evidence: {stats.entries_with_evidence}",
        f"avg_importance: {stats.avg_importance:.2f}",
        f"max_importance: {stats.max_importance:.2f}",
        f"avg_importance_by_type: {_format_float_counts(stats.avg_importance_by_type)}",
        f"entries_by_type: {_format_counts(stats.entries_by_type)}",
        f"entries_by_review_state: {_format_counts(stats.entries_by_review_state)}",
        f"candidates_by_review_state: {_format_counts(stats.candidates_by_review_state)}",
    ]
    return "\n".join(lines)


def _format_memory_relation(record: MemoryRelationIndexRecord) -> str:
    target_title = record.target_title or "(missing target)"
    target_type = record.target_type or "missing"
    return (
        f"{record.source_id} --{record.relation}-> {record.target_id} "
        f"[source={record.source_type}:{record.source_title} "
        f"target={target_type}:{target_title} "
        f"target_exists={record.target_exists} confidence={record.confidence:.2f}]"
    )


def _format_symbolic_graph_node(node: SymbolicGraphNode) -> str:
    return f"{node.id} [{node.kind}:{node.type}] {node.label}"


def _format_symbolic_graph_edge(edge: SymbolicGraphEdge) -> str:
    return f"{edge.id} {edge.source} --{edge.relation}-> {edge.target} confidence={edge.confidence:.2f}"




def _format_source_chunk_summary(chunk: SourceChunk) -> str:
    preview = _compact_text(chunk.text, 96)
    return f"{chunk.source_ref} {chunk.title} chars={len(chunk.text)} {preview}"


def _format_source_chunk_match(match: SourceChunkMatch) -> str:
    chunk = match.chunk
    document = match.document
    preview = _compact_text(chunk.text, 96)
    reasons = ",".join(match.reasons)
    tags = ",".join(document.tags) if document.tags else "-"
    return (
        f"{chunk.source_ref} {document.title} score={match.score:.2f} match={reasons} "
        f"tags={tags} path={document.path} {preview}"
    )


def _privacy_arg(value: object) -> PrivacyLevel:
    if value == "shareable":
        return "shareable"
    return "private"


def _format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "-"
    return ", ".join(f"{key}={counts[key]}" for key in sorted(counts))


def _format_float_counts(counts: dict[str, float]) -> str:
    if not counts:
        return "-"
    return ", ".join(f"{key}={counts[key]:.2f}" for key in sorted(counts))



def _format_memory_preview(project_root: Path | None, limit: int = DEFAULT_MEMORY_PREVIEW_LIMIT) -> str:
    normalized_limit = max(limit, 1)
    entries = MemoryEntryRepository(project_root).list()
    if not entries:
        return "No memory entries."
    shown = entries[:normalized_limit]
    lines: list[str] = []
    for i, entry in enumerate(shown):
        if i > 0:
            lines.append("")
        lines.append(render_memory_entry_row(entry))
        if entry.body:
            lines.extend(f"  {line}" for line in _wrap_body_preview(entry.body))
    lines.append("")
    lines.append(f"  {len(shown)}/{len(entries)} entries shown.")
    if len(entries) > normalized_limit:
        lines.append(f"  Use `nuself memory list` or `nuself memory preview --limit N` to see more.")
    return "\n".join(lines)


def _compact_text(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: max(limit - 3, 0)].rstrip() + "..."


def _wrap_body_preview(body: str, width: int = 88) -> list[str]:
    import shutil
    import textwrap

    cols = shutil.get_terminal_size((width, 24)).columns
    return textwrap.wrap(body, width=max(min(cols, width), 40)) or [""]


def _memory_type_choices() -> list[str]:
    return list(default_memory_type_registry().names())


if __name__ == "__main__":
    raise SystemExit(main())
