"""File-backed trace repository."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, cast

from nuself.config import runtime_paths
from nuself.handles import VisibleHandleError, resolve_visible_item
from nuself.trace.domain import ThoughtTrace, TraceKind, TraceLink, TraceVisibility

TraceVisibilityFilter = Literal["default", "private", "shareable", "internal", "all"]


class TraceNotFound(ValueError):
    """Raised when a trace cannot be resolved."""

    def __init__(self, trace_id: str) -> None:
        super().__init__(f"trace not found: {trace_id}")


class TraceRepository:
    """Store thought traces under private/traces/."""

    def __init__(self, project_root: Path | None = None) -> None:
        paths = runtime_paths(project_root)
        self._root = paths.private_root / "traces"
        self._traces_dir = self._root / "traces"
        self._links_dir = self._root / "links"
        self._index_path = self._root / "index.json"

    def ensure(self) -> None:
        self._traces_dir.mkdir(parents=True, exist_ok=True)
        self._links_dir.mkdir(parents=True, exist_ok=True)

    def save_trace(self, trace: ThoughtTrace) -> ThoughtTrace:
        self.ensure()
        _write_json_atomic(self._trace_path(trace.id), trace.to_wire())
        self.reindex()
        return trace

    def get_trace(self, trace_id: str) -> ThoughtTrace:
        path = self._trace_path(trace_id)
        if not path.exists():
            raise TraceNotFound(trace_id)
        return self._read_trace_path(path)

    def list_traces(
        self,
        *,
        kind: TraceKind | None = None,
        visibility: TraceVisibilityFilter = "default",
    ) -> list[ThoughtTrace]:
        self.ensure()
        traces: list[ThoughtTrace] = []
        for path in sorted(self._traces_dir.glob("*.json")):
            trace = _safe_read_trace_path(path)
            if trace is None:
                continue
            if kind is not None and trace.kind != kind:
                continue
            if not _visible(trace.visibility, visibility):
                continue
            traces.append(trace)
        return sorted(traces, key=lambda trace: (trace.created_at, trace.id))

    def search_traces(
        self,
        query: str,
        *,
        kind: TraceKind | None = None,
        visibility: TraceVisibilityFilter = "default",
    ) -> list[ThoughtTrace]:
        normalized = query.casefold().strip()
        traces = self.list_traces(kind=kind, visibility=visibility)
        if normalized == "":
            return traces
        scored: list[tuple[int, ThoughtTrace]] = []
        for trace in traces:
            score = _trace_search_score(trace, normalized)
            if score > 0:
                scored.append((score, trace))
        return [trace for _, trace in sorted(scored, key=lambda item: (-item[0], item[1].created_at, item[1].id))]

    def resolve_trace(
        self,
        id_or_index: str,
        *,
        kind: TraceKind | None = None,
        visibility: TraceVisibilityFilter = "default",
    ) -> ThoughtTrace:
        try:
            return self.get_trace(id_or_index)
        except TraceNotFound:
            pass
        traces = self.list_traces(kind=kind, visibility=visibility)
        try:
            trace = resolve_visible_item(id_or_index, traces, label="trace")
        except VisibleHandleError as exc:
            raise TraceNotFound(id_or_index) from exc
        if trace is None:
            raise TraceNotFound(id_or_index)
        return trace

    def save_link(self, link: TraceLink) -> TraceLink:
        self.ensure()
        _write_json_atomic(self._link_path(link.id), link.to_wire())
        self.reindex()
        return link

    def links_for(self, trace_id: str) -> list[TraceLink]:
        self.ensure()
        links: list[TraceLink] = []
        for path in sorted(self._links_dir.glob("*.json")):
            link = _safe_read_link_path(path)
            if link is None:
                continue
            if link.source_id == trace_id or link.target_id == trace_id:
                links.append(link)
        return sorted(links, key=lambda link: (link.created_at, link.id))

    def reindex(self) -> Path:
        self.ensure()
        traces = [_safe_read_trace_path(path) for path in sorted(self._traces_dir.glob("*.json"))]
        links = [_safe_read_link_path(path) for path in sorted(self._links_dir.glob("*.json"))]
        trace_ids = [trace.id for trace in traces if trace is not None]
        link_ids = [link.id for link in links if link is not None]
        payload: dict[str, object] = {
            "schema": "NuSelfTraceIndex/v1",
            "trace_count": len(trace_ids),
            "link_count": len(link_ids),
            "trace_ids": trace_ids,
            "link_ids": link_ids,
        }
        _write_json_atomic(self._index_path, payload)
        return self._index_path

    def _trace_path(self, trace_id: str) -> Path:
        _validate_id(trace_id, "trace id")
        return self._traces_dir / f"{trace_id}.json"

    def _link_path(self, link_id: str) -> Path:
        _validate_id(link_id, "trace link id")
        return self._links_dir / f"{link_id}.json"

    def _read_trace_path(self, path: Path) -> ThoughtTrace:
        trace = _safe_read_trace_path(path)
        if trace is None:
            raise ValueError(f"invalid trace file: {path}")
        return trace


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def _safe_read_trace_path(path: Path) -> ThoughtTrace | None:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return ThoughtTrace.from_wire(cast(dict[str, object], raw))
    except ValueError:
        return None


def _safe_read_link_path(path: Path) -> TraceLink | None:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return TraceLink.from_wire(cast(dict[str, object], raw))
    except ValueError:
        return None


def _validate_id(value: str, label: str) -> None:
    if value == "" or "/" in value or value in {".", ".."}:
        raise ValueError(f"invalid {label}: {value}")


def _visible(visibility: TraceVisibility, visibility_filter: TraceVisibilityFilter) -> bool:
    if visibility_filter == "all":
        return True
    if visibility_filter == "default":
        return visibility in {"private", "shareable"}
    return visibility == visibility_filter


def _trace_search_score(trace: ThoughtTrace, query: str) -> int:
    fields = [
        trace.title,
        trace.summary,
        *trace.inputs,
        *trace.evidence_refs,
        *trace.derived_from,
        *trace.outputs,
        *trace.participants,
        *trace.decision_points,
    ]
    score = 0
    for field in fields:
        if query in field.casefold():
            score += 1
    return score
