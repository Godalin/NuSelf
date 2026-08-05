"""LLM-backed reasoning step advancer with tool support."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any, cast

from langchain.agents import create_agent as _create_agent  # pyright: ignore[reportUnknownVariableType]
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from nuself.agent.errors import AgentInvalidOutputError, AgentProtocolError
from nuself.agent.failover import invoke_agent_endpoint
from nuself.agent.text import LangChainTextAgent
from nuself.agent.middleware import ToolCaptureMiddleware, ToolOutcome
from nuself.agent.tool_audit import ToolOutcomeProjection
from nuself.agent.structured import require_structured_response
from nuself.agent.tool_utils import (
    index_tool_service_components,
)
from nuself.config.settings import RuntimePaths

from nuself.agent.endpoint import LangChainLLMEndpoint
from nuself.reason.model import (
    ReasoningStep,
    ReasoningThread,
    StepKind,
    TerminalStatus,
)
from nuself.reason.audit import REASON_AUDIT
from nuself.reason.errors import ReasonAdvanceError
from nuself.reason.service import ReasonService
from nuself.persona.service import PersonaService
from nuself.runtime.context import current_runtime_context, runtime_context
from nuself.runtime.feature.execution import FeatureExecutor
from nuself.trace.service import TraceRecorder

if TYPE_CHECKING:
    from nuself.storage.workspace import ScopedWorkspace


def _current_reason_thread_id() -> str:
    thread_id = current_runtime_context().reason_id
    if thread_id is None:
        raise RuntimeError("reason tool requires an active reason thread context")
    return thread_id


def _log_tool_outcome(
    outcome: ToolOutcome,
    *,
    tool_service_map: dict[str, str] | None = None,
    project_root: Path | None,
) -> ToolOutcomeProjection:
    """Emit a service_tool_called log event for a reasoning tool invocation."""
    service_component = (
        (tool_service_map or {}).get(outcome.name) or "reason_advancer"
    )
    projection = ToolOutcomeProjection(
        component="reasoning",
        service_component=service_component,
        outcome=outcome,
    )
    projection.write_observed(project_root=project_root)
    return projection


class TrackedItemOutput(BaseModel):
    """Strict generated tracked-item response."""

    model_config = ConfigDict(strict=True, extra="forbid")

    label: str = Field(min_length=1)
    description: str = ""
    kind: str = ""
    status: str = "active"


class ReasonStepOutput(BaseModel):
    """Framework-native structured response for one reason advance."""

    model_config = ConfigDict(strict=True, extra="forbid")

    summary: str = Field(description="Concise one-sentence summary of what happened in this step")
    delta: str = Field(description="What changed in your thinking this step — the key insight or shift")
    kind: StepKind = Field(description="One of: progress, no_change, question, synthesis, contradiction, resolution, planning")
    output: str = Field(description="Your full current thinking, analysis, or draft — the observable product of this step")
    evidence_refs: list[str] = Field(default_factory=list, description="Reference strings for sources or evidence used")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0, description="How confident you are in this step, from 0.0 to 1.0")
    new_findings: list[TrackedItemOutput] = Field(default_factory=list[TrackedItemOutput], description="New findings or ideas to track")
    new_pending: list[TrackedItemOutput] = Field(default_factory=list[TrackedItemOutput], description="New open questions or unresolved points")
    retired_findings: list[TrackedItemOutput] = Field(default_factory=list[TrackedItemOutput], description="Previously tracked items that are now completed or abandoned")
    next_steps: list[TrackedItemOutput] = Field(default_factory=list[TrackedItemOutput], description="Planned next actions")
    terminal_status: TerminalStatus = Field(default="continue", description="One of: continue, suggest_resolved, suggest_paused")
    terminal_reason: str = Field(default="", description="Why this terminal status was chosen; empty if continuing normally")

    def to_step(
        self,
        thread_id: str,
        *,
        tool_logs: tuple[dict[str, object], ...] = (),
    ) -> ReasoningStep:
        def tracked(
            items: list[TrackedItemOutput],
        ) -> tuple[dict[str, object], ...]:
            return tuple(
                cast(dict[str, object], item.model_dump())
                for item in items
            )

        return ReasoningStep(
            thread_id=thread_id,
            kind=self.kind,
            summary=self.summary.strip(),
            delta=self.delta.strip(),
            evidence_refs=self.evidence_refs,
            output=self.output,
            tool_logs=tool_logs,
            confidence=self.confidence,
            new_findings_data=tracked(self.new_findings),
            new_pending_data=tracked(self.new_pending),
            retired_findings_data=tracked(self.retired_findings),
            next_steps_data=tracked(self.next_steps),
            terminal_status=self.terminal_status,
            terminal_reason=self.terminal_reason.strip(),
        )


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
        paths: RuntimePaths,
        reason_service: ReasonService,
        persona_service: PersonaService,
        trace_recorder: TraceRecorder,
        feature_executor: FeatureExecutor,
        readonly_tools: Sequence[BaseTool] | None = None,
        langchain_models: tuple[LangChainLLMEndpoint, ...] | None = None,
    ) -> None:
        self._paths = paths
        self._project_root = paths.authority_root
        self._reason_service = reason_service
        self._persona_service = persona_service
        self._trace_recorder = trace_recorder
        self._feature_executor = feature_executor
        self._readonly_tools = tuple(readonly_tools) if readonly_tools else ()
        self._langchain_models = langchain_models or ()
        self._captured: list[ToolOutcome] = []
        self._invoke_lock = Lock()
        self._middleware = ToolCaptureMiddleware(captured=self._captured)
        self._agents = self._build_agents()

    def _build_agents(
        self,
    ) -> tuple[tuple[LangChainLLMEndpoint, Any], ...]:
        """Build one equivalent LangGraph agent per configured endpoint."""
        if not self._langchain_models:
            return ()
        ws_tools = self._build_workspace_tools()
        persona_tools = self._build_persona_tools()
        all_tools = list(self._readonly_tools) + list(ws_tools) + list(persona_tools)
        create_agent = cast(Any, _create_agent)
        self._tool_service_map = index_tool_service_components(all_tools)
        return tuple(
            (
                endpoint,
                create_agent(
                    model=endpoint.model,
                    tools=all_tools,
                    response_format=ToolStrategy(ReasonStepOutput),
                    middleware=[self._middleware],
                ),
            )
            for endpoint in self._langchain_models
        )

    def advance(self, thread: ReasoningThread) -> ReasoningStep | None:
        """Generate a reasoning step for the given thread, or None on failure."""
        if not self._agents:
            raise ReasonAdvanceError(
                "No LangChain models configured — cannot advance reason thread"
            )
        with self._invoke_lock:
            return self._advance(thread)

    def _advance(self, thread: ReasoningThread) -> ReasoningStep | None:
        assert self._agents
        with runtime_context(reason_id=thread.id):
            try:
                self._captured.clear()
                base = build_advance_prompt(thread)
                system = SystemMessage(content=build_system_prompt(thread))
                messages = [system, HumanMessage(content=base)]
                agents = {
                    endpoint.index: agent
                    for endpoint, agent in self._agents
                }

                def invoke(endpoint: LangChainLLMEndpoint) -> object:
                    try:
                        return agents[endpoint.index].invoke(
                            {"messages": messages}
                        )
                    except Exception as exc:
                        if self._captured:
                            REASON_AUDIT.failure(
                                exc,
                                event=(
                                    "llm_failover_suppressed_after_tool_call"
                                ),
                                project_root=self._project_root,
                                metadata={},
                            )
                            raise ReasonAdvanceError(
                                "Reason endpoint failover suppressed after "
                                "tool execution"
                            ) from exc
                        raise

                try:
                    result = invoke_agent_endpoint(
                        tuple(
                            endpoint
                            for endpoint, _agent in self._agents
                        ),
                        invoke,
                        project_root=self._project_root,
                        component="reasoning",
                    )
                except Exception:
                    self._project_tool_outcomes()
                    raise
                step_tool_logs = self._project_tool_outcomes()
                try:
                    structured = require_structured_response(
                        result,
                        ReasonStepOutput,
                    )
                except (
                    AgentInvalidOutputError,
                    AgentProtocolError,
                ) as exc:
                    raise ReasonAdvanceError(
                        "Reason agent did not return ReasonStepOutput"
                    ) from exc
                return structured.to_step(
                    thread.id,
                    tool_logs=step_tool_logs,
                )
            except Exception as exc:
                REASON_AUDIT.failure(
                    exc,
                    event="advance_failed",
                    project_root=self._project_root,
                    metadata={},
                )
                raise

    def _project_tool_outcomes(
        self,
    ) -> tuple[dict[str, object], ...]:
        snapshots: list[dict[str, object]] = []
        for outcome in self._captured:
            projection = _log_tool_outcome(
                outcome,
                project_root=self._project_root,
                tool_service_map=self._tool_service_map,
            )
            snapshots.append(projection.to_snapshot())
        return tuple(snapshots)

    def _build_workspace_tools(self) -> tuple[BaseTool, ...]:
        """Build workspace tools once that resolve the active reason thread."""
        from nuself.agent.tools.workspace import (
            build_workspace_tools_from_provider,
        )

        return build_workspace_tools_from_provider(
            self._thread_workspace,
            executor=self._feature_executor,
        )

    def _build_persona_tools(self) -> tuple[BaseTool, ...]:
        """Build thread-scoped persona tools that resolve the current thread."""
        from nuself.persona.tools import build_reason_persona_tools

        return build_reason_persona_tools(
            paths=self._paths,
            global_service=self._persona_service,
            trace_recorder=self._trace_recorder,
            get_thread_workspace=self._thread_workspace,
            text_agent=LangChainTextAgent(
                endpoints=self._langchain_models,
                project_root=self._paths.authority_root,
                component="persona",
            ),
            executor=self._feature_executor,
        )

    def _thread_workspace(self) -> ScopedWorkspace:
        """Resolve one workspace from the active Reason thread context."""

        from nuself.storage.workspace import ScopedWorkspace, SqliteStore

        thread_id = _current_reason_thread_id()
        workspace = self._reason_service.workspace_paths(thread_id)
        return ScopedWorkspace(
            SqliteStore(workspace.database),
            ("workspace", "reason", thread_id),
        )


def default_reason_advancer(
    *,
    paths: RuntimePaths,
    reason_service: ReasonService,
    persona_service: PersonaService,
    trace_recorder: TraceRecorder,
    readonly_tools: Sequence[BaseTool] | None = None,
    langchain_models: tuple[LangChainLLMEndpoint, ...],
) -> ReasonAdvancer:
    """Build the default reason capability from explicit application resources."""
    return ReasonAdvancer(
        paths=paths,
        reason_service=reason_service,
        persona_service=persona_service,
        trace_recorder=trace_recorder,
        feature_executor=FeatureExecutor(),
        readonly_tools=readonly_tools,
        langchain_models=langchain_models,
    )
