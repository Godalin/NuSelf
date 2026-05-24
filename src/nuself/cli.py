"""Command-line interface for NuSelf."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from typing import cast
from uuid import uuid4
import warnings

from prompt_toolkit import HTML
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory
from prompt_toolkit.shortcuts import prompt as _prompt
from prompt_toolkit.styles import Style

_original_warn = warnings.warn

TYPEWRITER_DELAY_SECONDS = 0.01
TYPEWRITER_REFRESH_PER_SECOND = 30
NOTIFICATION_EVAL_FIXTURE_COUNT = 3


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
    from nuself.config import ensure_runtime_dirs, runtime_paths
    from nuself.agent.chat import ChatAgent, ThreadState, ThreadStore
    from nuself.daemon import client, lifecycle
    from nuself.daemon.protocol import JsonValue
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
    from nuself.trace.domain import TRACE_KINDS, TraceKind
    from nuself.trace.repository import TraceNotFound, TraceRepository, TraceVisibilityFilter
    from nuself.trace.service import TraceQueryService, TraceRecorder
    from nuself.logs import (
        LOG_COMPONENTS,
        InteractiveLogCursor,
        LogComponent,
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
        render_profile_detail,
        render_profile_row,
        render_source_detail,
        render_source_row,
    )
    from nuself.reason.service import ReasonService
    from nuself.reason.repository import ReasonNotFound
    from nuself.tui.reason import render_reason_detail, render_reason_row, render_step_watch_entry
    from nuself.tui.render import TerminalTheme, format_display_timestamp, render_log_event, render_log_event_json, render_session_header
    from nuself.tui.trace import render_trace_detail, render_trace_row
    from nuself.persona.prompt_repo import PersonaPromptRepository
    from nuself.persona.definition import BUILTIN_PERSONAS, MODERATOR_PERSONA, SYNTHESIZER_PERSONA
finally:
    warnings.warn = _original_warn

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
    "prompt": "ansicyan bold",
})

_history: FileHistory | None = None
_interactive_completer: _InteractiveCompleter | None = None
_theme = TerminalTheme()


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
                HTML('<style fg="ansicyan" bold>NuSelf&gt; </style>'),
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


@dataclass(frozen=True)
class InteractiveChatResult:
    code: int
    reply: str | None = None
    memory_update: str | None = None
    retryable: bool = False
    error: str | None = None





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
    parser.add_argument("--version", action="version", version=f"nuself {__version__}")
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

    memory_parser = subparsers.add_parser("memory")
    memory_parser.set_defaults(handler=None, help_parser=memory_parser)
    memory_subparsers = memory_parser.add_subparsers(dest="memory_command")
    list_parser = memory_subparsers.add_parser("list")
    list_parser.add_argument("--sort-by", choices=["updated_at", "importance", "type"], default="updated_at")
    list_parser.add_argument("--review-state", choices=["draft", "reviewed", "rejected", "quarantined", "archived"], default=None)
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
    edit_parser.add_argument("--review-state", choices=["draft", "reviewed", "rejected", "quarantined", "archived"], default=None)
    _add_handler(edit_parser, handle_memory_edit)
    delete_parser = memory_subparsers.add_parser("delete")
    delete_parser.add_argument("entry_id")
    _add_handler(delete_parser, handle_memory_delete)
    search_parser = memory_subparsers.add_parser("search")
    search_parser.add_argument("query", nargs="?", default="")
    search_parser.add_argument("--type", choices=_memory_type_choices(), default=None)
    search_parser.add_argument("--tag", default=None)
    search_parser.add_argument("--review-state", choices=["draft", "reviewed", "rejected", "quarantined", "archived"], default=None)
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
    source_parser = memory_subparsers.add_parser("source")
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
    candidate_parser = memory_subparsers.add_parser("review")
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

    thread_parser = subparsers.add_parser("thread")
    thread_parser.set_defaults(handler=None, help_parser=thread_parser)
    thread_subparsers = thread_parser.add_subparsers(dest="thread_command")
    _add_handler(thread_subparsers.add_parser("list"), handle_thread_list)
    thread_show_parser = thread_subparsers.add_parser("show")
    thread_show_parser.add_argument("thread_id")
    _add_handler(thread_show_parser, handle_thread_show)
    thread_create_parser = thread_subparsers.add_parser("new")
    thread_create_parser.add_argument("thread_id")
    _add_handler(thread_create_parser, handle_thread_create)
    thread_open_parser = thread_subparsers.add_parser("open")
    thread_open_parser.add_argument("thread_id", nargs="?", default=None)
    thread_open_parser.add_argument("--message", "-m", default=None)
    thread_open_parser.add_argument("--create", action="store_true")
    thread_open_parser.add_argument("--deep-link", default=None)
    _add_handler(thread_open_parser, handle_open)
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

    inbox_parser = subparsers.add_parser("inbox")
    inbox_parser.set_defaults(handler=None, help_parser=inbox_parser)
    inbox_subparsers = inbox_parser.add_subparsers(dest="inbox_command")
    reflection_parser = inbox_subparsers.add_parser("reflection")
    reflection_parser.set_defaults(handler=None, help_parser=reflection_parser)
    reflection_subparsers = reflection_parser.add_subparsers(dest="reflection_command")
    reflection_list_parser = reflection_subparsers.add_parser("list")
    reflection_list_parser.add_argument("--tail", type=int, default=20)
    reflection_list_parser.add_argument("--status", choices=["pending", "dismissed", "archived"], default=None)
    reflection_list_parser.add_argument("--json", action="store_true", default=False, dest="as_json")
    _add_handler(reflection_list_parser, handle_reflection_list)
    reflection_show_parser = reflection_subparsers.add_parser("show")
    reflection_show_parser.add_argument("entry_id")
    reflection_show_parser.add_argument("--by-index", "-i", action="store_true", default=False, help="Treat entry_id as a 0-based index from 'reflection list'")
    reflection_show_parser.add_argument("--json", action="store_true", default=False, dest="as_json")
    _add_handler(reflection_show_parser, handle_reflection_show)
    reflection_dismiss_parser = reflection_subparsers.add_parser("dismiss")
    reflection_dismiss_parser.add_argument("entry_id")
    reflection_dismiss_parser.add_argument("--by-index", "-i", action="store_true", default=False, help="Treat entry_id as a 0-based index from 'reflection list'")
    _add_handler(reflection_dismiss_parser, handle_reflection_dismiss)
    reflection_archive_parser = reflection_subparsers.add_parser("archive")
    reflection_archive_parser.add_argument("entry_id")
    reflection_archive_parser.add_argument("--by-index", "-i", action="store_true", default=False, help="Treat entry_id as a 0-based index from 'reflection list'")
    _add_handler(reflection_archive_parser, handle_reflection_archive)
    reflection_promote_parser = reflection_subparsers.add_parser("promote")
    reflection_promote_parser.add_argument("entry_id")
    reflection_promote_parser.add_argument("--by-index", "-i", action="store_true", default=False, help="Treat entry_id as a 0-based index from 'reflection list'")
    _add_handler(reflection_promote_parser, handle_reflection_promote)
    _add_handler(reflection_subparsers.add_parser("organize"), handle_reflection_organize)

    notify_parser = inbox_subparsers.add_parser("notify")
    notify_parser.set_defaults(handler=None, help_parser=notify_parser)
    notify_subparsers = notify_parser.add_subparsers(dest="notify_command")
    notify_list_parser = notify_subparsers.add_parser("list")
    notify_list_parser.add_argument("--status", choices=["pending", "sent", "failed", "dismissed"], default=None)
    _add_handler(notify_list_parser, handle_notify_list)
    notify_show_parser = notify_subparsers.add_parser("show")
    notify_show_parser.add_argument("entry_id")
    notify_show_parser.add_argument("--by-index", "-i", action="store_true", default=False, help="Treat entry_id as a 0-based index from 'notify list'")
    _add_handler(notify_show_parser, handle_notify_show)
    notify_send_parser = notify_subparsers.add_parser("send")
    notify_send_parser.add_argument("entry_id")
    notify_send_parser.add_argument("--by-index", "-i", action="store_true", default=False, help="Treat entry_id as a 0-based index from 'notify list'")
    _add_handler(notify_send_parser, handle_notify_send)
    notify_dismiss_parser = notify_subparsers.add_parser("dismiss")
    notify_dismiss_parser.add_argument("entry_id")
    notify_dismiss_parser.add_argument("--by-index", "-i", action="store_true", default=False, help="Treat entry_id as a 0-based index from 'notify list'")
    _add_handler(notify_dismiss_parser, handle_notify_dismiss)
    _add_handler(notify_subparsers.add_parser("stats"), handle_notify_stats)
    notify_watch_parser = notify_subparsers.add_parser("watch")
    notify_watch_parser.add_argument("--interval", type=int, default=5, help="Poll interval in seconds")
    _add_handler(notify_watch_parser, handle_notify_watch)
    _add_handler(notify_subparsers.add_parser("clear"), handle_notify_clear)

    reason_parser = subparsers.add_parser("reason")
    reason_parser.set_defaults(handler=None, help_parser=reason_parser)
    reason_subparsers = reason_parser.add_subparsers(dest="reason_command")
    reason_list_parser = reason_subparsers.add_parser("list")
    reason_list_parser.add_argument("--status", choices=("active", "paused", "resolved", "archived", "all"), default=None)
    reason_list_parser.add_argument("--json", action="store_true", default=False, dest="as_json")
    _add_handler(reason_list_parser, handle_reason_list)
    reason_show_parser = reason_subparsers.add_parser("show")
    reason_show_parser.add_argument("thread_id")
    reason_show_parser.add_argument("--by-index", "-i", action="store_true", default=False)
    reason_show_parser.add_argument("--full", "-f", action="store_true", default=False)
    reason_show_parser.add_argument("--json", action="store_true", default=False, dest="as_json")
    _add_handler(reason_show_parser, handle_reason_show)
    reason_watch_parser = reason_subparsers.add_parser("watch")
    reason_watch_parser.add_argument("thread_id")
    reason_watch_parser.add_argument("--by-index", "-i", action="store_true", default=False)
    reason_watch_parser.add_argument("--full", "-f", action="store_true", default=False)
    reason_watch_parser.add_argument("--interval", type=float, default=5.0)
    _add_handler(reason_watch_parser, handle_reason_watch)
    reason_start_parser = reason_subparsers.add_parser("start")
    reason_start_parser.add_argument("question")
    reason_start_parser.add_argument("--priority", choices=("normal", "high"), default="normal")
    _add_handler(reason_start_parser, handle_reason_start)
    for action_name in _REASON_VERBS:
        p = reason_subparsers.add_parser(action_name)
        p.add_argument("thread_id")
        p.add_argument("--by-index", "-i", action="store_true", default=False)
        p.set_defaults(action=action_name)
        _add_handler(p, handle_reason_thread_action)
    reason_delete_parser = reason_subparsers.add_parser("delete")
    reason_delete_parser.add_argument("thread_id")
    reason_delete_parser.add_argument("--by-index", "-i", action="store_true", default=False)
    reason_delete_parser.add_argument("--yes", "-y", action="store_true", default=False)
    _add_handler(reason_delete_parser, handle_reason_delete)
    trace_parser = subparsers.add_parser("trace")
    trace_parser.set_defaults(handler=None, help_parser=trace_parser)
    trace_subparsers = trace_parser.add_subparsers(dest="trace_command")
    trace_list_parser = trace_subparsers.add_parser("list")
    trace_list_parser.add_argument("--kind", choices=TRACE_KINDS, default=None)
    trace_list_parser.add_argument("--visibility", choices=("private", "shareable", "internal", "all"), default=None)
    trace_list_parser.add_argument("--json", action="store_true", default=False, dest="as_json")
    _add_handler(trace_list_parser, handle_trace_list)
    trace_show_parser = trace_subparsers.add_parser("show")
    trace_show_parser.add_argument("trace_id")
    trace_show_parser.add_argument("--by-index", "-i", action="store_true", default=False)
    trace_show_parser.add_argument("--json", action="store_true", default=False, dest="as_json")
    _add_handler(trace_show_parser, handle_trace_show)
    trace_search_parser = trace_subparsers.add_parser("search")
    trace_search_parser.add_argument("query")
    trace_search_parser.add_argument("--kind", choices=TRACE_KINDS, default=None)
    trace_search_parser.add_argument("--visibility", choices=("private", "shareable", "internal", "all"), default=None)
    trace_search_parser.add_argument("--json", action="store_true", default=False, dest="as_json")
    _add_handler(trace_search_parser, handle_trace_search)
    _add_handler(trace_subparsers.add_parser("reindex"), handle_trace_reindex)

    persona_parser = subparsers.add_parser("persona")
    persona_parser.set_defaults(handler=None, help_parser=persona_parser)
    persona_subparsers = persona_parser.add_subparsers(dest="persona_command")
    _add_handler(persona_subparsers.add_parser("list"), handle_persona_list)
    persona_show_parser = persona_subparsers.add_parser("show")
    persona_show_parser.add_argument("name_or_id")
    _add_handler(persona_show_parser, handle_persona_show)
    persona_delete_parser = persona_subparsers.add_parser("delete")
    persona_delete_parser.add_argument("name_or_id")
    persona_delete_parser.add_argument("--yes", "-y", action="store_true", default=False)
    _add_handler(persona_delete_parser, handle_persona_delete)

    dev_parser = subparsers.add_parser("dev")
    dev_parser.set_defaults(handler=None, help_parser=dev_parser)
    dev_subparsers = dev_parser.add_subparsers(dest="dev_command")
    _add_handler(dev_subparsers.add_parser("status"), handle_status)
    _add_handler(dev_subparsers.add_parser("health"), handle_health)
    _add_handler(dev_subparsers.add_parser("config"), handle_config)
    dev_logs_parser = dev_subparsers.add_parser("logs")
    _add_log_arguments(dev_logs_parser)
    _add_handler(dev_logs_parser, handle_logs)
    dev_eval_parser = dev_subparsers.add_parser("eval")
    dev_eval_parser.add_argument("--fixtures", type=Path, default=None)
    dev_eval_parser.add_argument("--component", choices=["conversations", "notifications", "all"], default="all")
    _add_handler(dev_eval_parser, handle_eval)

    return parser


def _add_handler(parser: argparse.ArgumentParser, handler: object) -> None:
    parser.set_defaults(handler=handler)


def _print_json_wire(*entities: object) -> None:
    """Print one or more to_wire() dicts as compact JSON lines."""
    import json
    for entity in entities:
        print(json.dumps(entity, sort_keys=True, ensure_ascii=True))


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
    _record_cli_memory_trace(args.project_root, entry, "add")
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
        review_state=args.review_state,
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
            all_passed += NOTIFICATION_EVAL_FIXTURE_COUNT
            all_total += NOTIFICATION_EVAL_FIXTURE_COUNT
        else:
            all_total += NOTIFICATION_EVAL_FIXTURE_COUNT
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


def _resolve_notify_entry_id(args: argparse.Namespace) -> str | None:
    """Resolve entry_id to actual entry id, supporting --by-index lookup."""
    from nuself.notification import NotificationOutbox

    if not getattr(args, "by_index", False):
        return args.entry_id
    outbox = NotificationOutbox(args.project_root)
    entries = outbox.list()
    try:
        idx = int(args.entry_id)
    except ValueError:
        print(f"Invalid index: {args.entry_id}", file=sys.stderr)
        return None
    if idx < 0 or idx >= len(entries):
        print(f"Invalid index {idx}. Valid range: 0-{len(entries) - 1}", file=sys.stderr)
        return None
    return entries[idx].id


def handle_notify_show(args: argparse.Namespace) -> int:
    from nuself.notification import NotificationOutbox, OutboxEntryNotFound
    from nuself.tui.render import render_outbox_detail

    entry_id = _resolve_notify_entry_id(args)
    if entry_id is None:
        return 1
    try:
        entry = NotificationOutbox(args.project_root).get(entry_id)
    except OutboxEntryNotFound:
        print(f"Outbox entry not found: {entry_id}", file=sys.stderr)
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

    entry_id = _resolve_notify_entry_id(args)
    if entry_id is None:
        return 1
    outbox = NotificationOutbox(args.project_root)
    try:
        entry = outbox.get(entry_id)
    except OutboxEntryNotFound:
        print(f"Outbox entry not found: {entry_id}", file=sys.stderr)
        return 1
    adapter = LogOnlyNotificationAdapter(args.project_root)
    if adapter.send(entry):
        outbox.mark_sent(entry_id)
        print(f"Sent: {entry.id}")
        return 0
    outbox.mark_failed(entry_id)
    print(f"Failed to send: {entry.id}", file=sys.stderr)
    return 1


def handle_notify_dismiss(args: argparse.Namespace) -> int:
    from nuself.notification import NotificationOutbox, OutboxEntryNotFound

    entry_id = _resolve_notify_entry_id(args)
    if entry_id is None:
        return 1
    try:
        NotificationOutbox(args.project_root).dismiss(entry_id)
        print(f"Dismissed: {entry_id}")
        return 0
    except OutboxEntryNotFound:
        print(f"Outbox entry not found: {entry_id}", file=sys.stderr)
        return 1


def handle_notify_clear(args: argparse.Namespace) -> int:
    from nuself.notification import NotificationOutbox

    count = NotificationOutbox(args.project_root).clear("dismissed")
    print(f"Cleared {count} dismissed notification(s).")
    return 0


# ── Reason handlers ───────────────────────────────────────────────────


def handle_reason_list(args: argparse.Namespace) -> int:
    service = ReasonService(args.project_root)
    threads = service.list_threads(status=args.status)
    if not threads:
        print("No reason threads.")
        return 0
    if args.as_json:
        _print_json_wire(*(thread.to_wire() for thread in threads))
        return 0
    for index, thread in enumerate(threads, start=1):
        print(render_reason_row(thread, index=index))
    return 0


def handle_reason_show(args: argparse.Namespace) -> int:
    service = ReasonService(args.project_root)
    try:
        thread = service.show_thread(args.thread_id, by_index=args.by_index)
    except ReasonNotFound:
        print(f"Reason thread not found: {args.thread_id}", file=sys.stderr)
        return 1
    steps = service.list_steps(thread.id)
    if args.as_json:
        payload = thread.to_wire()
        payload["steps"] = [step.to_wire() for step in steps]
        _print_json_wire(payload)
        return 0
    print(render_reason_detail(thread, steps, full=bool(getattr(args, "full", False))))
    return 0


def handle_reason_watch(args: argparse.Namespace) -> int:
    service = ReasonService(args.project_root)
    try:
        thread = service.show_thread(args.thread_id, by_index=args.by_index)
    except ReasonNotFound:
        print(f"Reason thread not found: {args.thread_id}", file=sys.stderr)
        return 1
    steps = service.list_steps(thread.id)
    full = bool(getattr(args, "full", False))
    print(render_reason_detail(thread, steps, full=full))
    seen = len(steps)
    try:
        while True:
            time.sleep(args.interval)
            steps = service.list_steps(thread.id)
            if len(steps) > seen:
                for step in steps[seen:]:
                    print(render_step_watch_entry(step))
                seen = len(steps)
    except KeyboardInterrupt:
        return 0


def handle_reason_start(args: argparse.Namespace) -> int:
    service = ReasonService(args.project_root)
    try:
        thread = service.start_thread(args.question, priority=args.priority)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Started reasoning thread: {thread.id}")
    print(render_reason_detail(thread))
    return 0


_REASON_VERBS: dict[str, tuple[str, str]] = {
    "advance": ("Advanced", "advance_thread"),
    "pause": ("Paused", "pause_thread"),
    "resume": ("Resumed", "resume_thread"),
    "resolve": ("Resolved", "resolve_thread"),
    "archive": ("Archived", "archive_thread"),
}


def handle_reason_thread_action(args: argparse.Namespace) -> int:
    verb, method_name = _REASON_VERBS[args.action]
    method = getattr(ReasonService(args.project_root), method_name)
    try:
        thread = method(args.thread_id, by_index=args.by_index)
    except (ReasonNotFound, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"{verb} reason thread: {thread.id}")
    print(render_reason_detail(thread))
    return 0


def handle_reason_delete(args: argparse.Namespace) -> int:
    if not bool(getattr(args, "yes", False)):
        print("Use --yes to confirm deletion.", file=sys.stderr)
        return 1
    service = ReasonService(args.project_root)
    try:
        tid = service.delete_thread(args.thread_id, by_index=args.by_index)
    except (ReasonNotFound, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Deleted reason thread: {tid}")
    return 0


def handle_trace_list(args: argparse.Namespace) -> int:
    service = TraceQueryService(args.project_root)
    traces = service.list_traces(
        kind=_optional_trace_kind(args.kind),
        visibility=_trace_visibility_filter(args.visibility),
    )
    if not traces:
        print("No trace records.")
        return 0
    if args.as_json:
        _print_json_wire(*(trace.to_wire() for trace in traces))
        return 0
    for index, trace in enumerate(traces, start=1):
        print(render_trace_row(trace, index=index))
    return 0


def handle_trace_show(args: argparse.Namespace) -> int:
    repository = TraceRepository(args.project_root)
    try:
        trace = repository.resolve_trace(args.trace_id, by_index=args.by_index)
    except TraceNotFound:
        print(f"Trace not found: {args.trace_id}", file=sys.stderr)
        return 1
    if args.as_json:
        payload = trace.to_wire()
        payload["links"] = [link.to_wire() for link in repository.links_for(trace.id)]
        _print_json_wire(payload)
        return 0
    print(render_trace_detail(trace, repository.links_for(trace.id)))
    return 0


def handle_trace_search(args: argparse.Namespace) -> int:
    service = TraceQueryService(args.project_root)
    traces = service.search_traces(
        args.query,
        kind=_optional_trace_kind(args.kind),
        visibility=_trace_visibility_filter(args.visibility),
    )
    if not traces:
        print("No matching trace records.")
        return 0
    if args.as_json:
        _print_json_wire(*(trace.to_wire() for trace in traces))
        return 0
    for index, trace in enumerate(traces, start=1):
        print(render_trace_row(trace, index=index))
    return 0


def handle_trace_reindex(args: argparse.Namespace) -> int:
    path = TraceRepository(args.project_root).reindex()
    print(f"Rebuilt trace index: {path}")
    return 0


def _optional_trace_kind(value: str | None) -> TraceKind | None:
    if value is None:
        return None
    return value if value in TRACE_KINDS else None


def _trace_visibility_filter(value: str | None) -> TraceVisibilityFilter:
    if value in {"private", "shareable", "internal", "all"}:
        return cast(TraceVisibilityFilter, value)
    return "default"


def _resolve_reflection_entry_id(args: argparse.Namespace) -> str | None:
    """Resolve entry_id to actual reflection id, supporting --by-index lookup."""
    from nuself.reflection.repository import ReflectionRepository

    if not getattr(args, "by_index", False):
        return args.entry_id
    repo = ReflectionRepository(args.project_root)
    entries = repo.list()
    try:
        idx = int(args.entry_id)
    except ValueError:
        print(f"Invalid index: {args.entry_id}", file=sys.stderr)
        return None
    if idx < 0 or idx >= len(entries):
        print(f"Invalid index {idx}. Valid range: 0-{len(entries) - 1}", file=sys.stderr)
        return None
    return entries[idx].id


def handle_reflection_list(args: argparse.Namespace) -> int:
    from nuself.reflection.repository import ReflectionRepository
    from nuself.tui.render import render_reflection_entry_summary

    repo = ReflectionRepository(args.project_root)
    entries = repo.list(status=args.status)
    if not entries:
        filter_msg = f" with status '{args.status}'" if args.status else ""
        print(f"No reflection entries{filter_msg}.")
        return 0
    if args.as_json:
        _print_json_wire(*(entry.to_wire() for entry in entries))
        return 0
    for idx, entry in enumerate(entries):
        print(render_reflection_entry_summary(entry, index=idx))
    return 0


def handle_reflection_show(args: argparse.Namespace) -> int:
    from nuself.reflection.repository import ReflectionEntryNotFound, ReflectionRepository
    from nuself.tui.render import render_reflection_entry_detail

    entry_id = _resolve_reflection_entry_id(args)
    if entry_id is None:
        return 1
    try:
        entry = ReflectionRepository(args.project_root).get(entry_id)
    except ReflectionEntryNotFound:
        print(f"Reflection entry not found: {entry_id}", file=sys.stderr)
        return 1
    if args.as_json:
        _print_json_wire(entry.to_wire())
        return 0
    print(render_reflection_entry_detail(entry))
    return 0


def handle_reflection_dismiss(args: argparse.Namespace) -> int:
    from nuself.reflection.repository import ReflectionEntryNotFound, ReflectionRepository

    entry_id = _resolve_reflection_entry_id(args)
    if entry_id is None:
        return 1
    try:
        ReflectionRepository(args.project_root).dismiss(entry_id)
        print(f"Dismissed: {entry_id}")
        return 0
    except ReflectionEntryNotFound:
        print(f"Reflection entry not found: {entry_id}", file=sys.stderr)
        return 1


def handle_reflection_archive(args: argparse.Namespace) -> int:
    from nuself.reflection.repository import ReflectionEntryNotFound, ReflectionRepository

    entry_id = _resolve_reflection_entry_id(args)
    if entry_id is None:
        return 1
    try:
        ReflectionRepository(args.project_root).archive(entry_id)
        print(f"Archived: {entry_id}")
        return 0
    except ReflectionEntryNotFound:
        print(f"Reflection entry not found: {entry_id}", file=sys.stderr)
        return 1


def handle_reflection_promote(args: argparse.Namespace) -> int:
    from nuself.reflection.repository import ReflectionEntryNotFound
    from nuself.reflection.service import ReflectionService

    try:
        thread = ReflectionService(args.project_root).promote_to_reason(args.entry_id, by_index=args.by_index)
    except (ReflectionEntryNotFound, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Promoted reflection to reason thread: {thread.id}")
    print(render_reason_detail(thread))
    return 0


def handle_reflection_organize(args: argparse.Namespace) -> int:
    from nuself.reflection.organizer import ReflectionOrganizer

    result = ReflectionOrganizer(args.project_root).organize_pending()
    print(
        "Organized reflections: "
        f"merged_groups={result.merged_groups} archived_entries={result.archived_entries}"
    )
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
        _record_cli_memory_trace(args.project_root, entry, "import")
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
        print(f"{len(pending)} pending candidate(s). Accept: nuself memory review accept <id>")
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
    _record_cli_memory_trace(args.project_root, entry, "accept")
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
    _record_cli_memory_trace(args.project_root, entry, "merge")
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


def handle_persona_list(args: argparse.Namespace) -> int:
    static = list(BUILTIN_PERSONAS) + [MODERATOR_PERSONA, SYNTHESIZER_PERSONA]
    print("Built-in personas (static):")
    for p in static:
        print(f"  {p.id}: {p.description}")
    prompts = PersonaPromptRepository(args.project_root).list()
    if prompts:
        print()
        print("Custom personas (dynamic):")
        for p in prompts:
            print(f"  {p.name} (id={p.id})")
    else:
        print("  (no custom personas yet — use persona_craft in chat to create one)")
    return 0


def handle_persona_show(args: argparse.Namespace) -> int:
    repo = PersonaPromptRepository(args.project_root)
    prompt = repo.resolve(args.name_or_id)
    if prompt is None:
        print(f"Persona not found: {args.name_or_id}", file=sys.stderr)
        return 1
    print(f"Name: {prompt.name}")
    print(f"ID:   {prompt.id}")
    print(f"Created: {prompt.created_at}")
    print(f"Updated: {prompt.updated_at}")
    print("---")
    print(prompt.prompt)
    return 0


def handle_persona_delete(args: argparse.Namespace) -> int:
    repo = PersonaPromptRepository(args.project_root)
    prompt = repo.resolve(args.name_or_id)
    if prompt is None:
        print(f"Persona not found: {args.name_or_id}", file=sys.stderr)
        return 1
    if not args.yes:
        confirm = input(f"Delete persona '{prompt.name}'? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return 0
    repo.delete(prompt.id)
    print(f"Deleted persona: {prompt.name}")
    return 0


def _send_chat(message: str, project_root: Path | None, thread_id: str = "default") -> int:
    result = _send_chat_interactive(message, project_root, thread_id)
    if result.reply is not None:
        _print_assistant_reply(result.reply)
    if result.memory_update is not None:
        theme = TerminalTheme()
        print(f"{theme.tag('[memory]', 'memory')} {result.memory_update}")
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
    print(render_session_header(daemon_status=_interactive_daemon_status(project_root), thread_id=current_thread_id))
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
                _auto_save_interactive_transcripts(project_root, session)
                return 130
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
                    print(render_session_header(daemon_status=_interactive_daemon_status(project_root), thread_id=current_thread_id))
                continue
            result = _send_interactive_chat_turn(
                send_message,
                project_root,
                current_thread_id,
                message,
                session,
            )
            print(render_session_header(daemon_status=_interactive_daemon_status(project_root), thread_id=current_thread_id))
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
                print(_theme.paint("Logs:", "93"))
                printed_logs = True
            print(f"{_theme.tag('[memory]', 'memory')} {result.memory_update}")
        if result.reply is not None:
            print()
            print(_theme.paint("NuSelf:", "96"))
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
    while send_thread.is_alive():
        time.sleep(INTERACTIVE_LOG_POLL_INTERVAL_SECONDS)
        new_events = _interactive_activity_events(project_root, log_cursor, turn_id=turn_id)
        if new_events:
            captured_events.extend(new_events)
            printed_logs = _print_visible_interactive_activity_events(new_events, printed_logs=printed_logs)
    send_thread.join()
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
        print(_theme.paint("Logs:", "93"))
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


def _setup_interactive_completer(project_root: Path | None) -> None:
    if readline is None:
        return
    readline.parse_and_bind("tab: complete")
    readline.set_completer(_InteractiveCompleter(project_root))
    # Keep colon as part of the word so :command completions work
    delims = readline.get_completer_delims().replace(":", "")
    readline.set_completer_delims(delims)


class _InteractiveCompleter(Completer):
    def __init__(self, project_root: Path | None) -> None:
        super().__init__()
        self._project_root = project_root

    def get_completions(self, document: Document, complete_event: object) -> Completion:
        text = document.text_before_cursor
        stripped = text.lstrip()
        word = text.split()[-1] if text.split() else ""

        if (stripped.startswith(":thread ") or stripped.startswith(":t ")) and word and not word.startswith(":"):
            yield from self._thread_completions(word)
            return
        if stripped.startswith(":unarchive ") and word and not word.startswith(":"):
            yield from self._archived_thread_completions(word)
            return
        if word.startswith(":"):
            for cmd in _INTERACTIVE_COMMANDS:
                if cmd.startswith(word):
                    yield Completion(cmd, start_position=-len(word))

    def _thread_completions(self, word: str) -> Completion:
        try:
            threads = ThreadStore(self._project_root).list()
        except Exception:
            return
        for t in threads:
            if t.startswith(word):
                yield Completion(t, start_position=-len(word))

    def _archived_thread_completions(self, word: str) -> Completion:
        try:
            threads = ThreadStore(self._project_root).list_archived()
        except Exception:
            return
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
        _theme = TerminalTheme()
        print(f"{_theme.tag('[memory]', 'memory')} curator failed: {exc}", file=sys.stderr)
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
        _theme = TerminalTheme()
        print(f"{_theme.tag('[memory]', 'memory')} {result.summary()}")


def _record_cli_memory_trace(project_root: Path | None, entry: MemoryEntry, action: str) -> None:
    try:
        TraceRecorder(project_root=project_root).record_memory_update(
            memory_id=entry.id,
            title=entry.title,
            summary=entry.body,
            memory_type=entry.type,
            action=action,
            confidence=entry.confidence,
        )
    except Exception:
        pass


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
        print(_handle_interactive_history_command(project_root, current_thread_id))
        return ("", current_thread_id)
    if command == ":whoami":
        print()
        print(_handle_interactive_whoami_command(project_root))
        return ("", current_thread_id)
    if command in {":inbox", ":i"}:
        print()
        print(_handle_interactive_inbox_command(project_root))
        return ("", current_thread_id)
    if command.startswith(":inbox reflection ") or command.startswith(":i reflection "):
        print()
        body = command.removeprefix(":inbox reflection").removeprefix(":i reflection").strip()
        parts = body.split(maxsplit=1)
        if not parts:
            print(_interactive_help(":inbox reflection"))
        elif parts[0] == "list":
            print(_handle_interactive_reflection_list_command(project_root))
        elif parts[0] == "show" and len(parts) == 2:
            print(_handle_interactive_reflection_show_command(project_root, parts[1]))
        elif len(parts) == 2:
            subcmd, entry_id = parts[0], parts[1]
            print(_handle_interactive_reflection_subcommand(project_root, subcmd, entry_id))
        else:
            print(_interactive_help(":inbox reflection"))
        return ("", current_thread_id)
    if command in {":inbox reflection", ":i reflection"}:
        print()
        print(_handle_interactive_reflection_command(project_root))
        return ("", current_thread_id)
    if command.startswith(":inbox notify ") or command.startswith(":i notify "):
        print()
        body = command.removeprefix(":inbox notify").removeprefix(":i notify").strip()
        parts = body.split(maxsplit=1)
        if not parts:
            print(_interactive_help(":inbox notify"))
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
            print(_interactive_help(":inbox notify"))
        return ("", current_thread_id)
    if command in {":inbox notify", ":i notify"}:
        print()
        print(_handle_interactive_notify_command(project_root))
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
        print(_handle_interactive_export_command(command, project_root, current_thread_id, session))
        return ("", current_thread_id)
    if command in {":mem", ":m"}:
        print()
        print(_format_memory_preview(project_root))
        return ("", current_thread_id)
    if command.startswith(":mem ") or command.startswith(":m "):
        print()
        body = command.removeprefix(":mem").removeprefix(":m").strip()
        print(_handle_interactive_memory_command(body, project_root))
        return ("", current_thread_id)
    if command in {":thread", ":t"}:
        print()
        print(_handle_interactive_threads_command(project_root))
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
    if command.startswith(":reason"):
        print()
        body = command.removeprefix(":reason").strip()
        print(_handle_interactive_reason_command(body, project_root))
        return ("", current_thread_id)
    if command.startswith(":trace"):
        print()
        body = command.removeprefix(":trace").strip()
        print(_handle_interactive_trace_command(body, project_root))
        return ("", current_thread_id)
    if command in {":restart", ":r"}:
        print()
        print(_handle_interactive_restart_command(project_root))
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
        print(render_log_event(event))


def _visible_interactive_activity_events(events: list[LogEvent]) -> list[LogEvent]:
    return [event for event in events if _is_interactive_activity_log(event)]


def _is_interactive_activity_log(event: LogEvent) -> bool:
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


def _export_interactive_transcript(
    project_root: Path | None,
    *,
    thread_id: str,
    start_index: int,
    connected_at: datetime,
    exported_at: datetime,
    messages: list[tuple[int, str, str]] | None = None,
    log_events: list[LogEvent] | None = None,
    log_events_by_message: dict[int, list[LogEvent]] | None = None,
    include_all_logs: bool = False,
) -> tuple[Path, str]:
    paths = runtime_paths(project_root)
    if messages is None:
        thread = ThreadStore(project_root).load(thread_id)
        messages = _thread_messages_from_index(thread, start_index)
    if not messages:
        raise ValueError("no chat messages in this connection yet")

    export_dir = paths.private_root / "transcripts"
    export_dir.mkdir(parents=True, exist_ok=True)
    filename = (
        f"chat-{_safe_filename_component(thread_id)}-"
        f"{_compact_timestamp(connected_at)}-{_compact_timestamp(exported_at)}.md"
    )
    path = export_dir / filename
    content = _render_chat_transcript(
        thread_id=thread_id,
        connected_at=connected_at,
        exported_at=exported_at,
        messages=messages,
        log_events=log_events or [],
        log_events_by_message=log_events_by_message or {},
        include_all_logs=include_all_logs,
    )
    path.write_text(content, encoding="utf-8")
    return path, content


def _thread_messages_from_index(thread: ThreadState, start_index: int) -> list[tuple[int, str, str]]:
    messages: list[tuple[int, str, str]] = []
    for offset, message in enumerate(thread.messages):
        index = thread.message_start_index + offset
        if index >= start_index:
            messages.append((index, message.role, message.content))
    return messages


def _render_chat_transcript(
    *,
    thread_id: str,
    connected_at: datetime,
    exported_at: datetime,
    messages: list[tuple[int, str, str]],
    log_events: list[LogEvent],
    log_events_by_message: dict[int, list[LogEvent]],
    include_all_logs: bool,
) -> str:
    lines = [
        "# NuSelf Chat Transcript",
        "",
        f"- Thread: `{thread_id}`",
        f"- Connected: {format_display_timestamp(connected_at)}",
        f"- Exported: {format_display_timestamp(exported_at)}",
        f"- Logs: {'all' if include_all_logs else 'share'}",
        "",
    ]
    for index, role, content in messages:
        label = "User" if role == "user" else "NuSelf"
        lines.extend([
            f"## {index}. {label}",
            "",
            _normalize_transcript_body(content),
            "",
        ])
        message_log_events = log_events_by_message.get(index, [])
        if message_log_events:
            lines.extend(["### Logs", ""])
            for event in message_log_events:
                lines.extend(_render_transcript_log_event(event))
                lines.append("")
    if log_events:
        lines.extend(["## Internal Process Logs", ""])
        for event in log_events:
            lines.extend(_render_transcript_log_event(event))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_transcript_log_event(event: LogEvent) -> list[str]:
    return [f"> {line}" if line else ">" for line in render_log_event(event, color=False).splitlines()]


def _normalize_transcript_body(content: str) -> str:
    body = content.strip()
    if body == "":
        return "_(empty)_"
    return _escape_markdown_fences(body)


def _escape_markdown_fences(text: str) -> str:
    lines = text.splitlines()
    longest_backtick_run = 0
    for line in lines:
        stripped = line.lstrip()
        if not stripped.startswith("```"):
            continue
        run = len(stripped) - len(stripped.lstrip("`"))
        longest_backtick_run = max(longest_backtick_run, run)
    if longest_backtick_run == 0:
        return text
    fence = "`" * (longest_backtick_run + 1)
    normalized_lines: list[str] = []
    for line in lines:
        leading_width = len(line) - len(line.lstrip())
        leading = line[:leading_width]
        stripped = line[leading_width:]
        if stripped.startswith("`" * longest_backtick_run):
            normalized_lines.append(f"{leading}{fence}{stripped[longest_backtick_run:]}")
        else:
            normalized_lines.append(line)
    return "\n".join(normalized_lines)


def _is_shareable_transcript_log(event: LogEvent) -> bool:
    if event.component == "chat" and event.event == "service_tool_called":
        return True
    if event.component == "persona":
        return event.event in {
            "persona_summary",
            "host_discussion_decision",
            "persona_discussion",
            "persona_discussion_step",
        }
    if event.component == "reflection":
        return event.event in {"persona_discussion", "cycle_completed", "cycle_discussion_rejected"}
    return False


def _copy_text_to_clipboard(text: str) -> tuple[bool, str]:
    command = _clipboard_command()
    if command is None:
        return False, "no supported clipboard command found"
    try:
        subprocess.run(command, input=text, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        return False, str(exc)
    return True, ""


def _clipboard_command() -> list[str] | None:
    if sys.platform == "darwin" and shutil.which("pbcopy") is not None:
        return ["pbcopy"]
    if shutil.which("wl-copy") is not None:
        return ["wl-copy"]
    if shutil.which("xclip") is not None:
        return ["xclip", "-selection", "clipboard"]
    if shutil.which("xsel") is not None:
        return ["xsel", "--clipboard", "--input"]
    return None


def _safe_filename_component(text: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in text)
    return cleaned.strip("-") or "thread"


def _compact_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")


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
    if command == "review":
        candidates = MemoryCandidateRepository(project_root).list()
        if not candidates:
            return "No memory candidates."
        return "\n".join(render_candidate_row(candidate) for candidate in candidates)
    if command.startswith("review "):
        candidate_id = command.removeprefix("review ").strip()
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


def _handle_interactive_reason_command(command: str, project_root: Path | None) -> str:
    service = ReasonService(project_root)
    if command == "":
        return _interactive_reason_help()
    if command == "list":
        threads = service.list_threads()
        if not threads:
            return "No reason threads."
        return "\n".join(render_reason_row(thread, index=index) for index, thread in enumerate(threads, start=1))
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
        try:
            thread = service.advance_thread(thread_id)
        except (ReasonNotFound, RuntimeError) as exc:
            return f"Error: {exc}"
        return f"Advanced reason thread: {thread.id}\n{render_reason_detail(thread)}"
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
            "  :reason start <question>",
            "  :reason advance <id|index>",
            "  :reason pause <id|index>",
            "  :reason resume <id|index>",
            "  :reason resolve <id|index>",
            "  :reason archive <id|index>",
        ]
    )
    return "\n".join(lines)


def _handle_interactive_trace_command(command: str, project_root: Path | None) -> str:
    service = TraceQueryService(project_root)
    if command in {"", "list"}:
        traces = service.list_traces()
        if not traces:
            return "No trace records."
        return "\n".join(render_trace_row(trace, index=index) for index, trace in enumerate(traces, start=1))
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
        return "\n".join(render_trace_row(trace, index=index) for index, trace in enumerate(traces, start=1))
    return _interactive_trace_help(command)


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
            "  :mem show <entry-id>",
            "  :mem review",
            "  :mem review <candidate-id>",
            "  :mem profile <query>",
            "  :mem sources",
            "  :mem source <source-id>",
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
