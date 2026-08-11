"""Bounded ordered provenance-chain queries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from nuself.trace.model import ThoughtTrace
from nuself.trace.service import TraceQueryService

_ARTIFACT_PREFIXES = (
    "conversation_turn:",
    "conversation_range:",
    "memory:",
    "profile:",
    "reason:",
    "reason_step:",
    "reflection:",
    "source:",
    "persona_prompt:",
)


class ArtifactSummaryResolver(Protocol):
    """Resolve one foreign artifact through its public service boundary."""

    def resolve(self, artifact_ref: str) -> str | None: ...


@dataclass(frozen=True)
class ProvenanceNode:
    """One ordered artifact or ThoughtTrace node."""

    ref: str
    body: str


@dataclass(frozen=True)
class ProvenanceChain:
    """A bounded topological projection of one artifact's producer graph."""

    nodes: tuple[ProvenanceNode, ...]
    truncated: bool = False


class ProvenanceService:
    """Resolve producer traces and their evidence into one ordered chain."""

    def __init__(
        self,
        traces: TraceQueryService,
        *,
        artifact_resolver: ArtifactSummaryResolver,
        max_nodes: int = 24,
        max_depth: int = 8,
    ) -> None:
        if max_nodes < 1 or max_depth < 1:
            raise ValueError("provenance limits must be positive")
        self._traces = traces
        self._artifact_resolver = artifact_resolver
        self._max_nodes = max_nodes
        self._max_depth = max_depth

    def chain_for(self, artifact_ref: str) -> ProvenanceChain:
        """Return ancestors first and the requested artifact last."""

        root = artifact_ref.strip()
        if not root:
            raise ValueError("artifact reference must not be empty")
        traces = self._traces.list_traces(visibility="all")
        by_id = {trace.id: trace for trace in traces}
        producers: dict[str, list[ThoughtTrace]] = {}
        for trace in traces:
            for output in trace.outputs:
                if _is_artifact_ref(output):
                    producers.setdefault(output, []).append(trace)
        for output_traces in producers.values():
            output_traces.sort(key=lambda item: (item.created_at, item.id))

        ordered: list[ProvenanceNode] = []
        emitted: set[str] = set()
        visiting: set[str] = set()
        truncated = False

        def append(node: ProvenanceNode) -> None:
            nonlocal truncated
            if node.ref in emitted:
                return
            if len(ordered) >= self._max_nodes:
                truncated = True
                return
            emitted.add(node.ref)
            ordered.append(node)

        def visit_trace(trace: ThoughtTrace, depth: int) -> None:
            nonlocal truncated
            ref = f"trace:{trace.id}"
            if ref in emitted or ref in visiting:
                return
            if depth > self._max_depth:
                truncated = True
                return
            visiting.add(ref)
            for evidence_ref in trace.evidence_refs:
                if evidence_ref.startswith("trace:"):
                    dependency = by_id.get(evidence_ref.removeprefix("trace:"))
                    if dependency is not None:
                        visit_trace(dependency, depth + 1)
                elif _is_artifact_ref(evidence_ref):
                    visit_artifact(evidence_ref, depth + 1)
            for derived_ref in trace.derived_from:
                trace_id = derived_ref.removeprefix("trace:")
                dependency = by_id.get(trace_id)
                if dependency is not None:
                    visit_trace(dependency, depth + 1)
            visiting.remove(ref)
            append(ProvenanceNode(ref, _trace_body(trace)))

        def visit_artifact(ref: str, depth: int) -> None:
            nonlocal truncated
            if ref in emitted or ref in visiting:
                return
            if depth > self._max_depth:
                truncated = True
                return
            visiting.add(ref)
            output_traces = producers.get(ref, ())
            for producer in output_traces:
                visit_trace(producer, depth + 1)
            visiting.remove(ref)
            resolved = self._artifact_resolver.resolve(ref)
            if resolved is None and output_traces:
                resolved = output_traces[-1].summary
            append(
                ProvenanceNode(
                    ref,
                    _normalized_body(
                        resolved or "Artifact unavailable (tombstone)."
                    ),
                )
            )

        visit_artifact(root, 0)
        return ProvenanceChain(tuple(ordered), truncated=truncated)


def _trace_body(trace: ThoughtTrace) -> str:
    if trace.kind == "reflection":
        return _reflection_trace_body(trace)
    body = f"{trace.kind}: {trace.summary}"
    if trace.decision_points:
        decisions = " | ".join(trace.decision_points)
        body = f"{body} | decisions: {decisions}"
    return _normalized_body(body)


def _reflection_trace_body(trace: ThoughtTrace) -> str:
    candidate_type = trace.metadata.get("candidate_type")
    if not isinstance(candidate_type, str) or not candidate_type:
        candidate_type = "unknown"
    lines = [
        f"Generated {candidate_type} Reflection",
        f"Basis: {len(trace.evidence_refs)} referenced artifact(s)",
    ]
    assessment: list[str] = []
    composite_score = trace.metadata.get("composite_score")
    if isinstance(composite_score, (int, float)) and not isinstance(
        composite_score,
        bool,
    ):
        assessment.append(f"score={float(composite_score):.2f}")
    discussion = trace.metadata.get("discussion_approved")
    if isinstance(discussion, bool):
        assessment.append(
            f"discussion={'approved' if discussion else 'rejected'}"
        )
    elif discussion is None:
        assessment.append("discussion=not required")
    if assessment:
        lines.append("Assessment: " + " · ".join(assessment))
    if trace.decision_points:
        lines.append("Decisions:")
        lines.extend(f"- {decision}" for decision in trace.decision_points)
    return "\n".join(lines)


def _is_artifact_ref(value: str) -> bool:
    return value.startswith(_ARTIFACT_PREFIXES)


def _normalized_body(value: str) -> str:
    return " ".join(value.split())
