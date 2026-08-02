"""One-shot durable memory entry command handlers."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
import sys
from pathlib import Path

from nuself.cli.composition import cli_application
from nuself.agent.structured import LangChainStructuredAgent
from nuself.cli.commands.memory.common import record_memory_trace
from nuself.cli.memory_preview import format_memory_preview
from nuself.cli.output import (
    print_ansi,
    resolve_handle,
    resolve_handle_selection,
)
from nuself.domain.memory import (
    MemoryEntry,
    default_memory_type_registry,
)
from nuself.llm import configured_langchain_chat_models
from nuself.memory.intake import IntakeResultOutput, MemoryIntakeAgent
from nuself.memory.query import MemoryQuery
from nuself.memory.repository import (
    MemoryEntryNotFound,
    MemoryRelationFilters,
    MemoryRelationIndexRecord,
    MemorySearchFilters,
    MemoryStats,
    memory_stats,
)
from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.tui.memory import render_memory_entry_detail, render_memory_entry_row


def memory_type_choices() -> list[str]:
    return list(default_memory_type_registry().names())


def _entries_for_list(
    project_root: Path | None,
    *,
    sort_by: str = "updated_at",
    review_state: str | None = None,
) -> list[MemoryEntry]:
    entries = cli_application().memory.entries.list()
    if review_state is not None:
        entries = [
            entry
            for entry in entries
            if entry.review_state == review_state
        ]
    if sort_by == "importance":
        return sorted(
            entries,
            key=lambda entry: (
                -entry.importance,
                entry.updated_at,
                entry.id,
            ),
        )
    if sort_by == "type":
        return sorted(
            entries,
            key=lambda entry: (
                entry.type,
                entry.updated_at,
                entry.id,
            ),
        )
    return entries


def _resolve_entry_id(args: argparse.Namespace) -> str | None:
    return resolve_handle(
        args.entry_id,
        _entries_for_list(args.project_root),
        label="memory",
        get_id=lambda entry: entry.id,
    )


def _resolve_entry_ids(
    args: argparse.Namespace,
) -> list[str] | None:
    return resolve_handle_selection(
        args.entry_id,
        _entries_for_list(args.project_root),
        label="memory",
        get_id=lambda entry: entry.id,
    )


def _format_counts(counts: Mapping[str, int]) -> str:
    if not counts:
        return "-"
    return ", ".join(
        f"{key}={counts[key]}" for key in sorted(counts)
    )


def _format_float_counts(counts: Mapping[str, float]) -> str:
    if not counts:
        return "-"
    return ", ".join(
        f"{key}={counts[key]:.2f}" for key in sorted(counts)
    )


def _format_stats(stats: MemoryStats) -> str:
    return "\n".join(
        [
            f"entries_total: {stats.entries_total}",
            f"candidates_total: {stats.candidates_total}",
            f"pending_candidates: {stats.pending_candidates}",
            "entries_with_observed_at: "
            f"{stats.entries_with_observed_at}",
            f"entries_with_evidence: {stats.entries_with_evidence}",
            f"avg_importance: {stats.avg_importance:.2f}",
            f"max_importance: {stats.max_importance:.2f}",
            "avg_importance_by_type: "
            f"{_format_float_counts(stats.avg_importance_by_type)}",
            "entries_by_type: "
            f"{_format_counts(stats.entries_by_type)}",
            "entries_by_review_state: "
            f"{_format_counts(stats.entries_by_review_state)}",
            "candidates_by_review_state: "
            f"{_format_counts(stats.candidates_by_review_state)}",
        ]
    )


def _format_relation(record: MemoryRelationIndexRecord) -> str:
    target_title = record.target_title or "(missing target)"
    target_type = record.target_type or "missing"
    return (
        f"{record.source_id} --{record.relation}-> "
        f"{record.target_id} "
        f"[source={record.source_type}:{record.source_title} "
        f"target={target_type}:{target_title} "
        f"target_exists={record.target_exists} "
        f"confidence={record.confidence:.2f}]"
    )


def handle_memory_list(args: argparse.Namespace) -> int:
    entries = _entries_for_list(
        args.project_root,
        sort_by=args.sort_by,
        review_state=args.review_state,
    )
    if not entries:
        print("No memory entries.")
        return 0
    for index, entry in enumerate(entries):
        print_ansi(render_memory_entry_row(entry, index=index))
    return 0


def handle_memory_preview(args: argparse.Namespace) -> int:
    print_ansi(format_memory_preview(args.project_root, args.limit))
    return 0


def handle_memory_show(args: argparse.Namespace) -> int:
    entry_id = _resolve_entry_id(args)
    if entry_id is None:
        return 1
    try:
        entry = cli_application().memory.entries.get(entry_id)
    except MemoryEntryNotFound:
        print(
            f"Memory entry not found: {entry_id}",
            file=sys.stderr,
        )
        return 1
    print_ansi(render_memory_entry_detail(entry))
    return 0


def handle_memory_add(args: argparse.Namespace) -> int:
    try:
        application = cli_application()
        inferred = MemoryIntakeAgent(
            agent=LangChainStructuredAgent(
                IntakeResultOutput,
                endpoints=configured_langchain_chat_models(
                    application.paths.authority_root,
                    config=application.config,
                ),
                project_root=application.paths.authority_root,
                component="memory",
            ),
            profile_repository=application.memory.profile,
        ).infer(
            body=args.body,
            title=args.title,
            memory_type=args.type,
            tags=list(args.tag),
        )
    except (RuntimeError, ValueError) as exc:
        print(
            "Memory intake failed: "
            f"{diagnostic_exception_message(exc)}",
            file=sys.stderr,
        )
        return 1
    entry = MemoryEntry(
        type=inferred.type,
        title=inferred.title,
        body=inferred.body,
        tags=list(inferred.tags),
        confidence=inferred.confidence,
        importance=(
            args.importance
            if args.importance is not None
            else inferred.importance
        ),
    )
    repository = application.memory.entries
    repository.save(entry)
    record_memory_trace(
        application.trace.recorder,
        args.project_root,
        entry,
        "add",
    )
    print_ansi(render_memory_entry_row(entry))
    return 0


def handle_memory_edit(args: argparse.Namespace) -> int:
    repository = cli_application().memory.entries
    entry_id = _resolve_entry_id(args)
    if entry_id is None:
        return 1
    try:
        entry = repository.get(entry_id)
    except MemoryEntryNotFound:
        print(
            f"Memory entry not found: {entry_id}",
            file=sys.stderr,
        )
        return 1
    updated = entry.with_updates(
        title=args.title,
        body=args.body,
        tags=list(args.tag) if args.tag is not None else None,
        importance=args.importance,
        review_state=args.review_state,
    )
    repository.save(updated)
    print_ansi(render_memory_entry_row(updated))
    return 0


def handle_memory_delete(args: argparse.Namespace) -> int:
    repository = cli_application().memory.entries
    entry_ids = _resolve_entry_ids(args)
    if entry_ids is None:
        return 1
    for entry_id in entry_ids:
        try:
            repository.delete(entry_id)
        except MemoryEntryNotFound:
            print(
                f"Memory entry not found: {entry_id}",
                file=sys.stderr,
            )
            return 1
    for entry_id in entry_ids:
        print(f"Deleted memory entry: {entry_id}")
    return 0


def handle_memory_search(args: argparse.Namespace) -> int:
    application = cli_application()
    repository = application.memory.entries
    filters = MemorySearchFilters(
        type=args.type,
        tag=args.tag,
        review_state=args.review_state,
        observed_from=args.observed_from,
        observed_to=args.observed_to,
        valid_on=args.valid_on,
        min_importance=args.min_importance,
    )
    eligible_ids = {
        entry.id for entry in repository.search("", filters)
    }
    matches = application.memory_service.search(
        MemoryQuery(
            text=args.query,
            limit=max(len(eligible_ids), 1),
            review_states=(
                "draft",
                "reviewed",
                "rejected",
                "quarantined",
                "archived",
            ),
        )
    )
    entries = [
        match.entry
        for match in matches
        if match.entry.id in eligible_ids
    ]
    if not entries:
        print("No matching memory entries.")
        return 0
    for entry in entries:
        print_ansi(render_memory_entry_row(entry))
    return 0


def handle_memory_stats(args: argparse.Namespace) -> int:
    repositories = cli_application().memory
    print(
        _format_stats(
            memory_stats(repositories.entries, repositories.candidates)
        )
    )
    return 0


def handle_memory_relations(args: argparse.Namespace) -> int:
    records = cli_application().memory.entries.list_relations(
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
        print(_format_relation(record))
    return 0


def handle_memory_types(args: argparse.Namespace) -> int:
    registry = default_memory_type_registry()
    if args.json:
        output: list[dict[str, object]] = []
        for name in registry.names():
            example = registry.example(name)
            output.append(
                {
                    "type": name,
                    "description": registry.describe(name),
                    "default_importance": (
                        registry.importance(example)
                        if example is not None
                        else None
                    ),
                    "example": (
                        example.to_wire()
                        if example is not None
                        else None
                    ),
                }
            )
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        for name in registry.names():
            example = registry.example(name)
            default_importance = (
                registry.importance(example)
                if example is not None
                else 0.5
            )
            print(
                f"{name}: {registry.describe(name)} "
                f"(default importance {default_importance})"
            )
    return 0


def handle_memory_unquarantine(
    args: argparse.Namespace,
) -> int:
    try:
        cli_application().memory.entries.unquarantine(
            args.entry_id
        )
    except MemoryEntryNotFound:
        print(
            f"Memory entry not found: {args.entry_id}",
            file=sys.stderr,
        )
        return 1
    except ValueError as exc:
        print(diagnostic_exception_message(exc), file=sys.stderr)
        return 1
    print(f"Unquarantined memory entry: {args.entry_id}")
    return 0
