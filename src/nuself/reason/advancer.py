"""LLM-backed reasoning step advancer with tool support."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from threading import Lock
from typing import Any, cast

from langchain.agents import create_agent as _create_agent  # pyright: ignore[reportUnknownVariableType]
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from nuself.agent.middleware import ToolCaptureMiddleware

from nuself.llm import LangChainLLMEndpoint
from nuself.reason.domain import STEP_KINDS, TERMINAL_STATUSES, ReasoningStep, ReasoningThread
from nuself.runtime import current_runtime_context, runtime_context
from nuself.runtime.observability import report_observed_failure
from nuself.workspace import PrivateWorkspaceStore


def _empty_dict_list() -> list[dict[str, object]]:
    return []


def _current_reason_thread_id() -> str:
    thread_id = current_runtime_context().thread_id
    if thread_id is None:
        raise RuntimeError("reason tool requires an active reason thread context")
    return thread_id


def _log_tool_call(tool_name: str, args: dict[str, object], *, tool_service_map: dict[str, str] | None = None, project_root: Path | None, result: str | None = None, error: str | None = None) -> None:
    """Emit a service_tool_called log event for a reasoning tool invocation."""
    from nuself.agent.tool_utils import tool_log_metadata
    from nuself.logs import write_log_event

    service_component = (tool_service_map or {}).get(tool_name) or "reason_advancer"
    write_log_event(
        "reasoning",
        "service_tool_called",
        f"{tool_name} {'failed' if error is not None else 'completed'}",
        project_root=project_root,
        status="completed" if error is None else "failed",
        metadata=tool_log_metadata(
            args=args,
            result=result,
            error=error,
            service_component=service_component,
            tool_name=tool_name,
        ),
    )


class ReasonStepOutput(BaseModel):
    summary: str = Field(description="Concise one-sentence summary of what happened in this step")
    delta: str = Field(description="What changed in your thinking this step — the key insight or shift")
    kind: str = Field(description="One of: progress, no_change, question, synthesis, contradiction, resolution, planning")
    output: str = Field(description="Your full current thinking, analysis, or draft — the observable product of this step")
    evidence_refs: list[str] = Field(default_factory=list, description="Reference strings for sources or evidence used")
    confidence: float | None = Field(default=None, description="How confident you are in this step, from 0.0 to 1.0")
    new_findings: list[dict[str, object]] = Field(default_factory=_empty_dict_list, description="New findings or ideas to track, each with fields: label, description, kind")
    new_pending: list[dict[str, object]] = Field(default_factory=_empty_dict_list, description="New open questions or unresolved points, each with fields: label, description, kind")
    retired_findings: list[dict[str, object]] = Field(default_factory=_empty_dict_list, description="Previously tracked items that are now completed or abandoned, each with fields: label, description, kind")
    next_steps: list[dict[str, object]] = Field(default_factory=_empty_dict_list, description="Planned next actions, each with a label field")
    terminal_status: str = Field(default="continue", description="One of: continue, suggest_resolved, suggest_paused")
    terminal_reason: str = Field(default="", description="Why this terminal status was chosen; empty if continuing normally")


REASON_ADVANCE_SYSTEM_PROMPT = (
    "You are a person engaged in deep thinking. Write what you are "
    "thinking right now as output, then update your notes.\n"
    "- output: your current thoughts, analysis, or draft.\n"
    "- active_items: ideas you are tracking.\n"
    "- pending_items: open questions or unresolved points.\n"
    "- new_findings: add new ideas to active_items.\n"
    "- new_pending: add new questions to pending_items.\n"
    "- retired_findings: set aside completed or abandoned ideas.\n"
    "- delta: what changed in your thinking this step.\n"
    "- next_steps: what you plan to do next.\n"
    "- terminal_status: one of continue, suggest_resolved, suggest_paused.\n"
    "- terminal_reason: why the terminal status applies, or empty when continuing.\n"
    "- mandates: constraints you must follow.\n"
    "Advance exactly one bounded unit. For round-based simulations, debates, "
    "interviews, games, or staged discussions, produce at most one complete "
    "round per advance. Setup may happen before the first round, but do not "
    "skip ahead through multiple simulated rounds in one ReasoningStep.\n"
    "Persona speech is tool-grounded. If your output presents a persona's own "
    "utterance, answer, critique, vote, judgment, or dialogue line, you must "
    "call persona_think for that persona during this same advance and base the "
    "visible line on the tool result. You may create or update personas with "
    "persona_craft, but do not fabricate later persona speech directly in output. "
    "Use persona_list first if you are unsure which persona names or ids exist.\n"
    "Use terminal_status=suggest_resolved only when the thread goal, staged "
    "simulation, or explicit terminal condition is complete. Use "
    "terminal_status=suggest_paused when progress should stop until user input, "
    "external context, or a later time. Otherwise use terminal_status=continue. "
    "Do not rely on prose alone to signal completion.\n"
    "Always finish by producing one structured ReasonStepOutput response."
)


def build_advance_prompt(thread: ReasoningThread) -> str:
    parts = [
        f"You are thinking about: {thread.topic}",
        f"So far you have noted: {thread.working_summary}",
    ]
    mandates = thread.mandates
    if mandates:
        parts.append("You must follow these constraints:")
        for m in mandates:
            parts.append(f"  - {m}")
    items = thread.active_items
    if items:
        parts.append("Active ideas you are tracking:")
        for item in items:
            tag = f" ({item.kind})" if item.kind else ""
            desc = f" — {item.description}" if item.description else ""
            parts.append(f"  - {item.label}{tag}{desc}")
    pending = thread.pending_items
    if pending:
        parts.append("Open questions or unresolved points:")
        for item in pending:
            tag = f" ({item.kind})" if item.kind else ""
            desc = f" — {item.description}" if item.description else ""
            parts.append(f"  - {item.label}{tag}{desc}")
    nxt = thread.next_steps
    if nxt:
        parts.append("Planned next actions:")
        for item in nxt:
            parts.append(f"  - {item.label}")
    if thread.evidence_refs:
        parts.append("References you have:")
        for r in thread.evidence_refs:
            parts.append(f"  - {r}")
    parts.append("")
    parts.append("Think one bounded step forward. For round-based topics, advance at most one complete round.")
    parts.append("Write your current thoughts as output, then update your notes for the next advance.")
    return "\n".join(parts)


def build_system_prompt(thread: ReasoningThread) -> str:
    if not thread.reasoning_prompt:
        return REASON_ADVANCE_SYSTEM_PROMPT
    return f"{REASON_ADVANCE_SYSTEM_PROMPT}\n\nTopic-specific guidance:\n{thread.reasoning_prompt}"


def step_from_data(data: dict[str, object], thread_id: str, *, tool_logs: tuple[dict[str, object], ...] = ()) -> ReasoningStep | None:
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

    evidence_refs_list = _string_list(ev_refs)

    def _as_tracked_list(raw: object) -> tuple[dict[str, object], ...]:
        if not isinstance(raw, list):
            return ()
        items = cast(list[object], raw)
        return tuple(cast(dict[str, object], item) for item in items if isinstance(item, dict))

    output_raw = data.get("output")
    if not isinstance(output_raw, str):
        return None
    terminal_status_raw = data.get("terminal_status")
    terminal_status = terminal_status_raw if isinstance(terminal_status_raw, str) and terminal_status_raw in TERMINAL_STATUSES else "continue"
    terminal_reason_raw = data.get("terminal_reason")
    terminal_reason = terminal_reason_raw.strip() if isinstance(terminal_reason_raw, str) else ""

    return ReasoningStep(
        thread_id=thread_id,
        kind=kind_raw,
        summary=summary_raw.strip(),
        delta=delta_raw.strip(),
        evidence_refs=evidence_refs_list,
        output=output_raw,
        tool_logs=tool_logs,
        confidence=confidence,
        new_findings_data=_as_tracked_list(data.get("new_findings")),
        new_pending_data=_as_tracked_list(data.get("new_pending")),
        retired_findings_data=_as_tracked_list(data.get("retired_findings")),
        next_steps_data=_as_tracked_list(data.get("next_steps")),
        terminal_status=terminal_status,
        terminal_reason=terminal_reason,
    )


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in cast(list[object], value) if isinstance(item, str)]


class ReasonAdvancer:
    """LLM-backed generator of reasoning steps with tool support.

    Uses a pre-built ``create_agent`` graph with structured output
    for tool-assisted reasoning.  Workspace tools resolve the current
    thread from the shared ``RuntimeContext`` so that the same tool
    instances can be reused across threads.
    """

    def __init__(
        self,
        *,
        project_root: Path | None = None,
        workspace_store: PrivateWorkspaceStore | None = None,
        readonly_tools: Sequence[Any] | None = None,
        langchain_models: tuple[LangChainLLMEndpoint, ...] | None = None,
    ) -> None:
        self._project_root = project_root
        self._workspace_store = workspace_store
        self._readonly_tools = tuple(readonly_tools) if readonly_tools else ()
        self._langchain_models = langchain_models or ()
        self._captured: list[tuple[str, dict[str, object], str | None]] = []
        self._invoke_lock = Lock()
        self._middleware = ToolCaptureMiddleware(captured=self._captured)
        self._agent = self._build_agent()

    def _build_agent(self) -> Any:
        """Build the LangGraph agent graph once, or None if no models configured."""
        if not self._langchain_models:
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
            response_format=ToolStrategy(ReasonStepOutput),
            middleware=[self._middleware],
        )

    def advance(self, thread: ReasoningThread) -> ReasoningStep | None:
        """Generate a reasoning step for the given thread, or None on failure."""
        if self._agent is None:
            raise RuntimeError("No LangChain models configured — cannot advance reason thread")
        with self._invoke_lock:
            return self._advance(thread)

    def _advance(self, thread: ReasoningThread) -> ReasoningStep | None:
        assert self._agent is not None
        with runtime_context(thread_id=thread.id):
            try:
                self._captured.clear()
                base = build_advance_prompt(thread)
                system = SystemMessage(content=build_system_prompt(thread))
                messages = [system, HumanMessage(content=base)]
                result = self._agent.invoke({"messages": messages})
                state = cast(dict[str, object], result) if isinstance(result, dict) else {}
                for name, args, tc_result in self._captured:
                    _log_tool_call(name, args, project_root=self._project_root, result=tc_result, tool_service_map=self._tool_service_map)
                from nuself.agent.tool_utils import tool_log_metadata

                step_tool_logs = cast(
                    "tuple[dict[str, object], ...]",
                    tuple(
                        {
                            "component": "reasoning",
                            "event": "service_tool_called",
                            "message": f"{name} completed",
                            "status": "completed",
                            "metadata": tool_log_metadata(
                                args=dict(args),
                                result=result,
                                service_component=self._tool_service_map.get(name, ""),
                                tool_name=name,
                            ),
                        }
                        for name, args, result in self._captured
                    ),
                )
                structured = state.get("structured_response")
                if structured is None:
                    return None
                if isinstance(structured, dict):
                    return step_from_data(cast(dict[str, object], structured), thread.id, tool_logs=step_tool_logs)
                pydantic_data = getattr(structured, "model_dump", None)
                if pydantic_data is not None:
                    data = pydantic_data()
                    if isinstance(data, dict):
                        return step_from_data(cast(dict[str, object], data), thread.id, tool_logs=step_tool_logs)
                return None
            except Exception as exc:
                report_observed_failure(
                    exc,
                    component="reasoning",
                    event="advance_tool_failed",
                    message=f"Reason advance failed for thread {thread.id}",
                    project_root=self._project_root,
                    level="error",
                    status="failed",
                    metadata={"thread_id": thread.id},
                )
                raise

    def _build_workspace_tools(self) -> tuple[Any, ...]:
        """Build workspace tools once that resolve the active reason thread."""
        ws_store = self._workspace_store
        if ws_store is None:
            return ()
        from nuself.agent.tools import _build_workspace_tools_from_provider  # pyright: ignore[reportPrivateUsage]
        from nuself.store import ScopedWorkspace, SqliteStore

        def _resolve() -> ScopedWorkspace:
            thread_id = _current_reason_thread_id()
            wpath = ws_store.ensure(thread_id)
            sqlite = SqliteStore(wpath.database)
            return ScopedWorkspace(sqlite, ("workspace", thread_id))

        return _build_workspace_tools_from_provider(_resolve)

    def _build_persona_tools(self) -> tuple[Any, ...]:
        """Build thread-scoped persona tools that resolve the current thread."""
        if self._workspace_store is None:
            return ()

        ws_store = self._workspace_store
        from nuself.persona.tools import build_reason_persona_tools

        def _persona_root() -> Path:
            thread_id = _current_reason_thread_id()
            wpath = ws_store.ensure(thread_id)
            root = wpath.root / "persona_prompts"
            root.mkdir(parents=True, exist_ok=True)
            return root

        return build_reason_persona_tools(
            global_project_root=self._project_root,
            get_thread_persona_root=_persona_root,
        )
