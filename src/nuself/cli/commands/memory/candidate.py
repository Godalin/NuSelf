"""One-shot memory candidate review command handlers."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from nuself.cli.commands.memory.common import record_memory_trace
from nuself.cli.commands.output import (
    print_ansi,
    resolve_handle,
    resolve_handle_selection,
)
from nuself.domain.memory import MemoryCandidate
from nuself.memory.repository import (
    MemoryCandidateNotFound,
    MemoryCandidateRepository,
    MemoryEntryNotFound,
)
from nuself.tui.memory import (
    render_candidate_detail,
    render_candidate_row,
)


def _candidates_for_list(
    project_root: Path | None,
    *,
    include_reviewed: bool = False,
    review_state: str | None = None,
    sort_by: str = "updated_at",
) -> list[MemoryCandidate]:
    candidates = MemoryCandidateRepository(project_root).list(
        include_reviewed=include_reviewed
    )
    if review_state is not None:
        candidates = [
            candidate
            for candidate in candidates
            if candidate.review_state == review_state
        ]
    if sort_by == "importance":
        return sorted(
            candidates,
            key=lambda candidate: (
                -candidate.importance,
                candidate.updated_at,
                candidate.id,
            ),
        )
    if sort_by == "type":
        return sorted(
            candidates,
            key=lambda candidate: (
                candidate.type,
                candidate.updated_at,
                candidate.id,
            ),
        )
    return candidates


def _resolve_candidate_id(
    args: argparse.Namespace,
) -> str | None:
    return resolve_handle(
        args.candidate_id,
        _candidates_for_list(args.project_root),
        label="memory candidate",
        get_id=lambda candidate: candidate.id,
    )


def _resolve_candidate_ids(
    args: argparse.Namespace,
) -> list[str] | None:
    return resolve_handle_selection(
        args.candidate_id,
        _candidates_for_list(args.project_root),
        label="memory candidate",
        get_id=lambda candidate: candidate.id,
    )


def handle_memory_candidate_list(
    args: argparse.Namespace,
) -> int:
    candidates = _candidates_for_list(
        args.project_root,
        include_reviewed=args.all,
        review_state=args.review_state,
        sort_by=args.sort_by,
    )
    if not candidates:
        print("No memory candidates.")
        return 0
    for index, candidate in enumerate(candidates):
        if index > 0:
            print()
        print_ansi(render_candidate_row(candidate, index=index))
    pending = [
        candidate
        for candidate in candidates
        if candidate.review_state == "pending"
    ]
    if pending:
        print()
        print(
            f"{len(pending)} pending candidate(s). Accept: "
            "nuself memory review accept <id|index-selection>"
        )
    return 0


def handle_memory_candidate_show(
    args: argparse.Namespace,
) -> int:
    candidate_id = _resolve_candidate_id(args)
    if candidate_id is None:
        return 1
    try:
        candidate = MemoryCandidateRepository(
            args.project_root
        ).get(candidate_id)
    except MemoryCandidateNotFound:
        print(
            f"Memory candidate not found: {candidate_id}",
            file=sys.stderr,
        )
        return 1
    print_ansi(render_candidate_detail(candidate))
    return 0


def handle_memory_candidate_accept(
    args: argparse.Namespace,
) -> int:
    candidate_ids = _resolve_candidate_ids(args)
    if candidate_ids is None:
        return 1
    repository = MemoryCandidateRepository(args.project_root)
    for candidate_id in candidate_ids:
        try:
            entry = repository.accept(candidate_id)
        except MemoryCandidateNotFound:
            print(
                f"Memory candidate not found: {candidate_id}",
                file=sys.stderr,
            )
            return 1
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        record_memory_trace(args.project_root, entry, "accept")
        print(
            f"Accepted memory candidate: {candidate_id} -> "
            f"{entry.id}"
        )
    return 0


def handle_memory_candidate_reject(
    args: argparse.Namespace,
) -> int:
    candidate_ids = _resolve_candidate_ids(args)
    if candidate_ids is None:
        return 1
    repository = MemoryCandidateRepository(args.project_root)
    for candidate_id in candidate_ids:
        try:
            repository.reject(candidate_id)
        except MemoryCandidateNotFound:
            print(
                f"Memory candidate not found: {candidate_id}",
                file=sys.stderr,
            )
            return 1
        print(f"Rejected memory candidate: {candidate_id}")
    return 0


def handle_memory_candidate_edit(
    args: argparse.Namespace,
) -> int:
    candidate_id = _resolve_candidate_id(args)
    if candidate_id is None:
        return 1
    try:
        updated = MemoryCandidateRepository(args.project_root).edit(
            candidate_id,
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
        print(
            f"Memory candidate not found: {candidate_id}",
            file=sys.stderr,
        )
        return 1
    print_ansi(render_candidate_row(updated))
    return 0


def handle_memory_candidate_merge(
    args: argparse.Namespace,
) -> int:
    candidate_id = _resolve_candidate_id(args)
    if candidate_id is None:
        return 1
    try:
        entry = MemoryCandidateRepository(
            args.project_root
        ).merge(candidate_id, args.entry_id)
    except MemoryCandidateNotFound:
        print(
            f"Memory candidate not found: {candidate_id}",
            file=sys.stderr,
        )
        return 1
    except MemoryEntryNotFound:
        print(
            f"Memory entry not found: {args.entry_id}",
            file=sys.stderr,
        )
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    record_memory_trace(args.project_root, entry, "merge")
    print(
        f"Merged memory candidate: {candidate_id} -> {entry.id}"
    )
    return 0
