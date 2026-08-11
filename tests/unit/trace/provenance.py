"""Ordered provenance-chain query tests."""

from __future__ import annotations

from pathlib import Path

from nuself.config.settings import runtime_paths
from nuself.trace.model import ThoughtTrace
from nuself.trace.provenance import ProvenanceService
from nuself.trace.repository import TraceRepository
from nuself.trace.service import TraceQueryService
from tests.backend import owned_backend


class _Resolver:
    def __init__(self, summaries: dict[str, str]) -> None:
        self._summaries = summaries

    def resolve(self, artifact_ref: str) -> str | None:
        return self._summaries.get(artifact_ref)


def _repository(root: Path) -> TraceRepository:
    return TraceRepository(
        runtime_paths(root),
        backend=owned_backend(root),
    )


def test_chain_orders_turn_traces_memory_and_reflection(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    chat = repository.save_trace(
        ThoughtTrace(
            id="trace-chat",
            kind="chat_turn",
            title="Chat turn",
            summary="The committed chat turn.",
            outputs=("conversation_turn:turn-1",),
        )
    )
    memory = repository.save_trace(
        ThoughtTrace(
            id="trace-memory",
            kind="memory_update",
            title="Memory update",
            summary="A durable preference.",
            evidence_refs=(
                "conversation_turn:turn-1",
                f"trace:{chat.id}",
            ),
            outputs=("memory:mem-1",),
        )
    )
    reflection = repository.save_trace(
        ThoughtTrace(
            id="trace-reflection",
            kind="reflection",
            title="Reflection",
            summary="A new connection.",
            evidence_refs=("memory:mem-1",),
            outputs=("reflection:refl-1",),
            decision_points=("Relevance gate passed.",),
            metadata={
                "candidate_type": "connection",
                "composite_score": 0.8,
                "discussion_approved": None,
            },
        )
    )
    service = ProvenanceService(
        TraceQueryService(repository),
        artifact_resolver=_Resolver(
            {
                "conversation_turn:turn-1": "user: remember this | assistant: noted",
                "memory:mem-1": "Preference: durable preference",
                "reflection:refl-1": "Connection: a new connection",
            }
        ),
    )

    chain = service.chain_for("reflection:refl-1")

    assert [node.ref for node in chain.nodes] == [
        f"trace:{chat.id}",
        "conversation_turn:turn-1",
        f"trace:{memory.id}",
        "memory:mem-1",
        f"trace:{reflection.id}",
        "reflection:refl-1",
    ]
    assert chain.nodes[-2].body.startswith(
        "Generated connection Reflection · evidence=1 · score=0.80"
    )
    assert "decisions: Relevance gate passed." in chain.nodes[-2].body
    assert "A new connection." not in chain.nodes[-2].body
    assert chain.nodes[-1].body == "Connection: a new connection"
    assert chain.truncated is False


def test_chain_is_cycle_safe_deduplicated_and_bounded(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.save_trace(
        ThoughtTrace(
            id="trace-a",
            kind="memory_update",
            title="A",
            summary="A summary",
            evidence_refs=("memory:b",),
            outputs=("memory:a",),
        )
    )
    repository.save_trace(
        ThoughtTrace(
            id="trace-b",
            kind="memory_update",
            title="B",
            summary="B summary",
            evidence_refs=("memory:a",),
            outputs=("memory:b",),
        )
    )
    service = ProvenanceService(
        TraceQueryService(repository),
        artifact_resolver=_Resolver({}),
        max_nodes=3,
    )

    chain = service.chain_for("memory:a")

    assert len(chain.nodes) == 3
    assert len({node.ref for node in chain.nodes}) == 3
    assert chain.truncated is True


def test_chain_orders_reason_step_memory_and_reflection(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    reason = repository.save_trace(
        ThoughtTrace(
            id="trace-reason",
            kind="reason_step",
            title="Reason step",
            summary="A committed reasoning conclusion.",
            outputs=("reason_step:step-1",),
        )
    )
    memory = repository.save_trace(
        ThoughtTrace(
            id="trace-memory",
            kind="memory_update",
            title="Memory update",
            summary="Conclusion promoted to memory.",
            evidence_refs=("reason_step:step-1",),
            outputs=("memory:mem-1",),
        )
    )
    reflection = repository.save_trace(
        ThoughtTrace(
            id="trace-reflection",
            kind="reflection",
            title="Reflection",
            summary="Reflection derived from the conclusion.",
            evidence_refs=("memory:mem-1",),
            outputs=("reflection:refl-1",),
        )
    )
    service = ProvenanceService(
        TraceQueryService(repository),
        artifact_resolver=_Resolver(
            {
                "memory:mem-1": "Conclusion: promoted memory",
                "reflection:refl-1": "Reflection: derived insight",
            }
        ),
    )

    chain = service.chain_for("reflection:refl-1")

    assert [node.ref for node in chain.nodes] == [
        f"trace:{reason.id}",
        "reason_step:step-1",
        f"trace:{memory.id}",
        "memory:mem-1",
        f"trace:{reflection.id}",
        "reflection:refl-1",
    ]
    assert chain.nodes[1].body == "A committed reasoning conclusion."


def test_chain_keeps_an_explicit_tombstone(tmp_path: Path) -> None:
    service = ProvenanceService(
        TraceQueryService(_repository(tmp_path)),
        artifact_resolver=_Resolver({}),
    )

    chain = service.chain_for("memory:missing")

    assert chain.nodes[0].ref == "memory:missing"
    assert "tombstone" in chain.nodes[0].body


def test_chain_preserves_complete_normalized_artifact_body(tmp_path: Path) -> None:
    body = "First paragraph.\n\n" + "complete evidence " * 40
    service = ProvenanceService(
        TraceQueryService(_repository(tmp_path)),
        artifact_resolver=_Resolver({"memory:long": body}),
    )

    chain = service.chain_for("memory:long")

    assert chain.nodes[0].body == " ".join(body.split())
    assert len(chain.nodes[0].body) > 240
    assert not chain.nodes[0].body.endswith("…")
