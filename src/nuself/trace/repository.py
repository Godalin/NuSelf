"""File-backed trace repository."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
import threading
from typing import Literal, cast

from nuself.handles import VisibleHandleError, resolve_visible_item
from nuself.config import runtime_paths
from nuself.derived import write_derived_index
from nuself.runtime.observability import decode_observed_record
from nuself.storage import StorageBackend
from nuself.trace.domain import ThoughtTrace, TraceKind, TraceLink, TraceVisibility

TraceVisibilityFilter = Literal["default", "private", "shareable", "internal", "all"]


class TraceNotFound(ValueError):
    """Raised when a trace cannot be resolved."""

    def __init__(self, trace_id: str) -> None:
        super().__init__(f"trace not found: {trace_id}")


class TraceRepository:
    """Store thought traces in the selected authority."""

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        backend: StorageBackend,
    ) -> None:
        self._traces = backend.collection("trace_nodes")
        self._links = backend.collection("trace_edges")
        self._lock = threading.RLock()
        self._paths = runtime_paths(project_root)

    def save_trace(self, trace: ThoughtTrace) -> ThoughtTrace:
        with self._lock:
            self._traces.put(trace.id, trace.to_wire())
        return trace

    def get_trace(self, trace_id: str) -> ThoughtTrace:
        wire = self._traces.get(trace_id)
        if wire is None:
            raise TraceNotFound(trace_id)
        return ThoughtTrace.from_wire(wire)

    def list_traces(
        self,
        *,
        kind: TraceKind | None = None,
        visibility: TraceVisibilityFilter = "default",
    ) -> list[ThoughtTrace]:
        traces: list[ThoughtTrace] = []
        for wire in self._traces.list():
            trace = decode_observed_record(
                wire,
                ThoughtTrace.from_wire,
                component="reasoning",
                collection="trace_nodes",
                project_root=self._paths.project_root,
            )
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

    def traces_for_artifact(
        self,
        artifact_ref: str,
        *,
        visibility: TraceVisibilityFilter = "default",
    ) -> list[ThoughtTrace]:
        normalized = artifact_ref.strip()
        if normalized == "":
            return []
        return [
            trace
            for trace in self.list_traces(visibility=visibility)
            if _trace_mentions_artifact(trace, normalized)
        ]

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
        with self._lock:
            self._links.put(link.id, link.to_wire())
        return link

    def links_for(self, trace_id: str) -> list[TraceLink]:
        links: list[TraceLink] = []
        for wire in self._links.list():
            link = self._decode_link(wire)
            if link is None:
                continue
            if link.source_id == trace_id or link.target_id == trace_id:
                links.append(link)
        return sorted(links, key=lambda link: (link.created_at, link.id))

    def links_for_artifact(self, artifact_ref: str) -> list[TraceLink]:
        normalized = artifact_ref.strip()
        if normalized == "":
            return []
        links: list[TraceLink] = []
        for wire in self._links.list():
            link = self._decode_link(wire)
            if link is None:
                continue
            if link.source_id == normalized or link.target_id == normalized:
                links.append(link)
        return sorted(links, key=lambda link: (link.created_at, link.id))

    def reindex(self) -> Path:
        records: list[object] = [
            {"_record_kind": "trace", **item.to_wire()}
            for item in self.list_traces(visibility="all")
        ]
        for wire in self._links.list():
            records.append({"_record_kind": "link", **wire})
        return write_derived_index(
            self._paths, "trace_index.json", records
        )

    def _decode_link(self, wire: dict[str, object]) -> TraceLink | None:
        return decode_observed_record(
            wire,
            TraceLink.from_wire,
            component="reasoning",
            collection="trace_edges",
            project_root=self._paths.project_root,
        )


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


def _trace_mentions_artifact(trace: ThoughtTrace, artifact_ref: str) -> bool:
    fields = (
        trace.inputs,
        trace.evidence_refs,
        trace.derived_from,
        trace.outputs,
    )
    if any(artifact_ref in field for field in fields):
        return True
    return _metadata_mentions_artifact(trace.metadata, artifact_ref)


def _metadata_mentions_artifact(value: object, artifact_ref: str) -> bool:
    if isinstance(value, str):
        return value == artifact_ref
    if isinstance(value, Sequence):
        items = cast(Sequence[object], value)
        return any(
            _metadata_mentions_artifact(item, artifact_ref)
            for item in items
        )
    if isinstance(value, Mapping):
        metadata = cast(Mapping[object, object], value)
        return any(_metadata_mentions_artifact(item, artifact_ref) for item in metadata.values())
    return False
