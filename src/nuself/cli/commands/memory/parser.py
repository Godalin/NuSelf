"""Parser registration for the memory command family."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nuself.cli.commands.memory.candidate import (
    handle_memory_candidate_accept,
    handle_memory_candidate_edit,
    handle_memory_candidate_list,
    handle_memory_candidate_merge,
    handle_memory_candidate_reject,
    handle_memory_candidate_show,
)
from nuself.cli.commands.memory.entries import (
    DEFAULT_PREVIEW_LIMIT,
    handle_memory_add,
    handle_memory_delete,
    handle_memory_edit,
    handle_memory_list,
    handle_memory_preview,
    handle_memory_reindex,
    handle_memory_relations,
    handle_memory_search,
    handle_memory_show,
    handle_memory_stats,
    handle_memory_types,
    handle_memory_unquarantine,
    memory_type_choices,
)
from nuself.cli.commands.memory.graph import (
    handle_memory_graph_closure,
    handle_memory_graph_edges,
    handle_memory_graph_nodes,
    handle_memory_graph_path,
    handle_memory_graph_search,
)
from nuself.cli.commands.memory.maintenance import (
    handle_memory_export,
    handle_memory_import,
    handle_memory_optimize,
    handle_memory_update,
)
from nuself.cli.commands.memory.plan import (
    handle_memory_plan_discard,
    handle_memory_plan_show,
)
from nuself.cli.commands.memory.profile import (
    handle_memory_profile_delete,
    handle_memory_profile_list,
    handle_memory_profile_reindex,
    handle_memory_profile_search,
    handle_memory_profile_show,
)
from nuself.cli.commands.memory.source import (
    handle_memory_source_chunks,
    handle_memory_source_delete,
    handle_memory_source_extract,
    handle_memory_source_ingest,
    handle_memory_source_list,
    handle_memory_source_search,
    handle_memory_source_show,
)
from nuself.cli.handlers import CliHandlerBindings
from nuself.domain.memory import default_relation_descriptor_registry


def add_memory_parser(
    subparsers: Any,
    bindings: CliHandlerBindings,
) -> None:
    bind_handler = bindings.bind
    bind_help = bindings.bind_help
    memory_parser = subparsers.add_parser(
        "memory",
        help="Manage memory entries, sources, profiles, reviews, and the memory graph.",
        description="Manage memory entries, sources, profiles, reviews, and the memory graph.",
    )
    bind_help(memory_parser)
    memory_subparsers = memory_parser.add_subparsers(
        dest="memory_command", metavar="<command>"
    )
    list_parser = memory_subparsers.add_parser(
        "list", help="List memory entries with visible indexes."
    )
    list_parser.add_argument(
        "--sort-by", choices=["updated_at", "importance", "type"], default="updated_at"
    )
    list_parser.add_argument(
        "--review-state",
        choices=["draft", "reviewed", "rejected", "quarantined", "archived"],
        default=None,
    )
    bind_handler(list_parser, handle_memory_list)
    preview_parser = memory_subparsers.add_parser(
        "preview", help="Show the memory preview used by chat context."
    )
    preview_parser.add_argument("--limit", type=int, default=DEFAULT_PREVIEW_LIMIT)
    bind_handler(preview_parser, handle_memory_preview)
    show_parser = memory_subparsers.add_parser(
        "show", help="Show one memory entry by ID or visible index."
    )
    show_parser.add_argument("entry_id")
    bind_handler(show_parser, handle_memory_show)
    add_parser = memory_subparsers.add_parser(
        "add", help="Create a memory entry manually."
    )
    add_parser.add_argument("--type", choices=memory_type_choices())
    add_parser.add_argument("--title", default=None)
    add_parser.add_argument("--body", "--text", required=True)
    add_parser.add_argument("--tag", action="append", default=[])
    add_parser.add_argument("--importance", type=float, default=None)
    bind_handler(add_parser, handle_memory_add)
    edit_parser = memory_subparsers.add_parser(
        "edit", help="Edit one memory entry by ID or visible index."
    )
    edit_parser.add_argument("entry_id")
    edit_parser.add_argument("--title", default=None)
    edit_parser.add_argument("--body", "--text", default=None)
    edit_parser.add_argument("--tag", action="append", default=None)
    edit_parser.add_argument("--importance", type=float, default=None)
    edit_parser.add_argument(
        "--review-state",
        choices=["draft", "reviewed", "rejected", "quarantined", "archived"],
        default=None,
    )
    bind_handler(edit_parser, handle_memory_edit)
    delete_parser = memory_subparsers.add_parser(
        "delete", help="Delete memory entries by ID, index, or selection."
    )
    delete_parser.add_argument("entry_id")
    bind_handler(delete_parser, handle_memory_delete)
    search_parser = memory_subparsers.add_parser(
        "search", help="Search durable memory entries."
    )
    search_parser.add_argument("query", nargs="?", default="")
    search_parser.add_argument("--type", choices=memory_type_choices(), default=None)
    search_parser.add_argument("--tag", default=None)
    search_parser.add_argument(
        "--review-state",
        choices=["draft", "reviewed", "rejected", "quarantined", "archived"],
        default=None,
    )
    search_parser.add_argument("--observed-from", default=None)
    search_parser.add_argument("--observed-to", default=None)
    search_parser.add_argument("--valid-on", default=None)
    search_parser.add_argument("--min-importance", type=float, default=None)
    search_parser.add_argument(
        "--sort-by", choices=["score", "updated_at", "importance"], default="score"
    )
    bind_handler(search_parser, handle_memory_search)
    bind_handler(
        memory_subparsers.add_parser(
            "stats", help="Show memory and review statistics."
        ),
        handle_memory_stats,
    )
    relations_parser = memory_subparsers.add_parser(
        "relations", help="List derived memory relations."
    )
    _relation_names = default_relation_descriptor_registry().names()
    relations_parser.add_argument("--relation", choices=_relation_names, default=None)
    relations_parser.add_argument("--source-id", default=None)
    relations_parser.add_argument("--target-id", default=None)
    bind_handler(relations_parser, handle_memory_relations)
    graph_parser = memory_subparsers.add_parser(
        "graph",
        help="Inspect symbolic memory graph nodes, edges, paths, and closure.",
        description="Inspect symbolic memory graph nodes, edges, paths, and closure.",
    )
    bind_help(graph_parser)
    graph_subparsers = graph_parser.add_subparsers(
        dest="graph_command", metavar="<command>"
    )
    graph_nodes_parser = graph_subparsers.add_parser("nodes", help="List graph nodes.")
    graph_nodes_parser.add_argument("--type", default=None)
    bind_handler(graph_nodes_parser, handle_memory_graph_nodes)
    graph_edges_parser = graph_subparsers.add_parser("edges", help="List graph edges.")
    graph_edges_parser.add_argument("--relation", choices=_relation_names, default=None)
    graph_edges_parser.add_argument("--source-id", default=None)
    graph_edges_parser.add_argument("--target-id", default=None)
    bind_handler(graph_edges_parser, handle_memory_graph_edges)
    graph_search_parser = graph_subparsers.add_parser(
        "search", help="Search graph nodes and nearby context."
    )
    graph_search_parser.add_argument("query")
    graph_search_parser.add_argument("--type", default=None)
    graph_search_parser.add_argument("--limit", type=int, default=8)
    graph_search_parser.add_argument("--depth", type=int, default=1)
    bind_handler(graph_search_parser, handle_memory_graph_search)
    graph_path_parser = graph_subparsers.add_parser(
        "path", help="Find a path between two graph nodes."
    )
    graph_path_parser.add_argument("from_id")
    graph_path_parser.add_argument("to_id")
    bind_handler(graph_path_parser, handle_memory_graph_path)
    graph_closure_parser = graph_subparsers.add_parser(
        "closure", help="Show reachable graph context from one node."
    )
    graph_closure_parser.add_argument("node_id")
    graph_closure_parser.add_argument(
        "--relation", choices=_relation_names, default=None
    )
    bind_handler(graph_closure_parser, handle_memory_graph_closure)
    bind_handler(
        memory_subparsers.add_parser("update", help="Run the memory curator once."),
        handle_memory_update,
    )
    plan_parser = memory_subparsers.add_parser(
        "plan",
        help="Inspect or discard curator recovery plans.",
        description="Inspect or discard curator recovery plans.",
    )
    bind_help(plan_parser)
    plan_subparsers = plan_parser.add_subparsers(
        dest="plan_command",
        metavar="<command>",
    )
    plan_show_parser = plan_subparsers.add_parser(
        "show",
        help="Show payload-safe recovery metadata for one thread.",
    )
    plan_show_parser.add_argument("thread_id")
    bind_handler(plan_show_parser, handle_memory_plan_show)
    plan_discard_parser = plan_subparsers.add_parser(
        "discard",
        help="Discard one thread's recovery plan without changing its cursor.",
    )
    plan_discard_parser.add_argument("thread_id")
    plan_discard_parser.add_argument(
        "--force",
        action="store_true",
        required=True,
        help="Acknowledge that the source range may be modeled again.",
    )
    bind_handler(plan_discard_parser, handle_memory_plan_discard)
    optimize_parser = memory_subparsers.add_parser(
        "optimize", help="Run the memory optimizer once."
    )
    optimize_parser.add_argument("--limit", type=int, default=50)
    bind_handler(optimize_parser, handle_memory_optimize)
    export_parser = memory_subparsers.add_parser(
        "export", help="Export memory entries to JSON."
    )
    export_parser.add_argument("--output", "-o", type=Path, required=True)
    bind_handler(export_parser, handle_memory_export)
    import_parser = memory_subparsers.add_parser(
        "import", help="Import memory entries from JSON."
    )
    import_parser.add_argument("path", type=Path)
    bind_handler(import_parser, handle_memory_import)
    profile_parser = memory_subparsers.add_parser(
        "profile",
        help="Manage extracted profile facts and preferences.",
        description="Manage extracted profile facts and preferences.",
    )
    bind_help(profile_parser)
    profile_subparsers = profile_parser.add_subparsers(
        dest="profile_command", metavar="<command>"
    )
    profile_list_parser = profile_subparsers.add_parser(
        "list", help="List profile entries with visible indexes."
    )
    profile_list_parser.add_argument(
        "--sort-by", choices=["updated_at", "importance", "type"], default="updated_at"
    )
    bind_handler(profile_list_parser, handle_memory_profile_list)
    profile_search_parser = profile_subparsers.add_parser(
        "search", help="Search profile entries."
    )
    profile_search_parser.add_argument("query", nargs="?", default="")
    profile_search_parser.add_argument("--type", default=None)
    profile_search_parser.add_argument("--tag", default=None)
    profile_search_parser.add_argument("--observed-from", default=None)
    profile_search_parser.add_argument("--observed-to", default=None)
    profile_search_parser.add_argument("--valid-on", default=None)
    bind_handler(profile_search_parser, handle_memory_profile_search)
    profile_show_parser = profile_subparsers.add_parser(
        "show", help="Show one profile entry by ID or visible index."
    )
    profile_show_parser.add_argument("profile_id")
    bind_handler(profile_show_parser, handle_memory_profile_show)
    profile_delete_parser = profile_subparsers.add_parser(
        "delete", help="Delete one profile entry by ID or visible index."
    )
    profile_delete_parser.add_argument("profile_id")
    bind_handler(profile_delete_parser, handle_memory_profile_delete)
    bind_handler(
        profile_subparsers.add_parser(
            "reindex", help="Rebuild derived profile entries."
        ),
        handle_memory_profile_reindex,
    )
    source_parser = memory_subparsers.add_parser(
        "source",
        help="Manage source documents and extracted chunks.",
        description="Manage source documents and extracted chunks.",
    )
    bind_help(source_parser)
    source_subparsers = source_parser.add_subparsers(
        dest="source_command", metavar="<command>"
    )
    source_ingest_parser = source_subparsers.add_parser(
        "ingest", help="Ingest a source document."
    )
    source_ingest_parser.add_argument("path", type=Path)
    source_ingest_parser.add_argument("--tag", action="append", default=[])
    source_ingest_parser.add_argument(
        "--privacy", choices=["private", "shareable"], default="private"
    )
    bind_handler(source_ingest_parser, handle_memory_source_ingest)
    bind_handler(
        source_subparsers.add_parser("list", help="List source documents."),
        handle_memory_source_list,
    )
    source_show_parser = source_subparsers.add_parser(
        "show", help="Show one source document by ID or visible index."
    )
    source_show_parser.add_argument("source_id")
    bind_handler(source_show_parser, handle_memory_source_show)
    source_delete_parser = source_subparsers.add_parser(
        "delete", help="Delete one source document by ID or visible index."
    )
    source_delete_parser.add_argument("source_id")
    bind_handler(source_delete_parser, handle_memory_source_delete)
    source_chunks_parser = source_subparsers.add_parser(
        "chunks", help="List chunks for one source document."
    )
    source_chunks_parser.add_argument("source_id", nargs="?")
    bind_handler(source_chunks_parser, handle_memory_source_chunks)
    source_search_parser = source_subparsers.add_parser(
        "search", help="Search source chunks."
    )
    source_search_parser.add_argument("query")
    source_search_parser.add_argument("--limit", type=int, default=8)
    bind_handler(source_search_parser, handle_memory_source_search)
    source_extract_parser = source_subparsers.add_parser(
        "extract", help="Extract memory candidates from one source document."
    )
    source_extract_parser.add_argument("source_id")
    bind_handler(source_extract_parser, handle_memory_source_extract)
    candidate_parser = memory_subparsers.add_parser(
        "review",
        help="Review pending memory candidates.",
        description="Review pending memory candidates.",
    )
    bind_help(candidate_parser)
    candidate_subparsers = candidate_parser.add_subparsers(
        dest="candidate_command", metavar="<command>"
    )
    candidate_list_parser = candidate_subparsers.add_parser(
        "list", help="List memory review candidates."
    )
    candidate_list_parser.add_argument("--all", action="store_true")
    candidate_list_parser.add_argument(
        "--review-state", choices=["pending", "accepted", "rejected"], default=None
    )
    candidate_list_parser.add_argument(
        "--sort-by", choices=["updated_at", "importance", "type"], default="updated_at"
    )
    bind_handler(candidate_list_parser, handle_memory_candidate_list)
    candidate_show_parser = candidate_subparsers.add_parser(
        "show", help="Show one review candidate by ID or visible index."
    )
    candidate_show_parser.add_argument("candidate_id")
    bind_handler(candidate_show_parser, handle_memory_candidate_show)
    candidate_accept_parser = candidate_subparsers.add_parser(
        "accept", help="Accept review candidates by ID, index, or selection."
    )
    candidate_accept_parser.add_argument("candidate_id")
    bind_handler(candidate_accept_parser, handle_memory_candidate_accept)
    candidate_reject_parser = candidate_subparsers.add_parser(
        "reject", help="Reject review candidates by ID, index, or selection."
    )
    candidate_reject_parser.add_argument("candidate_id")
    bind_handler(candidate_reject_parser, handle_memory_candidate_reject)
    candidate_edit_parser = candidate_subparsers.add_parser(
        "edit", help="Edit one review candidate."
    )
    candidate_edit_parser.add_argument("candidate_id")
    candidate_edit_parser.add_argument("--title", default=None)
    candidate_edit_parser.add_argument("--body", "--text", default=None)
    candidate_edit_parser.add_argument("--tag", action="append", default=None)
    candidate_edit_parser.add_argument("--importance", type=float, default=None)
    candidate_edit_parser.add_argument("--observed-at", default=None)
    candidate_edit_parser.add_argument("--valid-from", default=None)
    candidate_edit_parser.add_argument("--valid-until", default=None)
    candidate_edit_parser.add_argument("--temporal-note", default=None)
    bind_handler(candidate_edit_parser, handle_memory_candidate_edit)
    candidate_merge_parser = candidate_subparsers.add_parser(
        "merge", help="Merge one candidate into a memory entry."
    )
    candidate_merge_parser.add_argument("candidate_id")
    candidate_merge_parser.add_argument("entry_id")
    bind_handler(candidate_merge_parser, handle_memory_candidate_merge)
    types_parser = memory_subparsers.add_parser(
        "types", help="List registered memory types."
    )
    types_parser.add_argument("--json", action="store_true")
    bind_handler(types_parser, handle_memory_types)
    bind_handler(
        memory_subparsers.add_parser("reindex", help="Rebuild memory derived indexes."),
        handle_memory_reindex,
    )
    unquarantine_parser = memory_subparsers.add_parser(
        "unquarantine", help="Move one quarantined memory entry back to draft."
    )
    unquarantine_parser.add_argument("entry_id")
    bind_handler(unquarantine_parser, handle_memory_unquarantine)
