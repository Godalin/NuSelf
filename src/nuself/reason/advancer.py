"""LLM-backed reasoning step advancer."""

from __future__ import annotations

from typing import cast

from nuself.llm import ChatLLM, ChatMessage
from nuself.reason.domain import ReasoningStep, ReasoningThread, StepKind


REASON_ADVANCE_SYSTEM_PROMPT = (
    "You are a reasoning assistant that advances a long-running reasoning thread. "
    "Given the current state of a reasoning thread and any relevant reference context, "
    "produce a structured step that makes progress on the question. "
    "The step must include: summary, delta, kind (one of progress, no_change, question, "
    "synthesis, contradiction, resolution), new_hypotheses, new_open_questions, evidence_refs. "
    "Use the provided reference context (memory entries, past reflections, traces) to inform "
    "your reasoning where applicable. Reply with a JSON object only, no markdown, no explanation."
)


def _build_advance_prompt(thread: ReasoningThread, *, context: str = "") -> str:
    parts = [f"Question: {thread.question}"]
    parts.append(f"Working summary: {thread.working_summary}")
    if thread.hypotheses:
        parts.append("Hypotheses:")
        for h in thread.hypotheses:
            parts.append(f"  - {h}")
    if thread.open_questions:
        parts.append("Open questions:")
        for q in thread.open_questions:
            parts.append(f"  - {q}")
    if thread.evidence_refs:
        parts.append("Evidence references:")
        for r in thread.evidence_refs:
            parts.append(f"  - {r}")
    if context:
        parts.append("")
        parts.append("Reference context (memories, reflections, traces):")
        parts.append(context)
    parts.append("")
    parts.append("Produce a reasoning step as a JSON object with fields: summary, delta, kind, new_hypotheses, new_open_questions, evidence_refs, confidence.")
    return "\n".join(parts)


_REQUIRED_STEP_FIELDS = {"summary", "delta", "kind"}
_VALID_KINDS: set[str] = {"progress", "no_change", "question", "synthesis", "contradiction", "resolution"}


def _parse_step_json(raw: str) -> dict[str, object] | None:
    import json as _json

    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        parsed = _json.loads(text)
    except _json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return cast(dict[str, object], parsed)


def _validate_step_json(data: dict[str, object]) -> bool:
    if not _REQUIRED_STEP_FIELDS.issubset(data.keys()):
        return False
    kind = data.get("kind")
    if not isinstance(kind, str) or kind not in _VALID_KINDS:
        return False
    if not isinstance(data.get("summary"), str):
        return False
    if not isinstance(data.get("delta"), str):
        return False
    return True


class ReasonAdvancer:
    """LLM-backed generator of reasoning steps."""

    def __init__(
        self,
        llm: ChatLLM,
        *,
        memory_query_service: object | None = None,
        reflection_repository: object | None = None,
    ) -> None:
        self._llm = llm
        self._memory_query_service = memory_query_service
        self._reflection_repository = reflection_repository

    def advance(self, thread: ReasoningThread) -> ReasoningStep | None:
        """Generate a reasoning step for the given thread, or None on failure."""
        context = self._gather_context(thread)
        prompt = _build_advance_prompt(thread, context=context)
        raw = self._llm.complete([
            ChatMessage(role="system", content=REASON_ADVANCE_SYSTEM_PROMPT),
            ChatMessage(role="user", content=prompt),
        ])
        if not raw.strip():
            return None

        data = _parse_step_json(raw)
        if data is None or not _validate_step_json(data):
            return None

        kind = cast(StepKind, data["kind"])
        summary = cast(str, data["summary"])
        delta = cast(str, data["delta"])
        new_hyp = data.get("new_hypotheses")
        new_q = data.get("new_open_questions")
        ev_refs = data.get("evidence_refs")
        conf_raw = data.get("confidence")

        confidence: float | None = None
        if isinstance(conf_raw, int | float):
            confidence = max(0.0, min(float(conf_raw), 1.0))

        new_hypotheses: list[str] = list(cast(list[str], new_hyp)) if isinstance(new_hyp, list) else []
        new_open_questions: list[str] = list(cast(list[str], new_q)) if isinstance(new_q, list) else []
        evidence_refs: list[str] = list(cast(list[str], ev_refs)) if isinstance(ev_refs, list) else []

        return ReasoningStep(
            thread_id=thread.id,
            kind=kind,
            summary=summary.strip(),
            delta=delta.strip(),
            new_hypotheses=new_hypotheses,
            new_open_questions=new_open_questions,
            evidence_refs=evidence_refs,
            confidence=confidence,
        )

    def _gather_context(self, thread: ReasoningThread) -> str:
        """Collect relevant memory and reflection context for the thread question."""
        parts: list[str] = []

        if self._memory_query_service is not None:
            try:
                from nuself.memory.query import MemoryQuery
                query = MemoryQuery(text=thread.question, limit=5)
                packed = self._memory_query_service.pack(query)
                if packed.text:
                    parts.append(packed.text)
            except Exception:
                pass

        if self._reflection_repository is not None:
            try:
                entries = self._reflection_repository.list(status=None)
                recent = entries[:5]
                if recent:
                    ref_lines = ["Recent reflection entries:"]
                    for e in recent:
                        ref_lines.append(
                            f"  - [{e.status}] {e.title} (type={e.candidate_type}, "
                            f"confidence={e.confidence:.2f})"
                        )
                    parts.append("\n".join(ref_lines))
            except Exception:
                pass

        return "\n\n".join(parts)
