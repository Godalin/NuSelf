"""One-shot thought provenance trace command handlers."""

from __future__ import annotations

import argparse
import json
import sys
from typing import cast

from nuself.commands.output import print_ansi
from nuself.trace.domain import TRACE_KINDS, TraceKind
from nuself.trace.repository import (
    TraceNotFound,
    TraceRepository,
    TraceVisibilityFilter,
)
from nuself.trace.service import TraceQueryService
from nuself.tui.trace import render_trace_detail, render_trace_row


def _print_json(*entities: object) -> None:
    for entity in entities:
        print(json.dumps(entity, sort_keys=True, ensure_ascii=True))


def _optional_trace_kind(value: str | None) -> TraceKind | None:
    if value is None:
        return None
    return value if value in TRACE_KINDS else None


def _trace_visibility_filter(
    value: str | None,
) -> TraceVisibilityFilter:
    if value in {"private", "shareable", "internal", "all"}:
        return cast(TraceVisibilityFilter, value)
    return "default"


def handle_trace_list(args: argparse.Namespace) -> int:
    traces = TraceQueryService(args.project_root).list_traces(
        kind=_optional_trace_kind(args.kind),
        visibility=_trace_visibility_filter(args.visibility),
    )
    if not traces:
        print("No trace records.")
        return 0
    if args.as_json:
        _print_json(*(trace.to_wire() for trace in traces))
        return 0
    for index, trace in enumerate(traces):
        print_ansi(render_trace_row(trace, index=index))
    return 0


def handle_trace_show(args: argparse.Namespace) -> int:
    repository = TraceRepository(args.project_root)
    try:
        trace = repository.resolve_trace(args.trace_id)
    except TraceNotFound:
        print(f"Trace not found: {args.trace_id}", file=sys.stderr)
        return 1
    links = repository.links_for(trace.id)
    if args.as_json:
        payload = trace.to_wire()
        payload["links"] = [link.to_wire() for link in links]
        _print_json(payload)
        return 0
    print_ansi(render_trace_detail(trace, links))
    return 0


def handle_trace_search(args: argparse.Namespace) -> int:
    traces = TraceQueryService(args.project_root).search_traces(
        args.query,
        kind=_optional_trace_kind(args.kind),
        visibility=_trace_visibility_filter(args.visibility),
    )
    if not traces:
        print("No matching trace records.")
        return 0
    if args.as_json:
        _print_json(*(trace.to_wire() for trace in traces))
        return 0
    for index, trace in enumerate(traces):
        print_ansi(render_trace_row(trace, index=index))
    return 0


def handle_trace_related(args: argparse.Namespace) -> int:
    service = TraceQueryService(args.project_root)
    traces = service.traces_for_artifact(
        args.artifact_ref,
        visibility=_trace_visibility_filter(args.visibility),
    )
    links = service.links_for_artifact(args.artifact_ref)
    if not traces and not links:
        print(
            "No trace records or links related to: "
            f"{args.artifact_ref}"
        )
        return 0
    if args.as_json:
        _print_json(
            {
                "artifact_ref": args.artifact_ref,
                "traces": [trace.to_wire() for trace in traces],
                "links": [link.to_wire() for link in links],
            }
        )
        return 0
    for index, trace in enumerate(traces):
        print_ansi(render_trace_row(trace, index=index))
    if links:
        if traces:
            print()
        print("Related links:")
        for link in links:
            print(
                f"  {link.relation}: {link.source_id} -> "
                f"{link.target_id} ({link.summary})"
            )
    return 0


def handle_trace_reindex(args: argparse.Namespace) -> int:
    path = TraceRepository(args.project_root).reindex()
    print(f"Rebuilt trace index: {path}")
    return 0
