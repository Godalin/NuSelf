"""LLM-backed reasoning step advancer with tool support."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from langchain.agents import create_agent as _create_agent  # pyright: ignore[reportUnknownVariableType]
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, PrivateAttr

from nuself.llm import ChatLLM, ChatMessage, LangChainLLMEndpoint
from nuself.memory.query import MemoryQuery, MemoryQueryService
from nuself.reason.domain import STEP_KINDS, ReasoningStep, ReasoningThread
from nuself.reflection.repository import ReflectionRepository

import json as _json


def _log_tool_call(tool_name: str, args: dict[str, object], *, project_root: Path | None, result: str | None = None, error: str | None = None) -> None:
    """Emit a service_tool_called log event for a reasoning tool invocation."""
    from nuself.agent.tool_utils import format_tool_debug_body
    from nuself.logs import write_log_event

    body = format_tool_debug_body(args=args, result=result, error=error)
    write_log_event(
        "reasoning",
        "service_tool_called",
        body,
        project_root=project_root,
        status="completed" if error is None else "failed",
        metadata={
            "service_component": "reason_advancer",
            "tool": tool_name,
            "message_body": body,
        },
    )


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
    "Produce a concrete, meaningful reasoning step that makes genuine progress "
    "on the question. "
    "You have access to tools for gathering context: search memory, "
    "list reflections, search traces, browse other threads, and load skills. "
    "Use `load_skill` to load a service skill's behavioral policy. "
    "When you need more context, tools like reflection_list_pending and "
    "memory_search are available to help. "
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


def _step_from_data(data: dict[str, object], thread_id: str, *, tool_calls: tuple[tuple[str, dict[str, object], str | None], ...] = ()) -> ReasoningStep | None:
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
        tool_calls=tool_calls,
        confidence=confidence,
    )


def _parse_step_json(raw: str) -> dict[str, object] | None:
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


def _tool_input_to_dict(input_value: object) -> dict[str, object]:
    """Extract a dict from a tool invocation input."""
    if isinstance(input_value, dict):
        raw = cast(dict[str, object], input_value)
        inner = raw.get("args")
        if isinstance(inner, dict):
            return cast(dict[str, object], inner)
        return raw
    return {}


class _CapturingTool(BaseTool):
    """Wraps a tool and records invocations during agent execution.

    Used by ReasonAdvancer to capture tool calls from agent flow
    instead of mining them from message history afterwards.
    """

    _inner: BaseTool = PrivateAttr()
    _captured: list[tuple[str, dict[str, object], str | None]] = PrivateAttr()

    def __init__(self, inner: BaseTool, captured: list[tuple[str, dict[str, object], str | None]]) -> None:
        super().__init__(
            name=inner.name,
            description=inner.description,
            args_schema=inner.args_schema,
            return_direct=inner.return_direct,
            response_format=inner.response_format,
        )
        self._inner = inner
        self._captured = captured

    def invoke(self, input: Any, config: Any | None = None, **kwargs: Any) -> Any:  # pyright: ignore[reportUnknownParameterType]
        args = _tool_input_to_dict(input)
        try:
            result = self._inner.invoke(input, config=config, **kwargs)  # pyright: ignore[reportUnknownMemberType]
            result_text = str(result)
            if len(result_text) > 200:
                result_text = result_text[:197] + "..."
            self._captured.append((self.name, args, result_text))
            return result
        except Exception as exc:
            self._captured.append((self.name, args, str(exc)))
            raise

    def _run(self, *args: Any, **kwargs: Any) -> Any:  # pyright: ignore[reportUnknownParameterType]
        return self._inner._run(*args, **kwargs)  # pyright: ignore[reportUnknownMemberType]


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
        project_root: Path | None = None,
        memory_query_service: MemoryQueryService | None = None,
        reflection_repository: ReflectionRepository | None = None,
        readonly_tools: Sequence[Any] | None = None,
        langchain_models: tuple[LangChainLLMEndpoint, ...] | None = None,
    ) -> None:
        self._project_root = project_root
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
            captured: list[tuple[str, dict[str, object], str | None]] = []
            wrapped_tools = [_CapturingTool(t, captured) for t in self._readonly_tools]
            create_agent = cast(Any, _create_agent)
            agent = create_agent(
                model=endpoint.model,
                tools=wrapped_tools,
                system_prompt=REASON_ADVANCE_SYSTEM_PROMPT,
                response_format=ReasonStepOutput,
            )
            messages = [HumanMessage(content=_build_advance_prompt(thread))]
            result = agent.invoke({"messages": messages})
            state = cast(dict[str, object], result) if isinstance(result, dict) else {}
            for name, args, tc_result in captured:
                _log_tool_call(name, args, project_root=self._project_root, result=tc_result)
            step_tool_calls = tuple((n, a, r) for n, a, r in captured)
            structured = state.get("structured_response")
            if structured is None:
                return None
            if isinstance(structured, dict):
                return _step_from_data(cast(dict[str, object], structured), thread.id, tool_calls=step_tool_calls)
            pydantic_data = getattr(structured, "model_dump", None)
            if pydantic_data is not None:
                data = pydantic_data()
                if isinstance(data, dict):
                    return _step_from_data(cast(dict[str, object], data), thread.id, tool_calls=step_tool_calls)
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
