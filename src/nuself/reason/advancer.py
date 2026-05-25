"""LLM-backed reasoning step advancer with tool support."""

from __future__ import annotations

from collections.abc import Sequence
from contextvars import ContextVar, Token
from pathlib import Path
from typing import Any, cast

from langchain.agents import create_agent as _create_agent  # pyright: ignore[reportUnknownVariableType]
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from nuself.agent.middleware import ToolCaptureMiddleware

from nuself.llm import ChatLLM, ChatMessage, LangChainLLMEndpoint
from nuself.memory.query import MemoryQuery, MemoryQueryService
from nuself.reason.domain import STEP_KINDS, ReasoningStep, ReasoningThread
from nuself.reflection.repository import ReflectionRepository
from nuself.workspace import PrivateWorkspaceStore

import json as _json


_current_reason_thread_id: ContextVar[str] = ContextVar("reason_thread_id")


def _log_tool_call(tool_name: str, args: dict[str, object], *, tool_service_map: dict[str, str] | None = None, project_root: Path | None, result: str | None = None, error: str | None = None) -> None:
    """Emit a service_tool_called log event for a reasoning tool invocation."""
    from nuself.agent.tool_utils import format_tool_debug_body
    from nuself.logs import write_log_event

    body = format_tool_debug_body(args=args, result=result, error=error)
    service_component = (tool_service_map or {}).get(tool_name) or "reason_advancer"
    write_log_event(
        "reasoning",
        "service_tool_called",
        body,
        project_root=project_root,
        status="completed" if error is None else "failed",
        metadata={
            "service_component": service_component,
            "tool": tool_name,
            "message_body": body,
        },
    )


class ReasonStepOutput(BaseModel):
    summary: str
    delta: str
    kind: str
    output: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float | None = None
    new_findings: list[dict[str, object]] = Field(default_factory=list)
    new_pending: list[dict[str, object]] = Field(default_factory=list)
    retired_findings: list[dict[str, object]] = Field(default_factory=list)
    next_steps: list[dict[str, object]] = Field(default_factory=list)


REASON_ADVANCE_SYSTEM_PROMPT = (
    "You are an assistant that advances a long-running thinking thread. "
    "Produce a concrete, meaningful step that makes genuine progress. "
    ""
    "The thread has state that you update:"
    ""
    "- active_items — things being tracked. Each item has:"
    "  label (short name), description (optional detail), kind (free-text tag),"
    "  and status."
    "- pending_items — unresolved items. Same structure."
    "- next_steps — planned actions. Same structure."
    "- mandates — requirements you must follow on this advance."
    ""
    "Each step has:"
    "- summary — what this step accomplished."
    "- delta — what changed since the last step."
    "- kind — one of: progress, no_change, question, planning, synthesis,"
    "  contradiction, or resolution."
    "- output — the visible result or product of this step (e.g. a"
    "  paragraph of story, a candidate answer, a design sketch)."
    "  Empty if the step is purely internal."
    "- new_findings — items to add to active_items."
    "- new_pending — items to add to pending_items."
    "- retired_findings — items to remove from active_items."
    "- next_steps — items to add to next_steps."
    "- evidence_refs — optional references to memory, reflection, or trace."
    ""
    "Use load_skill to load service skills. Use load_skill(\"persona\") to"
    "get different perspectives on the current problem."
)


def _build_advance_prompt(thread: ReasoningThread) -> str:
    parts = [f"Topic: {thread.topic}"]
    parts.append(f"Working summary: {thread.working_summary}")
    mandates = thread.mandates
    if mandates:
        parts.append("Mandates (you MUST follow these on every advance):")
        for m in mandates:
            parts.append(f"  - {m}")
    items = thread.active_items
    if items:
        parts.append("Active items:")
        for item in items:
            tag = f" ({item.kind})" if item.kind else ""
            desc = f" — {item.description}" if item.description else ""
            parts.append(f"  - {item.label}{tag}{desc}")
    pending = thread.pending_items
    if pending:
        parts.append("Pending items:")
        for item in pending:
            tag = f" ({item.kind})" if item.kind else ""
            desc = f" — {item.description}" if item.description else ""
            parts.append(f"  - {item.label}{tag}{desc}")
    nxt = thread.next_steps
    if nxt:
        parts.append("Next steps:")
        for item in nxt:
            parts.append(f"  - {item.label}")
    if thread.evidence_refs:
        parts.append("References:")
        for r in thread.evidence_refs:
            parts.append(f"  - {r}")
    parts.append("")
    parts.append("Produce the next step for this thread.")
    return "\n".join(parts)


def _step_from_data(data: dict[str, object], thread_id: str, *, tool_calls: tuple[tuple[str, str, dict[str, object], str | None], ...] = ()) -> ReasoningStep | None:
    kind_raw = data.get("kind")
    summary_raw = data.get("summary")
    delta_raw = data.get("delta")
    if not isinstance(kind_raw, str) or kind_raw not in STEP_KINDS:
        return None
    if not isinstance(summary_raw, str) or not summary_raw.strip():
        return None
    if not isinstance(delta_raw, str):
        return None

    ev_refs = data.get("evidence_refs")
    conf_raw = data.get("confidence")

    confidence: float | None = None
    if isinstance(conf_raw, int | float):
        confidence = max(0.0, min(float(conf_raw), 1.0))

    evidence_refs_list: list[str] = list(cast(list[str], ev_refs)) if isinstance(ev_refs, list) else []

    def _as_tracked_list(raw: object) -> tuple[dict[str, object], ...]:
        if not isinstance(raw, list):
            return ()
        return tuple(cast(dict[str, object], item) for item in raw if isinstance(item, dict))

    # Parse both old string-list format and new TrackedItem dict format.
    # ReasoningStep's property fallbacks (new_findings → new_hypotheses etc.)
    # bridge old data until the LLM adapts to the new schema.
    new_hyp = data.get("new_hypotheses")
    new_q = data.get("new_open_questions")
    new_hypotheses: list[str] = list(cast(list[str], new_hyp)) if isinstance(new_hyp, list) else []
    new_open_questions: list[str] = list(cast(list[str], new_q)) if isinstance(new_q, list) else []

    return ReasoningStep(
        thread_id=thread_id,
        kind=kind_raw,
        summary=summary_raw.strip(),
        delta=delta_raw.strip(),
        new_hypotheses=new_hypotheses,
        new_open_questions=new_open_questions,
        evidence_refs=evidence_refs_list,
        output=str(data.get("output", "")),
        tool_calls=tool_calls,
        confidence=confidence,
        new_findings_data=_as_tracked_list(data.get("new_findings")),
        new_pending_data=_as_tracked_list(data.get("new_pending")),
        retired_findings_data=_as_tracked_list(data.get("retired_findings")),
        next_steps_data=_as_tracked_list(data.get("next_steps")),
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


class ReasonAdvancer:
    """LLM-backed generator of reasoning steps.

    When LangChain models and tools are available, uses a pre-built
    ``create_agent`` graph with structured output for tool-assisted
    reasoning.  Falls back to raw ``ChatLLM.complete()`` otherwise.

    The LangGraph agent is built once in ``__init__``.  Workspace tools
    resolve the current thread from a ``ContextVar`` so that the same
    tool instances can be reused across threads.
    """

    def __init__(
        self,
        llm: ChatLLM,
        *,
        project_root: Path | None = None,
        memory_query_service: MemoryQueryService | None = None,
        reflection_repository: ReflectionRepository | None = None,
        workspace_store: PrivateWorkspaceStore | None = None,
        readonly_tools: Sequence[Any] | None = None,
        langchain_models: tuple[LangChainLLMEndpoint, ...] | None = None,
    ) -> None:
        self._project_root = project_root
        self._llm = llm
        self._memory_query_service = memory_query_service
        self._reflection_repository = reflection_repository
        self._workspace_store = workspace_store
        self._readonly_tools = tuple(readonly_tools) if readonly_tools else ()
        self._langchain_models = langchain_models or ()
        self._captured: list[tuple[str, dict[str, object], str | None]] = []
        self._middleware = ToolCaptureMiddleware(captured=self._captured)
        self._agent = self._build_agent()

    def _build_agent(self) -> Any:
        """Build the LangGraph agent graph once (or return None for fallback)."""
        if not self._langchain_models or not self._readonly_tools:
            return None
        endpoint = self._langchain_models[0]
        ws_tools = self._build_workspace_tools()
        persona_tools = self._build_persona_tools()
        all_tools = list(self._readonly_tools) + list(ws_tools) + list(persona_tools)
        create_agent = cast(Any, _create_agent)
        self._tool_service_map: dict[str, str] = {}
        for tool in all_tools:
            if hasattr(tool, "metadata") and tool.metadata and "service_component" in tool.metadata:
                self._tool_service_map[tool.name] = tool.metadata["service_component"]
        return create_agent(
            model=endpoint.model,
            tools=all_tools,
            system_prompt=REASON_ADVANCE_SYSTEM_PROMPT,
            response_format=ReasonStepOutput,
            middleware=[self._middleware],
        )

    def advance(self, thread: ReasoningThread) -> ReasoningStep | None:
        """Generate a reasoning step for the given thread, or None on failure."""
        if self._agent is not None:
            return self._advance_with_tools(thread)
        return self._advance_raw(thread)

    def _advance_with_tools(self, thread: ReasoningThread) -> ReasoningStep | None:
        assert self._agent is not None
        token: Token[str] = _current_reason_thread_id.set(thread.id)
        try:
            self._captured.clear()
            messages = [HumanMessage(content=_build_advance_prompt(thread))]
            result = self._agent.invoke({"messages": messages})
            state = cast(dict[str, object], result) if isinstance(result, dict) else {}
            for name, args, tc_result in self._captured:
                _log_tool_call(name, args, project_root=self._project_root, result=tc_result, tool_service_map=self._tool_service_map)
            step_tool_calls = tuple(
                (name, self._tool_service_map.get(name, ""), dict(args), result)
                for name, args, result in self._captured
            )
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
        finally:
            _current_reason_thread_id.reset(token)

    def _build_workspace_tools(self) -> tuple[Any, ...]:
        """Build workspace tools once that resolve the thread from ContextVar."""
        ws_store = self._workspace_store
        if ws_store is None:
            return ()
        from nuself.agent.tools import _build_workspace_tools_from_provider  # pyright: ignore[reportPrivateUsage]
        from nuself.store import ScopedWorkspace, SqliteStore

        def _resolve() -> ScopedWorkspace:
            thread_id = _current_reason_thread_id.get()
            wpath = ws_store.ensure(thread_id)
            sqlite = SqliteStore(wpath.database)
            return ScopedWorkspace(sqlite, ("workspace", thread_id))

        return _build_workspace_tools_from_provider(_resolve)

    def _build_persona_tools(self) -> tuple[Any, ...]:
        """Build thread-scoped persona tools that resolve the current thread."""
        if self._workspace_store is None:
            return ()

        from nuself.persona.tools import build_reason_persona_tools

        def _persona_root() -> Path:
            thread_id = _current_reason_thread_id.get()
            wpath = self._workspace_store.ensure(thread_id)
            root = wpath.root / "persona_prompts"
            root.mkdir(parents=True, exist_ok=True)
            return root

        return build_reason_persona_tools(
            global_project_root=self._project_root,
            get_thread_persona_root=_persona_root,
        )

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
        """Collect relevant memory and reflection context for the thread topic."""
        parts: list[str] = []

        if self._memory_query_service is not None:
            try:
                query = MemoryQuery(text=thread.topic, limit=5)
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
