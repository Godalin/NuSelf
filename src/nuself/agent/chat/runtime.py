"""Memory-aware LangGraph-backed chat agent."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
import logging
import time
from pathlib import Path
from typing import Any, TypedDict, cast

from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph  # type: ignore[reportMissingTypeStubs]
from nuself.agent.chat.types import (
    ChatAgentSettings,
    ChatResult,
    ChatStructuredOutput,
    ConversationGraphRuntimeError,
    ConversationNodeName,
    ConversationNodeResult,
    ConversationTurnState,
)
from nuself.agent.chat.context import ConversationContextPreparer
from nuself.agent.chat.persona import ConversationPersonaOrchestrator
from nuself.agent.chat.response import ConversationResponseSynthesizer
from nuself.agent.chat.state import ConversationStateManager
from nuself.agent.chat.tool_runtime import ConversationToolRuntime
from nuself.agent.chat.thread import ThreadMessage, ThreadState, ThreadStore
from nuself.config import ConfigSystem
from nuself.llm import (
    ChatLLM,
    ChatMessage,
    LangChainLLMEndpoint,
    configured_langchain_chat_models,
    default_llm,
)
from nuself.logs import write_log_event
from nuself.memory.query import MemoryQueryService
from nuself.memory.repository import MemoryEntryRepository
from nuself.memory.source_repository import SourceRepository
from nuself.profile.repository import ProfileItemRepository
from nuself.reason.output import SectionPlanner
from nuself.runtime.context import runtime_context
from nuself.runtime.jobs import JobSink
from nuself.trace.service import TraceRecorder

LOGGER = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Response types, parsing, and user-facing boundary checks
# ------------------------------------------------------------------

def trace_summary(text: str, limit: int = 240) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


# ------------------------------------------------------------------
# LangGraph graph driver
# ------------------------------------------------------------------


class _ConversationGraphState(TypedDict):
    turn_state: ConversationTurnState


class ConversationGraphRuntime:
    """Graph-ready conversation runtime.

    Delegates response generation (including tool calling) to LangChain
    ``create_agent`` via ``_LangChainChatSupervisor``. NuSelf owns only the
    boundaries: context preparation, response validation, state persistence,
    and conversation compression.
    """

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        llm: ChatLLM | None = None,
        langchain_models: tuple[LangChainLLMEndpoint, ...] | None = None,
        settings: ChatAgentSettings | None = None,
        memory_query_service: MemoryQueryService | None = None,
        thread_store: ThreadStore | None = None,
        job_sink: JobSink | None = None,
        section_planner: SectionPlanner | None = None,
    ) -> None:
        self._llm = llm or default_llm(project_root)
        self._langchain_models: tuple[LangChainLLMEndpoint, ...] = (
            langchain_models
            if langchain_models is not None
            else (() if llm is not None else configured_langchain_chat_models(project_root))
        )
        self._settings = settings or ChatAgentSettings.from_project(project_root)
        self._project_root = project_root
        self._thread_store = thread_store or ThreadStore(project_root)
        system_config = ConfigSystem.load(project_root=project_root)
        self._language_preference = system_config.chat.language_preference
        self._trace_recorder = TraceRecorder(project_root)
        self._memory_query_service = memory_query_service or MemoryQueryService(
            MemoryEntryRepository(project_root),
            SourceRepository(project_root),
            ProfileItemRepository(project_root),
        )
        self._context_preparer = ConversationContextPreparer(
            self._memory_query_service
        )
        self._state_manager = ConversationStateManager(
            llm=self._llm,
            settings=self._settings,
        )
        self._persona_orchestrator = ConversationPersonaOrchestrator(
            project_root=project_root,
            llm=self._llm,
            langchain_models=self._langchain_models,
            language_preference=self._language_preference,
            memory_query_service=self._memory_query_service,
        )
        self._tool_runtime = ConversationToolRuntime(
            project_root=project_root,
            query_service=self._memory_query_service,
            selves_consult=self._consult_selves_tool,
            job_sink=job_sink,
            section_planner=section_planner,
        )
        self._tools: dict[str, BaseTool] = self._tool_runtime.tools
        self._response_synthesizer = ConversationResponseSynthesizer(
            project_root=project_root,
            llm=self._llm,
            langchain_models=self._langchain_models,
            tools=self._tools.values(),
            log_tool_call=self._tool_runtime.log_call,
            report_tool_log_failure=self._tool_runtime.report_log_failure,
        )
        graph: Any = StateGraph(_ConversationGraphState)
        graph.add_node("prepare_context", self._graph_prepare_context)
        graph.add_node("respond", self._graph_respond)
        graph.add_node("state_update", self._graph_state_update)
        graph.add_node("compression", self._graph_compression)
        graph.add_edge(START, "prepare_context")
        graph.add_edge("prepare_context", "respond")
        graph.add_edge("respond", "state_update")
        graph.add_edge("state_update", "compression")
        graph.add_edge("compression", END)
        self._graph = graph.compile()

    def respond(self, message: str, thread_id: str = "default", *, turn_id: str | None = None) -> ChatResult:
        def update(state: ThreadState) -> tuple[ThreadState, ChatResult]:
            completed = _completed_turn_result(state, message=message, thread_id=thread_id, turn_id=turn_id)
            if completed is not None:
                write_log_event(
                    "chat",
                    "turn_reused",
                    "chat turn reused existing completed result",
                    project_root=self._project_root,
                    thread_id=thread_id,
                    turn_id=turn_id,
                    source="chat_runtime",
                    status="completed",
                )
                return state, completed
            state, result, _ = self.run_turn(state, message, thread_id, turn_id=turn_id)
            return state, result

        return self._thread_store.update(thread_id, update)

    def run_turn(
        self,
        state: ThreadState,
        message: str,
        thread_id: str,
        *,
        turn_id: str | None = None,
    ) -> tuple[ThreadState, ChatResult, tuple[ConversationNodeName, ...]]:
        started_at = time.monotonic()
        with runtime_context(
            thread_id=thread_id,
            turn_id=turn_id,
            source="chat_runtime",
        ):
            write_log_event(
                "chat",
                "turn_started",
                "chat turn started",
                project_root=self._project_root,
                status="started",
            )
            try:
                output: object = self._graph.invoke({"turn_state": ConversationTurnState.start(state, message, thread_id, turn_id=turn_id)})
            except ConversationGraphRuntimeError:
                raise
            except Exception as exc:
                raise ConversationGraphRuntimeError(
                    f"conversation graph failed while handling thread '{thread_id}'",
                    node_trace=(),
                ) from exc
            if not isinstance(output, dict):
                raise ConversationGraphRuntimeError("conversation graph returned invalid state", node_trace=())
            graph_state = cast(_ConversationGraphState, output)
            turn_state = graph_state["turn_state"]
        updated = _require_thread_state(turn_state.updated_thread_state)
        final_response = _require_final_response(turn_state.final_response)
        duration_ms = int((time.monotonic() - started_at) * 1000)
        with runtime_context(
            thread_id=thread_id,
            turn_id=turn_id,
            source="chat_runtime",
        ):
            write_log_event(
                "chat",
                "turn_completed",
                "chat turn completed",
                project_root=self._project_root,
                duration_ms=duration_ms,
                status="completed",
            )
        trace_id = self._record_chat_turn_trace(
            user_message=message,
            final_response=final_response,
            thread_id=thread_id,
            node_trace=turn_state.node_trace,
        )
        state = updated
        return state, ChatResult(
            answer=final_response.answer,
            thread_id=thread_id,
            evidence_references=tuple(final_response.evidence_references),
            confidence=final_response.confidence,
            epistemic_status=final_response.epistemic_status,
            trace_id=trace_id,
        ), turn_state.node_trace

    def _record_chat_turn_trace(
        self,
        *,
        user_message: str,
        final_response: ChatStructuredOutput,
        thread_id: str,
        node_trace: tuple[ConversationNodeName, ...],
    ) -> str | None:
        if not final_response.evidence_references:
            return None
        evidence_refs = list(final_response.evidence_references)
        try:
            trace = self._trace_recorder.record_chat_turn(
                title=f"Chat turn cited {evidence_refs[0]}",
                summary="Assistant reply used retrieved context cited by the final response.",
                user_input=trace_summary(user_message),
                assistant_output=trace_summary(final_response.answer),
                thread_id=thread_id,
                evidence_refs=evidence_refs,
                participants=["chat_agent"],
                decision_points=["Recorded because the final response cited evidence references."],
                metadata={"node_trace": list(node_trace), "epistemic_status": final_response.epistemic_status},
            )
            return trace.id
        except Exception as exc:
            write_log_event(
                "memory",
                "trace_write_failed",
                "chat trace write failed",
                project_root=self._project_root,
                thread_id=thread_id,
                status="error",
                metadata={"error": str(exc)},
            )
        return None

    # ------------------------------------------------------------------
    # LangGraph node wrappers
    # ------------------------------------------------------------------

    def _run_graph_node(self, node_name: ConversationNodeName, state: _ConversationGraphState, run: Callable[[ConversationTurnState], ConversationNodeResult]) -> _ConversationGraphState:
        turn_state = state["turn_state"]
        try:
            return {"turn_state": run(turn_state).state}
        except ConversationGraphRuntimeError:
            raise
        except Exception as exc:
            raise ConversationGraphRuntimeError(
                f"conversation graph node '{node_name}' failed while handling thread '{turn_state.thread_id}'",
                node=node_name,
                node_trace=(*turn_state.node_trace, node_name),
            ) from exc

    def _graph_prepare_context(self, state: _ConversationGraphState) -> _ConversationGraphState:
        return self._run_graph_node("prepare_context", state, self.prepare_context_node)

    def _graph_respond(self, state: _ConversationGraphState) -> _ConversationGraphState:
        return self._run_graph_node("respond", state, self.respond_node)

    def _graph_state_update(self, state: _ConversationGraphState) -> _ConversationGraphState:
        return self._run_graph_node("state_update", state, self.state_update_node)

    def _graph_compression(self, state: _ConversationGraphState) -> _ConversationGraphState:
        return self._run_graph_node("compression", state, self.compression_node)

    # ------------------------------------------------------------------
    # Graph node methods
    # ------------------------------------------------------------------

    def prepare_context_node(self, state: ConversationTurnState) -> ConversationNodeResult:
        return self._context_preparer.prepare(state)

    def respond_node(self, state: ConversationTurnState) -> ConversationNodeResult:
        prompt = self._build_prompt(state)
        response = self._complete_response(prompt)
        final = self._finalize_draft_response(state, response)
        saved = (
            *state.active_messages,
            ThreadMessage(role="assistant", content=final.answer, turn_id=state.turn_id),
        )
        return ConversationNodeResult(
            state=replace(
                state,
                final_response=final,
                saved_messages=saved,
                node_trace=(*state.node_trace, "respond"),
            ),
        )

    def state_update_node(self, state: ConversationTurnState) -> ConversationNodeResult:
        return self._state_manager.update(state)

    def compression_node(self, state: ConversationTurnState) -> ConversationNodeResult:
        return self._state_manager.compress(state)

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def _build_prompt(self, state: ConversationTurnState) -> list[ChatMessage]:
        prompt: list[ChatMessage] = [ChatMessage(role="system", content=self._system_prompt(state))]
        for message in state.active_messages[-self._settings.recent_messages :]:
            prompt.append(ChatMessage(role=message.role, content=message.content))
        return prompt

    def _system_prompt(self, state: ConversationTurnState) -> str:
        parts = [
            "You are NuSelf, a private AI mirror for one person.",
            "Use the user's memory entries and source chunks as durable context. Do not invent memories.",
            "Return a JSON object with answer, evidence_references, confidence, and epistemic_status.",
            "answer must be the user-facing text. evidence_references must cite relevant memory ids or source refs when available.",
            "Use internal persona synthesis as private context only. "
            "Do not narrate internal persona composition or say which self contributed what in the user-facing answer, "
            "unless the user explicitly asks about the internal persona mechanism.",
            "The JSON object is only an internal transport protocol. "
            "The answer field must contain only the text to show to the user; "
            "do not include raw JSON, fenced code blocks, or protocol field names inside answer.",
            "If you make a claim about the user's preferences, history, or other personal facts without evidence, set epistemic_status to unsupported.",
            "confidence should be a number between 0 and 1 when you can estimate it; otherwise omit it.",
            "epistemic_status should be one of grounded, inferred, uncertain, or unsupported.",
            "Answer directly, keep uncertainty explicit, and surface useful questions when appropriate.",
        ]
        if self._language_preference != "en":
            parts.append(f"Respond to the user in {self._language_preference}.")
        if state.memory_context != "":
            parts.extend(["", "Relevant memory context:", state.memory_context])
        if state.persisted_state.summary != "":
            parts.extend(["", "Compressed conversation so far:", state.persisted_state.summary])
        parts.extend(self._tool_runtime.prompt_sections())
        if self._tool_runtime.has_tool("reason_propose"):
            parts.extend([
                "",
                "Reason skill:",
                "Reason is NuSelf's durable long-run thinking space. When a discussion reveals a topic "
                "with real depth that would benefit from sustained incremental reasoning, you should "
                "suggest creating a reasoning thread. Help the user refine the question and add "
                "initial tracked items with appropriate kind tags from your discussion. Call "
                "reason_propose when the user wants to start the thread; the decorated tool will "
                "prompt for confirmation before writing the proposal. Do NOT call reason_propose "
                "based on a user's mere agreement that a topic is 'interesting'.",
            ])
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Response generation
    # ------------------------------------------------------------------

    def _complete_response(self, prompt: list[ChatMessage]) -> ChatStructuredOutput:
        return self._response_synthesizer.complete(prompt)

    @staticmethod
    def _parse_llm_output(raw: str) -> ChatStructuredOutput:
        return ConversationResponseSynthesizer.parse_output(raw)

    def _finalize_draft_response(self, state: ConversationTurnState, draft: ChatStructuredOutput) -> ChatStructuredOutput:
        return self._response_synthesizer.finalize(state, draft)

    # ------------------------------------------------------------------
    # Selves consultation (exposed as the selves_consult tool)
    # ------------------------------------------------------------------

    def _consult_selves_tool(self, topic: str, mode: str = "consult", context: str | None = None) -> str:
        return self._persona_orchestrator.consult(
            topic,
            mode=mode,
            context=context,
        )

# ======================================================================
# Module-level helpers
# ======================================================================
# Module-level helpers
# ======================================================================


def _require_thread_state(state: ThreadState | None) -> ThreadState:
    if state is None:
        raise RuntimeError("conversation runtime thread state is missing")
    return state


def _require_final_response(response: ChatStructuredOutput | None) -> ChatStructuredOutput:
    if response is None:
        raise RuntimeError("conversation runtime presented response is missing")
    return response


def _completed_turn_result(
    state: ThreadState,
    *,
    message: str,
    thread_id: str,
    turn_id: str | None,
) -> ChatResult | None:
    if turn_id is None or len(state.messages) < 2:
        return None
    assistant_message: ThreadMessage | None = None
    for item in reversed(state.messages):
        if item.turn_id == turn_id and item.role == "assistant":
            assistant_message = item
            break
    if assistant_message is None:
        return None
    for item in reversed(state.messages):
        if item.turn_id == turn_id and item.role == "user":
            if item.content == message:
                return ChatResult(answer=assistant_message.content, thread_id=thread_id)
            return None
    return None


# Backward-compatible alias
ChatAgent = ConversationGraphRuntime
