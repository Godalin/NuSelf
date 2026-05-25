"""Memory-aware LangGraph-backed chat agent."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, TypedDict, cast

from langchain.agents import create_agent as _create_agent  # pyright: ignore[reportUnknownVariableType]
from langchain.agents.factory import ToolStrategy as _ToolStrategy
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph  # type: ignore[reportMissingTypeStubs]
from pydantic import BaseModel, Field

from nuself.agent.middleware import ToolCaptureMiddleware
from nuself.agent.skills import AgentSkill, load_agent_skills, render_tool_placeholders
from nuself.agent.thread import ThreadMessage, ThreadState, ThreadStore
from nuself.agent.tools import build_langchain_chat_tools
from nuself.agent.tool_utils import format_tool_debug_body
from nuself.domain.proactive import IdeaCandidate
from nuself.config import ConfigSystem
from nuself.llm import (
    ChatLLM,
    ChatMessage,
    LangChainLLMEndpoint,
    configured_langchain_chat_models,
    default_llm,
    is_endpoint_availability_error,
    record_llm_endpoint_success,
    redact_llm_error,
)
from nuself.logs import current_log_context, log_context, write_log_event
from nuself.memory.query import MemoryQuery, MemoryQueryService
from nuself.memory.repository import MemoryEntryRepository
from nuself.memory.source_repository import SourceRepository
from nuself.persona import (
    LLMBackedActivationPolicy,
    LLMBackedPersonaNode,
    LLMBackedSynthesizerNode,
    PersonaDefinition,
    PersonaGraphDriver,
    PersonaInput,
    PersonaTurnState,
    SharedPersonaDiscussionService,
    load_persona_definitions,
)
from nuself.profile.repository import ProfileItemRepository
from nuself.trace.service import TraceRecorder

ToolServiceComponent = Literal["memory", "reflection", "reasoning", "trace", "selves", "skill", "workspace", "persona"]
ConversationNodeName = Literal[
    "prepare_context",
    "respond",
    "state_update",
    "compression",
]
LOGGER = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Response types, parsing, and user-facing boundary checks
# ------------------------------------------------------------------

EpistemicStatus = Literal["grounded", "inferred", "uncertain", "unsupported"]


class ChatStructuredOutput(BaseModel):
    """Structured chat response returned by LangChain response_format."""

    answer: str = Field(description="Plain user-facing answer text. Do not include internal protocol fields.")
    evidence_references: list[str] = Field(default_factory=list, description="Memory, source, or trace ids used.")
    confidence: float | None = Field(default=None, description="Optional confidence from 0.0 to 1.0.")
    epistemic_status: str = Field(default="inferred", description="One of grounded, inferred, uncertain, unsupported.")






def trace_summary(text: str, limit: int = 240) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


@dataclass(frozen=True)
class ChatAgentSettings:
    """Context window settings for the chat agent."""

    recent_messages: int
    summary_trigger_messages: int
    summary_target_chars: int

    @classmethod
    def from_project(cls, project_root: Path | None = None) -> "ChatAgentSettings":
        config = ConfigSystem.load(project_root=project_root)
        return cls(
            recent_messages=config.chat.context.recent_messages,
            summary_trigger_messages=config.chat.context.summary_trigger_messages,
            summary_target_chars=config.chat.context.summary_target_chars,
        )


@dataclass(frozen=True)
class ChatResult:
    """Result returned by one chat turn."""

    answer: str
    thread_id: str
    evidence_references: tuple[str, ...] = ()
    confidence: float | None = None
    epistemic_status: str = "inferred"
    trace_id: str | None = None

    @property
    def reply(self) -> str:
        return self.answer

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "answer": self.answer,
            "reply": self.answer,
            "thread_id": self.thread_id,
            "evidence_references": list(self.evidence_references),
            "epistemic_status": self.epistemic_status,
        }
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        if self.trace_id is not None:
            payload["trace_id"] = self.trace_id
        return payload


@dataclass(frozen=True)
class ConversationTurnState:
    """Typed state passed between conversation runtime nodes."""

    thread_id: str
    persisted_state: ThreadState
    user_message: str
    turn_id: str | None = None
    memory_context: str = ""
    base_messages: tuple[ThreadMessage, ...] = ()
    active_messages: tuple[ThreadMessage, ...] = ()
    final_response: ChatStructuredOutput | None = None
    saved_messages: tuple[ThreadMessage, ...] = ()
    updated_thread_state: ThreadState | None = None
    node_trace: tuple[ConversationNodeName, ...] = ()

    @classmethod
    def start(
        cls,
        state: ThreadState,
        message: str,
        thread_id: str,
        *,
        turn_id: str | None = None,
    ) -> "ConversationTurnState":
        return cls(thread_id=thread_id, persisted_state=state, user_message=message, turn_id=turn_id)


@dataclass(frozen=True)
class ConversationNodeResult:
    """Result from one graph-ready conversation runtime node."""

    state: ConversationTurnState





# ------------------------------------------------------------------
# LangGraph graph driver
# ------------------------------------------------------------------


class ConversationGraphRuntimeError(RuntimeError):
    """Raised when the conversation graph cannot complete a turn."""

    def __init__(
        self,
        message: str,
        *,
        node: ConversationNodeName | None = None,
        node_trace: tuple[ConversationNodeName, ...] = (),
    ) -> None:
        super().__init__(message)
        self.node = node
        self.node_trace = node_trace


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
        self._persona_definitions = load_persona_definitions(project_root)
        self._activation_policy = LLMBackedActivationPolicy(
            self._persona_definitions,
            llm=self._llm,
            langchain_models=self._langchain_models,
            project_root=self._project_root,
        )
        self._persona_driver = PersonaGraphDriver(
            persona_node=LLMBackedPersonaNode(
                llm=self._llm,
                language_preference=self._language_preference,
                langchain_models=self._langchain_models,
                project_root=self._project_root,
            ),
            synthesizer_node=LLMBackedSynthesizerNode(
                llm=self._llm,
                language_preference=self._language_preference,
                langchain_models=self._langchain_models,
                project_root=self._project_root,
            ),
        )
        self._persona_discussion_service = SharedPersonaDiscussionService(
            project_root=project_root,
            llm=self._llm,
            language_preference=self._language_preference,
        )
        self._trace_recorder = TraceRecorder(project_root)
        self._memory_query_service = memory_query_service or MemoryQueryService(
            MemoryEntryRepository(project_root),
            SourceRepository(project_root),
            ProfileItemRepository(project_root),
        )
        from nuself.reflection.repository import ReflectionRepository

        self._reflection_repo = ReflectionRepository(project_root)
        tools = build_langchain_chat_tools(
            query_service=self._memory_query_service,
            reflection_repository=self._reflection_repo,
            project_root=project_root,
            selves_consult=self._consult_selves_tool,
        )
        self._tools: dict[str, BaseTool] = {tool.name: tool for tool in tools}
        self._skills: tuple[AgentSkill, ...] = load_agent_skills()
        self._tools_by_skill: dict[str, tuple[str, ...]] = {
            skill.name: tuple(
                name for name in self._tools
                if _tool_service_component(name) == skill.name
            )
            for skill in self._skills
        }
        self._tools["load_skill"] = self._build_skill_loader_tool()
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
        with log_context(thread_id=thread_id, turn_id=turn_id, source="chat_runtime"):
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
        with log_context(thread_id=thread_id, turn_id=turn_id, source="chat_runtime"):
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
        base_messages = tuple(_messages_for_prompt_context(state.persisted_state.messages))
        active_messages = (*base_messages, ThreadMessage(role="user", content=state.user_message, turn_id=state.turn_id))
        packed_memory = self._memory_query_service.pack(MemoryQuery(text=state.user_message))
        return ConversationNodeResult(
            state=replace(
                state,
                base_messages=base_messages,
                active_messages=active_messages,
                memory_context=packed_memory.text,
                node_trace=(*state.node_trace, "prepare_context"),
            ),
        )

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
        updated = ThreadState(
            thread_id=state.thread_id,
            summary=state.persisted_state.summary,
            messages=list(state.saved_messages),
            message_start_index=state.persisted_state.message_start_index,
            next_message_index=(
                state.persisted_state.next_message_index + len(state.saved_messages) - len(state.base_messages)
            ),
        )
        return ConversationNodeResult(
            state=replace(
                state,
                updated_thread_state=updated,
                node_trace=(*state.node_trace, "state_update"),
            ),
        )

    def compression_node(self, state: ConversationTurnState) -> ConversationNodeResult:
        updated = _require_thread_state(state.updated_thread_state)
        return ConversationNodeResult(
            state=replace(
                state,
                updated_thread_state=self._compress_if_needed(updated),
                node_trace=(*state.node_trace, "compression"),
            ),
        )

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
        parts.extend(_tool_prompt_sections(self._tools.values()))
        if any(tool.name == "reason_propose" for tool in self._tools.values()):
            parts.extend([
                "",
                "Reason skill:",
                "Reason is NuSelf's durable long-run thinking space. When a discussion reveals a topic "
                "with real depth that would benefit from sustained incremental reasoning, you should "
                "suggest creating a reasoning thread. Help the user refine the question and add "
                "initial tracked items with appropriate kind tags from your discussion, and only "
                "call reason_propose after the user explicitly confirms. Do NOT call reason_propose "
                "based on a user's mere agreement that "
                "a topic is 'interesting' — wait for explicit confirmation like 'yes, start it', "
                "'go ahead', or 'create the thread'.",
            ])
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Response generation
    # ------------------------------------------------------------------

    def _complete_response(self, prompt: list[ChatMessage]) -> ChatStructuredOutput:
        if self._langchain_models:
            return self._complete_response_with_langchain_tools(prompt)
        raw = self._llm.complete(prompt)
        return self._parse_llm_output(raw)

    def _complete_response_with_langchain_tools(self, prompt: list[ChatMessage]) -> ChatStructuredOutput:
        last_error: Exception | None = None
        for position, endpoint in enumerate(self._langchain_models):
            for attempt in range(2):
                try:
                    response = self._complete_response_with_langchain_endpoint(endpoint, prompt)
                except Exception as exc:
                    last_error = exc
                    if attempt == 0 and not is_endpoint_availability_error(str(exc)):
                        write_log_event(
                            "chat",
                            "llm_endpoint_retry",
                            "LLM endpoint error; retrying",
                            project_root=self._project_root,
                            status="retry",
                            error=redact_llm_error(str(exc)),
                            metadata={
                                "endpoint_index": endpoint.index,
                                "base_url": endpoint.settings.base_url,
                                "model": endpoint.settings.model,
                            },
                        )
                        continue
                    remaining = self._langchain_models[position + 1 :]
                    if remaining:
                        status = "failed_over" if is_endpoint_availability_error(str(exc)) else "error"
                        write_log_event(
                            "chat",
                            "llm_endpoint_failed_over" if is_endpoint_availability_error(str(exc)) else "llm_endpoint_error",
                            "LLM endpoint failed; trying next configured endpoint",
                            project_root=self._project_root,
                            status=status,
                            error=redact_llm_error(str(exc)),
                            metadata={
                                "endpoint_index": endpoint.index,
                                "base_url": endpoint.settings.base_url,
                                "model": endpoint.settings.model,
                                "next_endpoint_index": remaining[0].index,
                            },
                        )
                    break
                else:
                    record_llm_endpoint_success(self._project_root, endpoint.index)
                    return response
        if last_error is not None:
            write_log_event(
                "chat",
                "llm_endpoints_exhausted",
                "all LLM endpoints failed; falling back to local LLM",
                project_root=self._project_root,
                status="fallback",
                error=redact_llm_error(str(last_error)),
            )
        raw = self._llm.complete(prompt)
        return self._parse_llm_output(raw)

    def _complete_response_with_langchain_endpoint(
        self,
        endpoint: LangChainLLMEndpoint,
        prompt: list[ChatMessage],
    ) -> ChatStructuredOutput:
        supervisor = _LangChainChatSupervisor(
            endpoint=endpoint,
            tools=self._tools.values(),
            log_tool_call=self._log_langchain_service_tool_call,
        )
        return supervisor.complete(prompt)

    @staticmethod
    def _parse_llm_output(raw: str) -> ChatStructuredOutput:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return ChatStructuredOutput(answer=raw)
        if isinstance(parsed, dict):
            return ChatStructuredOutput.model_validate(cast(dict[str, object], parsed))
        return ChatStructuredOutput(answer=raw)

    def _finalize_draft_response(self, state: ConversationTurnState, draft: ChatStructuredOutput) -> ChatStructuredOutput:
        write_log_event(
            "chat",
            "final_response_completed",
            "final response accepted from chat supervisor",
            project_root=self._project_root,
            thread_id=state.thread_id,
            status="completed",
            metadata={"epistemic_status": draft.epistemic_status},
        )
        return draft

    def _log_langchain_service_tool_call(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        result: str | None = None,
        error: str | None = None,
    ) -> None:
        service_component = _tool_service_component(tool_name)
        if service_component is None:
            return
        self._write_service_tool_log(
            tool_name,
            service_component,
            "failed" if error is not None else "completed",
            args=args,
            result=result,
            error=error,
        )

    # ------------------------------------------------------------------
    # Selves consultation (exposed as the selves_consult tool)
    # ------------------------------------------------------------------

    def _consult_selves_tool(self, topic: str, mode: str = "consult", context: str | None = None) -> str:
        thread_id = current_log_context().thread_id or "default"
        memory_context = self._memory_query_service.pack(MemoryQuery(text=topic)).text
        extra_context = context.strip() if isinstance(context, str) else ""
        combined_context = "\n\n".join(part for part in (memory_context, extra_context) if part)
        persona_input = PersonaInput(user_message=topic, memory_context=combined_context)
        activation = self._activation_policy.decide(persona_input)
        selected_personas = activation.selected_personas or self._default_consult_personas()
        turn_state = PersonaTurnState(input=persona_input, selected_personas=selected_personas)
        updated_turn_state = self._persona_driver.run(turn_state)
        trigger = activation.trigger or "selves_consult"
        self._write_persona_summary_log(updated_turn_state, thread_id=thread_id, trigger=trigger)

        force_discussion = mode.strip().casefold() in {"discussion", "discuss", "debate", "competitive"}
        should_escalate = activation.should_escalate or force_discussion
        escalation_reason = activation.escalation_reason or ("requested discussion mode" if force_discussion else "consultation only")
        self._write_host_discussion_decision_log(
            thread_id=thread_id,
            should_escalate=should_escalate,
            escalation_reason=escalation_reason,
        )
        discussion_note = ""
        try:
            if should_escalate:
                result = self._persona_discussion_service.discuss(
                    self._build_chat_discussion_candidate(
                        thread_id=thread_id,
                        user_message=topic,
                        title=(topic.splitlines()[0] if topic.splitlines() else topic)[:120],
                        source_summary=updated_turn_state.synthesis.summary if updated_turn_state.synthesis is not None else "",
                    ),
                    on_trace_entry=lambda entry: self._write_persona_discussion_step_log(
                        thread_id,
                        trigger,
                        entry,
                    ),
                )
                discussion_note = f"\nDiscussion result: {result.reason}"
                try:
                    write_log_event(
                        "persona",
                        "persona_discussion",
                        f"chat-triggered discussion: {result.reason}",
                        project_root=self._project_root,
                        thread_id=thread_id,
                        status=trigger,
                        metadata={
                            "winner_persona_ids": list(result.winner_persona_ids),
                            "emergent_persona_ids": list(result.emergent_persona_ids),
                            "blocking_vetos": list(result.blocking_vetos),
                            "reason": result.reason,
                            "discussion_steps": len(result.discussion_trace),
                        },
                    )
                except Exception:
                    LOGGER.exception("failed to write persona discussion log")
        except Exception as exc:
            write_log_event(
                "persona",
                "persona_discussion_failure",
                str(exc),
                project_root=self._project_root,
                level="error",
                error=str(exc),
            )
            discussion_note = f"\nDiscussion failed: {exc}"

        return _format_selves_consult_result(updated_turn_state, trigger=trigger, discussion_note=discussion_note)

    def _default_consult_personas(self) -> tuple[PersonaDefinition, ...]:
        preferred = ("analyst_self", "skeptic_self", "builder_self")
        by_id = {persona.id: persona for persona in self._persona_definitions}
        selected = tuple(by_id[pid] for pid in preferred if pid in by_id)
        if selected:
            return selected
        return tuple(self._persona_definitions[:3])

    def _write_persona_summary_log(self, turn_state: PersonaTurnState, *, thread_id: str, trigger: str) -> None:
        try:
            write_log_event(
                "persona",
                "persona_summary",
                _compact_persona_summary(turn_state),
                project_root=self._project_root,
                thread_id=thread_id,
                status=trigger,
                metadata={
                    "persona_count": len(turn_state.contributions),
                    "has_synthesis": turn_state.synthesis is not None,
                },
            )
        except Exception:
            LOGGER.exception("failed to write persona summary log")

    def _write_host_discussion_decision_log(
        self,
        *,
        thread_id: str,
        should_escalate: bool,
        escalation_reason: str,
    ) -> None:
        try:
            write_log_event(
                "persona",
                "host_discussion_decision",
                escalation_reason,
                project_root=self._project_root,
                thread_id=thread_id,
                status="approved" if should_escalate else "skipped",
                metadata={
                    "should_escalate": should_escalate,
                    "escalation_reason": escalation_reason,
                },
            )
        except Exception:
            LOGGER.exception("failed to write host discussion decision log")

    def _write_persona_discussion_step_log(self, thread_id: str, trigger: str, entry: str) -> None:
        try:
            write_log_event(
                "persona",
                "persona_discussion_step",
                "",
                project_root=self._project_root,
                thread_id=thread_id,
                status=trigger,
                metadata={"discussion_trace": [entry]},
            )
        except Exception:
            LOGGER.exception("failed to write persona discussion step log")

    def _build_chat_discussion_candidate(
        self,
        *,
        thread_id: str,
        user_message: str,
        title: str,
        source_summary: str,
    ) -> IdeaCandidate:
        ctype = "question" if "?" in user_message else "action"
        return IdeaCandidate(
            id=f"chat-{thread_id}-{int(datetime.now(UTC).timestamp())}",
            title=title,
            body=user_message,
            candidate_type=ctype,
            confidence=0.8,
            novelty=0.5,
            urgency=0.2,
            interruption_cost=0.1,
            evidence_refs=(),
            suggested_thread_id=thread_id,
            source_summary=source_summary,
            created_at=datetime.now(UTC).isoformat(),
        )

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def _compress_if_needed(self, state: ThreadState) -> ThreadState:
        if len(state.messages) <= self._settings.summary_trigger_messages:
            return state
        recent = state.messages[-self._settings.recent_messages :]
        older = state.messages[: -self._settings.recent_messages]
        summary = self._summarize(state.summary, older)
        return ThreadState(
            thread_id=state.thread_id,
            summary=summary,
            messages=recent,
            message_start_index=state.next_message_index - len(recent),
            next_message_index=state.next_message_index,
        )

    def _summarize(self, previous_summary: str, messages: list[ThreadMessage]) -> str:
        transcript = "\n".join(f"{message.role}: {message.content}" for message in messages)
        prompt = [
            ChatMessage(
                role="system",
                content=(
                    "Compress a private NuSelf conversation into durable context. "
                    "Preserve user preferences, decisions, unresolved questions, and useful facts. "
                    "Do not add new facts."
                ),
            ),
            ChatMessage(
                role="user",
                content=f"Previous summary:\n{previous_summary or '(none)'}\n\nNew transcript:\n{transcript}",
            ),
        ]
        try:
            summary = self._llm.complete(prompt).strip()
        except RuntimeError:
            summary = _local_summary(previous_summary, transcript, self._settings.summary_target_chars)
        return summary[: self._settings.summary_target_chars]

    # ------------------------------------------------------------------
    # Tool logging
    # ------------------------------------------------------------------

    def _write_service_tool_log(
        self,
        tool_name: str,
        service_component: ToolServiceComponent,
        status: str,
        *,
        args: dict[str, Any],
        result: str | None = None,
        error: str | None = None,
    ) -> None:
        message = format_tool_debug_body(args=args, result=result, error=error)
        full_body = format_tool_debug_body(args=args, result=result, error=error, full=True)
        write_log_event(
            "chat",
            "service_tool_called",
            message,
            project_root=self._project_root,
            status=status,
            error=error,
            metadata={
                "service_component": service_component,
                "tool": tool_name,
                "message_body": full_body,
            },
        )

    # ------------------------------------------------------------------
    # Skill loader tool
    # ------------------------------------------------------------------

    def _build_skill_loader_tool(self) -> BaseTool:
        skill_lines = "\n".join(f"  - {skill.name}: {skill.description}" for skill in self._skills)

        def load_skill(skill_name: str) -> str:
            for skill in self._skills:
                if skill.name == skill_name:
                    tools = self._tools_by_skill.get(skill_name, ())
                    body = f"Service skill: {skill.name}"
                    if tools:
                        body += f"\nAllowed tools: {', '.join(tools)}"
                    body += f"\n\n{render_tool_placeholders(skill.instructions, skill_name=skill_name, tools=tools)}"
                    return body
            return f"Error: unknown skill '{skill_name}'. Available skills:\n{skill_lines}"

        from langchain_core.tools import StructuredTool

        return StructuredTool.from_function(  # pyright: ignore[reportUnknownMemberType]
            name="load_skill",
            description=f"Load a service skill's behavioral policy. Skills define when and how the agent should use service tools.\n\nAvailable skills:\n{skill_lines}",
            func=load_skill,
            tags=("readonly",),
        )


# ======================================================================
# LangChain supervisor (inline — wraps create_agent for one chat turn)
# ======================================================================


class _LangChainChatSupervisor:
    """Runs one chat turn through LangChain's agent/tool runtime.

    The agent graph is rebuilt per turn so that the system prompt
    (which varies with conversation context) can be baked in by
    ``create_agent`` — this ensures tool descriptions and the
    ``response_format`` instruction are properly injected.
    """

    def __init__(
        self,
        *,
        endpoint: LangChainLLMEndpoint,
        tools: Iterable[BaseTool],
        log_tool_call: Callable[..., None],
    ) -> None:
        self._endpoint = endpoint
        self._tools = tuple(tools)
        self._log_tool_call = log_tool_call

    def complete(self, prompt: list[ChatMessage]) -> ChatStructuredOutput:
        system_prompt, messages = _split_prompt(prompt)
        tool_cache: dict[str, str] = {}
        middleware = ToolCaptureMiddleware(
            log_callback=self._log_tool_call,
            cache=tool_cache,
        )
        create_agent = cast(Any, _create_agent)
        agent = create_agent(
            model=self._endpoint.model,
            tools=list(self._tools),
            system_prompt=system_prompt,
            response_format=_ToolStrategy(schema=ChatStructuredOutput),
            middleware=[middleware],
        )
        result = agent.invoke({"messages": messages})
        return _structured_output_from_state(result)


def _structured_output_from_state(result: object) -> ChatStructuredOutput:
    """Extract ChatStructuredOutput from agent state.

    1. Prefer ``state.structured_response`` (set by LangChain's
       ``response_format`` mechanism) — validated that the answer
       doesn't contain tool call markers.
    2. Fall through to parse the last message content directly.
    """
    if not isinstance(result, dict):
        raise ValueError(f"LangChain agent returned invalid state: {type(result).__name__}")
    state = cast(dict[str, object], result)

    # Priority 1 — structured_response from response_format mechanism.
    structured = state.get("structured_response")
    if isinstance(structured, ChatStructuredOutput):
        if not _looks_like_tool_call(structured.answer):
            return structured
    elif isinstance(structured, dict):
        try:
            parsed = ChatStructuredOutput.model_validate(structured)
            if not _looks_like_tool_call(parsed.answer):
                return parsed
        except Exception:
            pass

    # Priority 2 — parse last message content.
    msgs = state.get("messages")
    if isinstance(msgs, list) and msgs:
        last = cast(object, msgs[-1])
        content = getattr(last, "content", None)
        if isinstance(content, str):
            if _looks_like_tool_call(content):
                raise ValueError(
                    f"Agent produced tool call text instead of structured response: {content[:200]!r}"
                )
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    return ChatStructuredOutput.model_validate(cast(dict[str, object], parsed))
            except json.JSONDecodeError:
                pass
            return ChatStructuredOutput(answer=content)
    raise ValueError("no valid structured output in agent state")


def _looks_like_tool_call(text: str) -> bool:
    """Heuristic: does the text look like a serialised tool call?"""
    # Minimax serialises tool calls as ``minimax:tool_call`` XML markers.
    return "minimax:tool_call" in text


def _split_prompt(prompt: list[ChatMessage]) -> tuple[str | None, list[BaseMessage]]:
    system_parts: list[str] = []
    messages: list[BaseMessage] = []
    for message in prompt:
        if message.role == "system":
            system_parts.append(message.content)
        elif message.role == "assistant":
            messages.append(AIMessage(content=message.content))
        else:
            messages.append(HumanMessage(content=message.content))
    return ("\n\n".join(system_parts) if system_parts else None), messages





# ======================================================================
# Module-level helpers
# ======================================================================
# Module-level helpers
# ======================================================================


def _local_summary(previous_summary: str, transcript: str, target_chars: int) -> str:
    combined = "\n\n".join(part for part in [previous_summary, transcript] if part != "")
    if len(combined) <= target_chars:
        return combined
    return combined[-target_chars:]


def _compact_persona_summary(turn_state: "PersonaTurnState") -> str:
    parts: list[str] = []
    for contrib in turn_state.contributions:
        note = contrib.notes[0] if contrib.notes else ""
        snippet = note if len(note) <= 140 else (note[:137] + "...")
        parts.append(f"{contrib.persona_id}: {snippet}")
    if turn_state.synthesis is not None:
        summary = turn_state.synthesis.summary
        synthesis_snippet = summary if len(summary) <= 140 else (summary[:137] + "...")
        parts.append(f"synthesizer_self: {synthesis_snippet}")
    if not parts:
        return "(no persona contributions)"
    return "\n".join(parts)


def _format_selves_consult_result(
    turn_state: "PersonaTurnState",
    *,
    trigger: str,
    discussion_note: str = "",
) -> str:
    lines = [
        "Selves consultation result:",
        f"trigger: {trigger}",
    ]
    if turn_state.contributions:
        lines.append("persona notes:")
        for contribution in turn_state.contributions:
            note = contribution.notes[0] if contribution.notes else "(no note)"
            lines.append(f"- {contribution.persona_id}: {note}")
    if turn_state.synthesis is not None:
        lines.extend(
            [
                "synthesis:",
                turn_state.synthesis.summary,
                f"source_personas: {', '.join(turn_state.synthesis.source_personas)}",
            ]
        )
    if discussion_note:
        lines.append(discussion_note.strip())
    return "\n".join(lines)


def _messages_for_prompt_context(messages: list[ThreadMessage]) -> list[ThreadMessage]:
    return [message for message in messages if not (message.role == "assistant" and message.content.startswith("LLM API is not configured yet."))]


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


def _tool_service_component(tool_name: str) -> ToolServiceComponent | None:
    if tool_name.startswith("memory_"):
        return "memory"
    if tool_name.startswith("reflection_"):
        return "reflection"
    if tool_name.startswith("reason_"):
        return "reasoning"
    if tool_name.startswith("trace_"):
        return "trace"
    if tool_name.startswith("selves_"):
        return "selves"
    if tool_name.startswith("persona_"):
        return "persona"
    if tool_name == "load_skill":
        return "skill"
    if tool_name.startswith("workspace_"):
        return "workspace"
    return None


def _tool_prompt_sections(tools: "Iterable[BaseTool]") -> list[str]:
    lines = [
        "",
        "Available tools:",
        "The following LangChain tools are loaded in the current NuSelf runtime.",
        "CRITICAL: When the user asks a question that a tool can answer, you MUST call the tool before generating your final answer. Always use the tool to get the actual current state.",
        "Tools are bound through LangChain's native tool-calling API.",
        'Do not write visible markers such as "[Tool call: memory_search]" or JSON tool fields in the answer body.',
        "The tool will be executed and its result injected back into context. Only then generate your final answer.",
        "Service skills define when and how to use tools. Use `load_skill` to load a skill's behavioral policy.",
        "Tools available:",
    ]
    for tool in tools:
        args = _tool_args_signature(tool)
        lines.append(f"- {tool.name}({args}): {tool.description}")
    return lines


def _tool_args_signature(tool: BaseTool) -> str:
    raw_args_schema = cast(object, getattr(tool, "args"))
    args_schema = cast(dict[object, object], raw_args_schema) if isinstance(raw_args_schema, dict) else {}
    pieces: list[str] = []
    for name, schema in args_schema.items():
        if not isinstance(name, str):
            continue
        type_name = "object"
        default: object | None = None
        if isinstance(schema, dict):
            schema_dict = cast(dict[object, object], schema)
            type_value = schema_dict.get("type")
            if isinstance(type_value, str):
                type_name = type_value
            default = schema_dict.get("default")
        if default is None:
            pieces.append(f"{name}: {type_name}")
        else:
            pieces.append(f"{name}: {type_name} = {default!r}")
    return ", ".join(pieces)


# Backward-compatible alias
ChatAgent = ConversationGraphRuntime
