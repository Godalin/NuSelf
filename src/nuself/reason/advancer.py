"""LLM-backed reasoning step advancer with tool support."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from langchain.agents import create_agent as _create_agent  # pyright: ignore[reportUnknownVariableType]
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from nuself.llm import ChatLLM, ChatMessage, LangChainLLMEndpoint
from nuself.memory.query import MemoryQuery, MemoryQueryService
from nuself.reason.domain import STEP_KINDS, ReasoningStep, ReasoningThread
from nuself.reflection.repository import ReflectionRepository


class ReasonStepOutput(BaseModel):
    summary: str
    delta: str
    kind: str
    new_hypotheses: list[str] = Field(default_factory=list)
    new_open_questions: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float | None = None


REASON_ADVANCE_SYSTEM_PROMPT = (
    "You are a reasoning assistant that advances a long-running reasoning thread. "
    "Given the current state of a reasoning thread, produce a structured step "
    "that makes progress on the question. "
    "You have access to tools for looking up relevant context: search memory, "
    "list reflections, search traces, and browse other reasoning threads. "
    "Use these tools to gather information before producing your step when needed. "
    "The step must include: summary, delta, kind (one of progress, no_change, question, "
    "synthesis, contradiction, resolution), new_hypotheses, new_open_questions, evidence_refs."
)


def _build_advance_prompt(thread: ReasoningThread) -> str:
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
    parts.append("")
    parts.append("Produce a structured reasoning step for this thread.")
    return "\n".join(parts)


def _step_from_data(data: dict[str, object], thread_id: str) -> ReasoningStep | None:
    kind_raw = data.get("kind")
    summary_raw = data.get("summary")
    delta_raw = data.get("delta")
    if not isinstance(kind_raw, str) or kind_raw not in STEP_KINDS:
        return None
    if not isinstance(summary_raw, str) or not summary_raw.strip():
        return None
    if not isinstance(delta_raw, str):
        return None

    new_hyp = data.get("new_hypotheses")
    new_q = data.get("new_open_questions")
    ev_refs = data.get("evidence_refs")
    conf_raw = data.get("confidence")

    confidence: float | None = None
    if isinstance(conf_raw, int | float):
        confidence = max(0.0, min(float(conf_raw), 1.0))

    new_hypotheses: list[str] = list(cast(list[str], new_hyp)) if isinstance(new_hyp, list) else []
    new_open_questions: list[str] = list(cast(list[str], new_q)) if isinstance(new_q, list) else []
    evidence_refs_list: list[str] = list(cast(list[str], ev_refs)) if isinstance(ev_refs, list) else []

    return ReasoningStep(
        thread_id=thread_id,
        kind=kind_raw,
        summary=summary_raw.strip(),
        delta=delta_raw.strip(),
        new_hypotheses=new_hypotheses,
        new_open_questions=new_open_questions,
        evidence_refs=evidence_refs_list,
        confidence=confidence,
    )


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


class ReasonAdvancer:
    """LLM-backed generator of reasoning steps.

    When LangChain models and tools are available, uses create_agent with
    structured output for tool-assisted reasoning.  Falls back to raw
    ChatLLM.complete() otherwise.
    """

    def __init__(
        self,
        llm: ChatLLM,
        *,
        memory_query_service: MemoryQueryService | None = None,
        reflection_repository: ReflectionRepository | None = None,
        readonly_tools: Sequence[Any] | None = None,
        langchain_models: tuple[LangChainLLMEndpoint, ...] | None = None,
    ) -> None:
        self._llm = llm
        self._memory_query_service = memory_query_service
        self._reflection_repository = reflection_repository
        self._readonly_tools = tuple(readonly_tools) if readonly_tools else ()
        self._langchain_models = langchain_models or ()

    def advance(self, thread: ReasoningThread) -> ReasoningStep | None:
        """Generate a reasoning step for the given thread, or None on failure."""
        if self._langchain_models and self._readonly_tools:
            return self._advance_with_tools(thread)
        return self._advance_raw(thread)

    def _advance_with_tools(self, thread: ReasoningThread) -> ReasoningStep | None:
        if not self._langchain_models:
            return self._advance_raw(thread)
        endpoint = self._langchain_models[0]

        try:
            create_agent = cast(Any, _create_agent)
            agent = create_agent(
                model=endpoint.model,
                tools=list(self._readonly_tools),
                system_prompt=REASON_ADVANCE_SYSTEM_PROMPT,
                response_format=ReasonStepOutput,
            )
            messages = [HumanMessage(content=_build_advance_prompt(thread))]
            result = agent.invoke({"messages": messages})
            state = cast(dict[str, object], result) if isinstance(result, dict) else {}
            structured = state.get("structured_response")
            if structured is None:
                return None
            if isinstance(structured, dict):
                return _step_from_data(cast(dict[str, object], structured), thread.id)
            pydantic_data = getattr(structured, "model_dump", None)
            if pydantic_data is not None:
                data = pydantic_data()
                if isinstance(data, dict):
                    return _step_from_data(cast(dict[str, object], data), thread.id)
            return None
        except Exception:
            return self._advance_raw(thread)

    def _advance_raw(self, thread: ReasoningThread) -> ReasoningStep | None:
        """Fallback: raw ChatLLM call with pre-injected context."""
        context = self._gather_context(thread)
        prompt_lines = [_build_advance_prompt(thread)]
        if context:
            prompt_lines.append("")
            prompt_lines.append("Reference context (memories, reflections, traces):")
            prompt_lines.append(context)
            prompt_lines.append("")
            prompt_lines.append("Reply with a JSON object only, no markdown, no explanation.")
        prompt = "\n".join(prompt_lines)
        raw = self._llm.complete([
            ChatMessage(role="system", content=REASON_ADVANCE_SYSTEM_PROMPT),
            ChatMessage(role="user", content=prompt),
        ])
        if not raw.strip():
            return None

        data = _parse_step_json(raw)
        if data is None:
            return None
        return _step_from_data(data, thread.id)

    def _gather_context(self, thread: ReasoningThread) -> str:
        """Collect relevant memory and reflection context for the thread question."""
        parts: list[str] = []

        if self._memory_query_service is not None:
            try:
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
