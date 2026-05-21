"""Memory-aware LangGraph-backed chat agent."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
import json
import logging
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol, TypeAlias, cast

from langchain_core.tools import BaseTool
from pydantic import ValidationError

from nuself.agent.skills import AgentSkill, load_agent_skills, render_agent_skill_sections
from nuself.agent.supervisor import ChatStructuredOutput, LangChainChatSupervisor
from nuself.agent.thread import ThreadMessage, ThreadState, ThreadStore
from nuself.agent.tools import build_langchain_chat_tools
from nuself.agent.persona import (
    PersonaActivation,
    PersonaDefinition,
    LLMBackedActivationPolicy,
    LLMBackedPersonaNode,
    LLMBackedSynthesizerNode,
    PersonaGraphDriver,
    PersonaInput,
    PersonaSynthesis,
    PersonaTurnState,
    load_persona_definitions,
)
from nuself.domain.proactive import IdeaCandidate
from nuself.config_system import ConfigSystem
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
from nuself.profile.repository import ProfileItemRepository
from nuself.persona_discussion_service import SharedPersonaDiscussionService
from nuself.trace.service import TraceRecorder

ToolServiceComponent = Literal["memory", "reflection", "reasoning", "trace", "selves"]
ConversationNodeName = Literal[
    "prepare_context",
    "persona_activation",
    "run_personas",
    "initial_response",
    "detect_tool_request",
    "execute_tool",
    "finalize_response",
    "state_update",
    "compression",
]
USER_FACING_PERSONA_BOUNDARY = (
    "Use internal persona synthesis as private context only. "
    "Do not narrate internal persona composition or say which self contributed what in the user-facing answer, "
    "unless the user explicitly asks about the internal persona mechanism."
)
USER_FACING_PROTOCOL_BOUNDARY = (
    "The JSON object is only an internal transport protocol. "
    "The answer field must contain only the text to show to the user; "
    "do not include raw JSON, fenced code blocks, or protocol field names inside answer."
)
LOGGER = logging.getLogger(__name__)
REGENERATE_USER_FACING_RESPONSE_PROMPT = (
    "Your previous response leaked the internal response protocol into the user-visible answer. "
    "Regenerate the response using the same context. Return only the required JSON object for the runtime, "
    "and make the answer field plain user-facing text without JSON, code fences, or protocol field names."
)
PRESENTATION_BOUNDARY_FAILURE_ANSWER = "我刚刚的输出格式出了问题。请你再说一遍，我会直接用正常聊天的方式回答。"


class _InvokableTool(Protocol):
    def invoke(self, input: object) -> object: ...


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
        return payload


@dataclass(frozen=True)
class DraftResponse:
    """Internal substantive response before final presentation."""

    answer: str
    evidence_references: tuple[str, ...] = ()
    confidence: float | None = None
    epistemic_status: str = "inferred"
    tool: str | None = None
    tool_args: dict[str, Any] | None = None

    @property
    def draft_answer(self) -> str:
        return self.answer


@dataclass(frozen=True)
class PresentedResponse:
    """Final user-facing response after presentation."""

    answer: str
    evidence_references: tuple[str, ...] = ()
    confidence: float | None = None
    epistemic_status: str = "inferred"


@dataclass(frozen=True)
class ConversationRuntimeResult:
    """Output from one conversation runtime turn."""

    state: ThreadState
    result: ChatResult
    node_trace: tuple[ConversationNodeName, ...] = ()


@dataclass(frozen=True)
class ConversationToolCall:
    """Detected tool call request inside one conversation turn."""

    name: str
    args: dict[str, Any]
    supported: bool
    diagnostic: str = ""


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
    persona_activation: PersonaActivation | None = None
    persona_turn_state: PersonaTurnState | None = None
    initial_response: DraftResponse | None = None
    tool_call: ConversationToolCall | None = None
    tool_result: str | None = None
    tool_results: tuple[str, ...] = ()
    final_response: PresentedResponse | None = None
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

    node: ConversationNodeName
    state: ConversationTurnState


class ConversationRuntime(Protocol):
    """Runtime boundary for one conversation turn."""

    def run_turn(
        self,
        state: ThreadState,
        message: str,
        thread_id: str,
        *,
        turn_id: str | None = None,
    ) -> ConversationRuntimeResult:
        """Run one user turn and return the persisted state plus user-facing result."""
        ...


class ChatAgent:
    """Memory-aware chat agent backed by a conversation runtime boundary."""

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        llm: ChatLLM | None = None,
        settings: ChatAgentSettings | None = None,
        thread_store: ThreadStore | None = None,
        memory_query_service: MemoryQueryService | None = None,
        runtime: ConversationRuntime | None = None,
    ) -> None:
        self._project_root = project_root
        self._thread_store = thread_store or ThreadStore(project_root)
        self._runtime = runtime or ConversationGraphRuntime(
            project_root,
            llm=llm,
            settings=settings,
            memory_query_service=memory_query_service,
        )

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
            runtime_result = self._runtime.run_turn(state, message, thread_id, turn_id=turn_id)
            return runtime_result.state, runtime_result.result

        return self._thread_store.update(thread_id, update)


class ConversationGraphRuntime:
    """Graph-ready linear conversation runtime.

    The node methods below keep the current behavior explicit while giving the
    later LangGraph migration a narrow replacement boundary.
    """

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        llm: ChatLLM | None = None,
        langchain_models: tuple[LangChainLLMEndpoint, ...] | None = None,
        settings: ChatAgentSettings | None = None,
        memory_query_service: MemoryQueryService | None = None,
    ) -> None:
        self._llm = llm or default_llm(project_root)
        self._langchain_models: tuple[LangChainLLMEndpoint, ...] = (
            langchain_models
            if langchain_models is not None
            else (() if llm is not None else configured_langchain_chat_models(project_root))
        )
        self._settings = settings or ChatAgentSettings.from_project(project_root)
        self._project_root = project_root
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
        from nuself.agent.graph_driver import ConversationGraphDriver

        self._graph_driver = ConversationGraphDriver(self)

    def run_turn(
        self,
        state: ThreadState,
        message: str,
        thread_id: str,
        *,
        turn_id: str | None = None,
    ) -> ConversationRuntimeResult:
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
                turn_state = self._graph_driver.run(ConversationTurnState.start(state, message, thread_id, turn_id=turn_id))
            except Exception as exc:
                duration_ms = int((time.monotonic() - started_at) * 1000)
                write_log_event(
                    "chat",
                    "turn_failed",
                    "chat turn failed",
                    project_root=self._project_root,
                    duration_ms=duration_ms,
                    status="error",
                    error=str(exc),
                )
                raise
        updated = _require_thread_state(turn_state.updated_thread_state)
        final_response = _require_presented_response(turn_state.final_response)
        duration_ms = int((time.monotonic() - started_at) * 1000)
        completed_metadata: dict[str, object] = {
            "node_trace": list(turn_state.node_trace),
            "tool_call_count": len(turn_state.tool_results),
        }
        with log_context(thread_id=thread_id, turn_id=turn_id, source="chat_runtime"):
            write_log_event(
                "chat",
                "turn_completed",
                "chat turn completed",
                project_root=self._project_root,
                duration_ms=duration_ms,
                status="completed",
                metadata=completed_metadata,
            )
        self._record_chat_turn_trace(
            user_message=message,
            final_response=final_response,
            thread_id=thread_id,
            node_trace=turn_state.node_trace,
        )
        return ConversationRuntimeResult(
            state=updated,
            result=ChatResult(
                answer=final_response.answer,
                thread_id=thread_id,
                evidence_references=final_response.evidence_references,
                confidence=final_response.confidence,
                epistemic_status=final_response.epistemic_status,
            ),
            node_trace=turn_state.node_trace,
        )

    def _record_chat_turn_trace(
        self,
        *,
        user_message: str,
        final_response: PresentedResponse,
        thread_id: str,
        node_trace: tuple[ConversationNodeName, ...],
    ) -> None:
        if not final_response.evidence_references:
            return
        evidence_refs = list(final_response.evidence_references)
        try:
            self._trace_recorder.record_chat_turn(
                title=f"Chat turn cited {evidence_refs[0]}",
                summary="Assistant reply used retrieved context cited by the final response.",
                user_input=_trace_summary(user_message),
                assistant_output=_trace_summary(final_response.answer),
                thread_id=thread_id,
                evidence_refs=evidence_refs,
                participants=["chat_agent"],
                decision_points=["Recorded because the final response cited evidence references."],
                metadata={"node_trace": list(node_trace), "epistemic_status": final_response.epistemic_status},
            )
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

    def prepare_context_node(self, state: ConversationTurnState) -> ConversationNodeResult:
        base_messages = tuple(_messages_for_prompt_context(state.persisted_state.messages))
        active_messages = (*base_messages, ThreadMessage(role="user", content=state.user_message, turn_id=state.turn_id))
        packed_memory = self._memory_query_service.pack(MemoryQuery(text=state.user_message))
        return ConversationNodeResult(
            node="prepare_context",
            state=replace(
                state,
                base_messages=base_messages,
                active_messages=active_messages,
                memory_context=packed_memory.text,
                node_trace=(*state.node_trace, "prepare_context"),
            ),
        )

    def persona_activation_node(self, state: ConversationTurnState) -> ConversationNodeResult:
        activation = PersonaActivation(
            trigger="selves available as subagent tool",
            should_escalate=False,
            escalation_reason="The main chat agent decides whether to call selves_consult.",
        )
        return ConversationNodeResult(
            node="persona_activation",
            state=replace(
                state,
                persona_activation=activation,
                persona_turn_state=None,
                node_trace=(*state.node_trace, "persona_activation"),
            ),
        )

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
            LOGGER.exception("persona discussion failed during selves consultation")
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

    def run_personas_node(self, state: ConversationTurnState) -> ConversationNodeResult:
        persona_turn_state = _require_persona_turn_state(state.persona_turn_state)
        updated_persona_turn_state = self._persona_driver.run(persona_turn_state)
        activation = state.persona_activation
        trigger = activation.trigger if activation is not None else "activated"
        if activation is not None and activation.activated:
            self._write_persona_summary_log(updated_persona_turn_state, thread_id=state.thread_id, trigger=trigger)
        should_escalate = activation.should_escalate if activation is not None else False
        escalation_reason = activation.escalation_reason if activation is not None else "no activation"
        self._write_host_discussion_decision_log(
            thread_id=state.thread_id,
            should_escalate=should_escalate,
            escalation_reason=escalation_reason,
        )
        # Host decision is the only gate for entering competitive discussion.
        try:
            if should_escalate:
                # Build a lightweight IdeaCandidate from the chat turn.
                lines = state.user_message.splitlines()
                title = (lines[0] if lines else state.user_message)[:120]
                result = self._persona_discussion_service.discuss(
                    self._build_chat_discussion_candidate(
                        thread_id=state.thread_id,
                        user_message=state.user_message,
                        title=title,
                        source_summary=updated_persona_turn_state.synthesis.summary if updated_persona_turn_state.synthesis is not None else "",
                    ),
                    on_trace_entry=lambda entry: self._write_persona_discussion_step_log(
                        state.thread_id,
                        trigger,
                        entry,
                    ),
                )
                # Log and REPL-print discussion outcome
                try:
                    write_log_event(
                        "persona",
                        "persona_discussion",
                        f"chat-triggered discussion: {result.reason}",
                        project_root=self._project_root,
                        thread_id=state.thread_id,
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
        except Exception:
            # Keep chat robust: failures in discussion should not break response
            LOGGER.exception("persona discussion failed during chat turn")
        return ConversationNodeResult(
            node="run_personas",
            state=replace(
                state,
                persona_turn_state=updated_persona_turn_state,
                node_trace=(*state.node_trace, "run_personas"),
            ),
        )

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
            candidate_type=ctype,  # type: ignore[arg-type]
            confidence=0.8,
            novelty=0.5,
            urgency=0.2,
            interruption_cost=0.1,
            evidence_refs=(),
            suggested_thread_id=thread_id,
            source_summary=source_summary,
            created_at=datetime.now(UTC).isoformat(),
        )

    def initial_response_node(self, state: ConversationTurnState) -> ConversationNodeResult:
        if state.persona_turn_state is not None and state.persona_turn_state.synthesis is not None:
            response = self._synthesize_response(state)
        else:
            prompt = self._build_prompt(state)
            response = self._complete_response(prompt)
        return ConversationNodeResult(
            node="initial_response",
            state=replace(
                state,
                initial_response=response,
                node_trace=(*state.node_trace, "initial_response"),
            ),
        )

    def detect_tool_request_node(self, state: ConversationTurnState) -> ConversationNodeResult:
        response = _require_chat_response(state.initial_response)
        tool_call = self._detect_tool_call(response)
        return ConversationNodeResult(
            node="detect_tool_request",
            state=replace(
                state,
                tool_call=tool_call,
                node_trace=(*state.node_trace, "detect_tool_request"),
            ),
        )

    def execute_tool_node(self, state: ConversationTurnState) -> ConversationNodeResult:
        response = _require_chat_response(state.initial_response)
        tool_result = self._invoke_tool(response)
        return ConversationNodeResult(
            node="execute_tool",
            state=replace(
                state,
                tool_result=tool_result,
                tool_results=(tool_result,),
                saved_messages=state.active_messages,
                node_trace=(*state.node_trace, "execute_tool"),
            ),
        )

    def finalize_response_node(self, state: ConversationTurnState) -> ConversationNodeResult:
        final_tool_results = state.tool_results
        if _is_supported_tool_call(state.tool_call):
            draft_response, final_tool_results = self._complete_after_tool_loop(state)
            final_response = self._finalize_draft_response(state, draft_response)
            saved_messages = (
                *state.active_messages,
                ThreadMessage(role="assistant", content=final_response.answer, turn_id=state.turn_id),
            )
        else:
            response = _require_chat_response(state.initial_response)
            final_response = self._finalize_draft_response(state, response)
            saved_messages = (
                *state.active_messages,
                ThreadMessage(role="assistant", content=final_response.answer, turn_id=state.turn_id),
            )
        return ConversationNodeResult(
            node="finalize_response",
            state=replace(
                state,
                final_response=final_response,
                saved_messages=saved_messages,
                tool_results=final_tool_results,
                node_trace=(*state.node_trace, "finalize_response"),
            ),
        )

    def _finalize_draft_response(self, state: ConversationTurnState, draft: ParsedChatResponse) -> PresentedResponse:
        if _is_parsed_user_facing_safe(draft):
            response = _apply_unsupported_claim_guard(_to_presented_response(draft))
            write_log_event(
                "chat",
                "final_response_completed",
                "final response accepted from chat supervisor",
                project_root=self._project_root,
                thread_id=state.thread_id,
                status="completed",
                metadata={"epistemic_status": response.epistemic_status},
            )
            return response

        write_log_event(
            "chat",
            "final_response_retry",
            "chat supervisor draft violated user-facing boundary; retrying",
            project_root=self._project_root,
            thread_id=state.thread_id,
            status="retry",
            metadata={"retry_reason": "protocol_leak"},
        )
        try:
            retry = self._complete_response(self._build_final_response_retry_prompt(state, draft))
        except Exception as exc:
            write_log_event(
                "chat",
                "final_response_failed",
                "final response retry failed",
                project_root=self._project_root,
                thread_id=state.thread_id,
                status="failed",
                error=str(exc),
                metadata={"reason": "retry_exception"},
            )
            retry = None

        if retry is not None and _is_parsed_user_facing_safe(retry):
            response = _apply_unsupported_claim_guard(_to_presented_response(retry))
            write_log_event(
                "chat",
                "final_response_completed",
                "final response accepted after retry",
                project_root=self._project_root,
                thread_id=state.thread_id,
                status="completed",
                metadata={"epistemic_status": response.epistemic_status, "retried": True},
            )
            return response

        write_log_event(
            "chat",
            "final_response_failed",
            "final response remained invalid after retry",
            project_root=self._project_root,
            thread_id=state.thread_id,
            status="failed",
            metadata={"reason": "protocol_leak"},
        )
        return PresentedResponse(
            answer=PRESENTATION_BOUNDARY_FAILURE_ANSWER,
            evidence_references=(),
            confidence=0.0,
            epistemic_status="unsupported",
        )

    def _complete_after_tool_loop(self, state: ConversationTurnState) -> tuple[ParsedChatResponse, tuple[str, ...]]:
        tool_results = list(state.tool_results)
        tool_cache: dict[str, str] = {}
        if state.tool_call is not None and state.tool_results:
            tool_cache[_tool_call_cache_key(state.tool_call.name, state.tool_call.args)] = state.tool_results[-1]
        thread_state = ThreadState(
            thread_id=state.thread_id,
            summary=state.persisted_state.summary,
            messages=list(state.active_messages),
        )
        draft_response = self._complete_response(self._build_follow_up_prompt(thread_state, tuple(tool_results)))
        iterations = 0
        while True:
            tool_call = self._detect_tool_call(draft_response)
            if not _is_supported_tool_call(tool_call):
                return draft_response, tuple(tool_results)
            if iterations >= 5:
                raise RuntimeError("fallback tool call loop exceeded 5 iterations")
            tool_result = self._invoke_tool(draft_response, tool_cache=tool_cache)
            tool_results.append(tool_result)
            draft_response = self._complete_response(self._build_follow_up_prompt(thread_state, tuple(tool_results)))
            iterations += 1

    def _complete_response(self, prompt: list[ChatMessage]) -> ParsedChatResponse:
        if self._langchain_models:
            return self._complete_response_with_langchain_tools(prompt)
        return _parse_chat_response(self._llm.complete(prompt))

    def _complete_response_with_langchain_tools(self, prompt: list[ChatMessage]) -> ParsedChatResponse:
        last_error: Exception | None = None
        for position, endpoint in enumerate(self._langchain_models):
            try:
                response = self._complete_response_with_langchain_endpoint(endpoint, prompt)
            except Exception as exc:
                last_error = exc
                remaining = self._langchain_models[position + 1 :]
                if remaining and is_endpoint_availability_error(str(exc)):
                    write_log_event(
                        "chat",
                        "llm_endpoint_failed_over",
                        "LLM endpoint failed; trying next configured endpoint",
                        project_root=self._project_root,
                        status="failed_over",
                        error=redact_llm_error(str(exc)),
                        metadata={
                            "endpoint_index": endpoint.index,
                            "base_url": endpoint.settings.base_url,
                            "model": endpoint.settings.model,
                            "next_endpoint_index": remaining[0].index,
                        },
                    )
                    continue
                raise
            record_llm_endpoint_success(self._project_root, endpoint.index)
            return response
        if last_error is not None:
            raise RuntimeError(f"all configured LLM endpoints failed: {redact_llm_error(str(last_error))}") from last_error
        return _parse_chat_response(self._llm.complete(prompt))

    def _complete_response_with_langchain_endpoint(
        self,
        endpoint: LangChainLLMEndpoint,
        prompt: list[ChatMessage],
    ) -> ParsedChatResponse:
        supervisor = LangChainChatSupervisor(
            endpoint=endpoint,
            tools=self._tools.values(),
            log_tool_call=self._log_langchain_service_tool_call,
        )
        return _structured_chat_output_to_response(supervisor.complete(prompt))

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

    def _detect_tool_call(self, response: ParsedChatResponse) -> ConversationToolCall | None:
        if response.tool is None:
            return None
        tool_name = _normalize_tool_name(response.tool)
        tool_args = response.tool_args if response.tool_args is not None else {}
        if tool_name not in self._tools:
            return ConversationToolCall(
                name=tool_name,
                args=tool_args,
                supported=False,
                diagnostic=f"unsupported tool request: {response.tool}",
            )
        return ConversationToolCall(name=tool_name, args=tool_args, supported=True)

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
            node="state_update",
            state=replace(
                state,
                updated_thread_state=updated,
                node_trace=(*state.node_trace, "state_update"),
            ),
        )

    def compression_node(self, state: ConversationTurnState) -> ConversationNodeResult:
        updated = _require_thread_state(state.updated_thread_state)
        return ConversationNodeResult(
            node="compression",
            state=replace(
                state,
                updated_thread_state=self._compress_if_needed(updated),
                node_trace=(*state.node_trace, "compression"),
            ),
        )

    def _build_prompt(self, state: ConversationTurnState) -> list[ChatMessage]:
        synthesis = None
        if state.persona_turn_state is not None:
            synthesis = state.persona_turn_state.synthesis
        prompt: list[ChatMessage] = [ChatMessage(role="system", content=self._system_prompt(state, synthesis))]
        for message in state.active_messages[-self._settings.recent_messages :]:
            prompt.append(ChatMessage(role=message.role, content=message.content))
        return prompt

    def _synthesize_response(self, state: ConversationTurnState) -> ParsedChatResponse:
        """Generate the user-facing response from persona contributions."""
        synthesis = _require_synthesis(state.persona_turn_state)
        parts: list[str] = [
            "You are the synthesizer self of NuSelf. Fuse the following internal persona perspectives into a single, coherent user-facing response.",
            "Return a JSON object with answer, evidence_references, confidence, and epistemic_status.",
            "answer must be the user-facing text. evidence_references must cite relevant memory ids or source refs when available.",
            USER_FACING_PERSONA_BOUNDARY,
            USER_FACING_PROTOCOL_BOUNDARY,
            "If you make a claim about the user's preferences, history, or other personal facts without evidence, set epistemic_status to unsupported.",
            "confidence should be a number between 0 and 1 when you can estimate it; otherwise omit it.",
            "epistemic_status should be one of grounded, inferred, uncertain, or unsupported.",
        ]
        if self._language_preference != "en":
            parts.append(f"Respond to the user in {self._language_preference}.")
        if state.memory_context != "":
            parts.extend(["", "Relevant memory context:", state.memory_context])
        if state.persisted_state.summary != "":
            parts.extend(["", "Compressed conversation so far:", state.persisted_state.summary])
        parts.extend(["", "Persona contributions:"])
        for contrib in state.persona_turn_state.contributions if state.persona_turn_state is not None else ():
            note = contrib.notes[0] if contrib.notes else ""
            parts.append(f"- {contrib.persona_id}: {note}")
        parts.extend([
            "",
            "Internal perspective fusion:",
            f"Summary: {synthesis.summary}",
            f"Perspectives involved: {', '.join(synthesis.source_personas)}",
        ])
        parts.extend(_tool_prompt_sections(self._tools.values(), self._skills))
        prompt: list[ChatMessage] = [ChatMessage(role="system", content="\n".join(parts))]
        for message in state.active_messages[-self._settings.recent_messages :]:
            prompt.append(ChatMessage(role=message.role, content=message.content))
        return self._complete_response(prompt)

    def _build_follow_up_prompt(self, state: ThreadState, tool_results: str | tuple[str, ...]) -> list[ChatMessage]:
        """Build a prompt for the follow-up after tool invocation."""
        results = (tool_results,) if isinstance(tool_results, str) else tool_results
        follow_up_system = (
            "You are NuSelf. Previous tool calls returned the following results. "
            "Use these results to either call another needed tool or generate your final answer. "
            "Return a JSON object with answer, evidence_references, confidence, and epistemic_status. "
            f"{USER_FACING_PROTOCOL_BOUNDARY}"
        )
        follow_up_system += "\nIf more required information is missing and an available tool can retrieve it, request that tool next."
        if self._language_preference != "en":
            follow_up_system += f"\n\nRespond to the user in {self._language_preference}."
        prompt: list[ChatMessage] = [
            ChatMessage(
                role="system",
                content=follow_up_system,
            )
        ]
        # Include recent message history
        for message in state.messages[-self._settings.recent_messages :]:
            prompt.append(ChatMessage(role=message.role, content=message.content))
        # Add tool results
        rendered_results = "\n\n".join(f"Tool result {index}:\n{result}" for index, result in enumerate(results, start=1))
        prompt.append(ChatMessage(role="user", content=f"Tool results so far:\n{rendered_results}"))
        return prompt

    def _build_final_response_retry_prompt(
        self,
        state: ConversationTurnState,
        draft: ParsedChatResponse,
    ) -> list[ChatMessage]:
        prompt = self._build_prompt(state)
        hints = _presentation_hints(state.user_message)
        retry_parts = [
            REGENERATE_USER_FACING_RESPONSE_PROMPT,
            "",
            "Previous invalid draft:",
            draft.answer,
            "",
            "Draft metadata:",
            f"- evidence_references: {list(draft.evidence_references)}",
            f"- confidence: {draft.confidence}",
            f"- epistemic_status: {draft.epistemic_status}",
        ]
        if hints:
            retry_parts.extend(["", "User-facing style hints:", *[f"- {hint}" for hint in hints]])
        retry_parts.append("Do not call additional tools unless the previous draft cannot be repaired without missing information.")
        return [*prompt, ChatMessage(role="user", content="\n".join(retry_parts))]

    def _system_prompt(self, state: ConversationTurnState, synthesis: "PersonaSynthesis | None" = None) -> str:
        parts = [
            "You are NuSelf, a private AI mirror for one person.",
            "Use the user's memory entries and source chunks as durable context. Do not invent memories.",
            "Return a JSON object with answer, evidence_references, confidence, and epistemic_status.",
            "answer must be the user-facing text. evidence_references must cite relevant memory ids or source refs when available.",
            USER_FACING_PERSONA_BOUNDARY,
            USER_FACING_PROTOCOL_BOUNDARY,
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
        if synthesis is not None:
            parts.extend(["", "Internal perspective fusion:", f"Summary: {synthesis.summary}", f"Perspectives involved: {', '.join(synthesis.source_personas)}"])

        parts.extend(_tool_prompt_sections(self._tools.values(), self._skills))
        return "\n".join(parts)

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

    def _invoke_tool(self, tool: ParsedChatResponse, *, tool_cache: dict[str, str] | None = None) -> str:
        """Execute a tool call and return the result."""
        tool_name = _normalize_tool_name(tool.tool or "")
        if tool_name == "" or tool_name not in self._tools:
            return f"Error: unknown tool {tool.tool}"

        tool_args_input = tool.tool_args if tool.tool_args is not None else {}
        service_component = _tool_service_component(tool_name)
        cache_key = _tool_call_cache_key(tool_name, tool_args_input)
        if tool_cache is not None:
            cached_result = tool_cache.get(cache_key)
            if cached_result is not None:
                return cached_result

        try:
            tool_obj = self._tools[tool_name]
            result = str(cast(_InvokableTool, tool_obj).invoke(tool_args_input))
            if tool_cache is not None:
                tool_cache[cache_key] = result
            if service_component is not None:
                self._write_service_tool_log(
                    tool_name,
                    service_component,
                    "completed",
                    args=tool_args_input,
                    result=result,
                )
            return result
        except TypeError as e:
            if service_component is not None:
                self._write_service_tool_log(tool_name, service_component, "failed", args=tool_args_input, error=str(e))
            return f"Error invoking {tool_name}: {e}"
        except Exception as e:
            if service_component is not None:
                self._write_service_tool_log(tool_name, service_component, "failed", args=tool_args_input, error=str(e))
            return f"Error: {e}"

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
        message = _format_tool_debug_body(args=args, result=result, error=error)
        full_body = _format_tool_debug_body(args=args, result=result, error=error, full=True)
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


def _trace_summary(text: str, limit: int = 240) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _is_local_fallback_reply(message: ThreadMessage) -> bool:
    return message.role == "assistant" and message.content.startswith("LLM API is not configured yet.")


def _messages_for_prompt_context(messages: list[ThreadMessage]) -> list[ThreadMessage]:
    return [message for message in messages if _is_prompt_context_message(message)]


def _is_prompt_context_message(message: ThreadMessage) -> bool:
    if _is_local_fallback_reply(message):
        return False
    return message.role != "assistant" or _is_user_facing_safe(message.content)


def _require_chat_response(response: ParsedChatResponse | None) -> ParsedChatResponse:
    if response is None:
        raise RuntimeError("conversation runtime response is missing")
    return response


def _require_thread_state(state: ThreadState | None) -> ThreadState:
    if state is None:
        raise RuntimeError("conversation runtime thread state is missing")
    return state


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


def _require_presented_response(response: PresentedResponse | None) -> PresentedResponse:
    if response is None:
        raise RuntimeError("conversation runtime presented response is missing")
    return response


def _require_persona_turn_state(state: PersonaTurnState | None) -> PersonaTurnState:
    if state is None:
        raise RuntimeError("conversation runtime persona turn state is missing")
    return state


def _require_synthesis(state: PersonaTurnState | None) -> PersonaSynthesis:
    if state is None or state.synthesis is None:
        raise RuntimeError("conversation runtime synthesis is missing")
    return state.synthesis


def _is_supported_tool_call(tool_call: ConversationToolCall | None) -> bool:
    return tool_call is not None and tool_call.supported


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
    return None


LEGACY_TOOL_NAME_MAP: dict[str, str] = {
    "search_memory": "memory_search",
    "count_memory": "memory_count",
    "archive_memory": "memory_archive",
    "update_memory_importance": "memory_update_importance",
    "list_pending_reflections": "reflection_list_pending",
    "dismiss_reflection": "reflection_dismiss",
    "archive_reflection": "reflection_archive",
    "list_active_reasoning_threads": "reason_list_active",
    "show_reasoning_thread": "reason_show",
    "search_trace": "trace_search",
    "show_trace": "trace_show",
}


def _normalize_tool_name(tool_name: str) -> str:
    return LEGACY_TOOL_NAME_MAP.get(tool_name, tool_name)


def _tool_call_cache_key(tool_name: str, args: dict[str, Any]) -> str:
    try:
        args_text = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        args_text = str(sorted(args.items()))
    return f"{tool_name}:{args_text}"


def _format_tool_debug_body(
    *,
    args: dict[str, Any],
    result: str | None = None,
    error: str | None = None,
    full: bool = False,
) -> str:
    limit = 0 if full else 200
    lines = [f"args: {_format_tool_debug_value(args, limit=limit)}"]
    if result is not None:
        lines.append(f"result: {_truncate_tool_debug_text(result, limit=limit)}")
    if error is not None:
        lines.append(f"error: {_truncate_tool_debug_text(error, limit=limit)}")
    return "\n".join(lines)


def _format_tool_debug_value(value: object, limit: int = 200) -> str:
    try:
        return _truncate_tool_debug_text(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str), limit=limit)
    except (TypeError, ValueError):
        return _truncate_tool_debug_text(str(value), limit=limit)


def _truncate_tool_debug_text(text: str, limit: int = 200) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _structured_chat_output_to_response(output: object) -> ParsedChatResponse:
    if isinstance(output, ChatStructuredOutput):
        return ParsedChatResponse(
            answer=output.answer,
            evidence_references=tuple(output.evidence_references),
            confidence=output.confidence,
            epistemic_status=output.epistemic_status,
        )
    if isinstance(output, dict):
        data = cast(dict[object, object], output)
        answer = data.get("answer")
        if not isinstance(answer, str):
            raise ValueError("structured chat output did not include answer")
        return ParsedChatResponse(
            answer=answer,
            evidence_references=_string_tuple(data.get("evidence_references")),
            confidence=_optional_float(data.get("confidence")),
            epistemic_status=_string_field(data.get("epistemic_status"), default="inferred") or "inferred",
        )
    raise TypeError(f"unsupported structured chat output: {type(output).__name__}")


def _tool_prompt_sections(tools: "Iterable[BaseTool]", skills: tuple[AgentSkill, ...]) -> list[str]:
    lines = [
        "",
        "Available tools:",
        "The following LangChain tools are loaded in the current NuSelf runtime.",
        "CRITICAL: When the user asks a question that a tool can answer, you MUST call the tool before generating your final answer.",
        "Do NOT answer from your training data; always use the tool to get the actual current state.",
        "Tools are bound through LangChain's native tool-calling API.",
        'Do not write visible markers such as "[Tool call: memory_search]" or JSON tool fields in the answer body.',
        "The tool will be executed and its result injected back into context. Only then generate your final answer.",
        "Tools available:",
    ]
    for tool in tools:
        args = _tool_args_signature(tool)
        lines.append(f"- {tool.name}({args}): {tool.description}")

    tools_by_service: dict[str, list[str]] = {}
    for tool in tools:
        sc = _tool_service_component(tool.name)
        if sc is not None:
            tools_by_service.setdefault(sc, []).append(tool.name)
    skill_service_map = {
        "memory": "memory",
        "reflection": "reflection",
        "reason": "reasoning",
        "trace": "trace",
        "selves": "selves",
    }
    allowed_tools_by_skill = {
        skill_name: tuple(tools_by_service.get(service, []))
        for skill_name, service in skill_service_map.items()
    }
    lines.extend(
        render_agent_skill_sections(skills, allowed_tools_by_skill=allowed_tools_by_skill)
    )
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


ParsedChatResponse: TypeAlias = DraftResponse
_PROTOCOL_FIELD_NAMES = ("answer", "evidence_references", "confidence", "epistemic_status")
_TOOL_MARKER_RE = re.compile(r"^\[Tool call:\s*(?P<tool>[A-Za-z_][A-Za-z0-9_]*)\]\s*(?P<body>.*)$", re.DOTALL)
_VISIBLE_TOOL_MARKER_RE = re.compile(r"\[Tool call:\s*[A-Za-z_][A-Za-z0-9_]*\]", re.IGNORECASE)
_TOOL_BLOCK_RE = re.compile(r"\[TOOL_CALL\](?P<body>.*?)\[/TOOL_CALL\]", re.DOTALL | re.IGNORECASE)
_TOOL_BLOCK_TOOL_RE = re.compile(r"\btool\s*(?:=>|:)\s*[\"'](?P<tool>[A-Za-z_][A-Za-z0-9_]*)[\"']")
_TOOL_BLOCK_ARGS_RE = re.compile(r"\bargs\s*(?:=>|:)\s*\{(?P<args>.*?)\}", re.DOTALL)
_QUERY_ARG_RE = re.compile(r"\bQuery\s*:\s*(?P<query>.*?)(?:\s+\bLimit\s*:|$)", re.DOTALL | re.IGNORECASE)
_LIMIT_ARG_RE = re.compile(r"\bLimit\s*:\s*(?P<limit>\d+)", re.IGNORECASE)


def _parse_chat_response(raw: str) -> ParsedChatResponse:
    stripped = raw.strip()
    tool_marker_response = _parse_tool_marker_response(stripped)
    if tool_marker_response is not None:
        return tool_marker_response
    protocol_json = _extract_protocol_json(stripped)
    if protocol_json is not None:
        try:
            parsed: object = json.loads(protocol_json)
        except json.JSONDecodeError:
            return ParsedChatResponse(answer=raw)
        if isinstance(parsed, dict) and "tool" not in cast(dict[str, object], parsed):
            try:
                structured = ChatStructuredOutput.model_validate_json(protocol_json)
                return ParsedChatResponse(
                    answer=structured.answer,
                    evidence_references=tuple(structured.evidence_references),
                    confidence=structured.confidence,
                    epistemic_status=structured.epistemic_status or "inferred",
                )
            except ValidationError:
                pass
        if isinstance(parsed, dict):
            data = cast(dict[str, object], parsed)
            answer = data.get("answer")
            tool = _string_field(data.get("tool"))
            if (not isinstance(answer, str) or answer.strip() == "") and tool is None:
                return ParsedChatResponse(answer=raw)
            evidence_references = _string_tuple(data.get("evidence_references"))
            confidence = _optional_float(data.get("confidence"))
            epistemic_status = _string_field(data.get("epistemic_status"), default="inferred") or "inferred"
            tool_args_raw = data.get("tool_args")
            tool_args = cast(dict[str, Any], tool_args_raw) if isinstance(tool_args_raw, dict) else None
            answer_text = answer if isinstance(answer, str) else ""
            return ParsedChatResponse(
                answer=answer_text,
                evidence_references=evidence_references,
                confidence=confidence,
                epistemic_status=epistemic_status,
                tool=tool,
                tool_args=tool_args,
            )
    markdown_response = _parse_markdown_chat_response(raw)
    if markdown_response is not None:
        return markdown_response
    return ParsedChatResponse(answer=raw)


def _parse_tool_marker_response(text: str) -> ParsedChatResponse | None:
    legacy_match = _TOOL_MARKER_RE.match(text)
    if legacy_match is not None:
        tool_name = _normalize_tool_name(legacy_match.group("tool"))
        return ParsedChatResponse(
            answer="",
            tool=tool_name,
            tool_args=_parse_tool_marker_args(tool_name, legacy_match.group("body")),
        )
    block_match = _TOOL_BLOCK_RE.search(text)
    if block_match is None:
        return None
    body = block_match.group("body")
    tool_match = _TOOL_BLOCK_TOOL_RE.search(body)
    if tool_match is None:
        return None
    tool_name = _normalize_tool_name(tool_match.group("tool"))
    return ParsedChatResponse(answer="", tool=tool_name, tool_args=_parse_tool_marker_args(tool_name, body))


def _parse_tool_marker_args(tool_name: str, body: str) -> dict[str, Any]:
    args_match = _TOOL_BLOCK_ARGS_RE.search(body)
    if args_match is not None:
        parsed = _parse_tool_block_args(args_match.group("args"))
        if parsed:
            return parsed
    result: dict[str, Any] = {}
    query_match = _QUERY_ARG_RE.search(body)
    if query_match is not None and query_match.group("query").strip():
        result["query"] = query_match.group("query").strip()
    limit_match = _LIMIT_ARG_RE.search(body)
    if limit_match is not None:
        result["limit"] = int(limit_match.group("limit"))
    if tool_name == "reflection_list_pending" and "limit" not in result:
        result["limit"] = 5
    return result


def _parse_tool_block_args(args_body: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, raw_value in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:=>|:)\s*(\"[^\"]*\"|'[^']*'|\d+)", args_body):
        if raw_value[:1] in {"\"", "'"}:
            result[key] = raw_value[1:-1]
        else:
            result[key] = int(raw_value)
    return result


def _extract_protocol_json(text: str) -> str | None:
    if text.startswith("{"):
        return text
    if not text.startswith("```"):
        return None
    lines = text.splitlines()
    if len(lines) < 3:
        return None
    fence = lines[0].strip().casefold()
    if fence not in {"```", "```json"}:
        return None
    closing_index = _closing_fence_index(lines)
    if closing_index is None:
        return None
    body = "\n".join(lines[1:closing_index]).strip()
    if not body.startswith("{"):
        return None
    return body


def _closing_fence_index(lines: list[str]) -> int | None:
    for index in range(len(lines) - 1, 0, -1):
        if lines[index].strip() == "```":
            return index
    return None


def _to_presented_response(response: ParsedChatResponse) -> PresentedResponse:
    return PresentedResponse(
        answer=response.answer,
        evidence_references=response.evidence_references,
        confidence=response.confidence,
        epistemic_status=response.epistemic_status,
    )


def _leaks_response_protocol(answer: str) -> bool:
    stripped = answer.strip()
    if _VISIBLE_TOOL_MARKER_RE.search(stripped) is not None or _TOOL_BLOCK_RE.search(stripped) is not None:
        return True
    if stripped.startswith("```"):
        return True
    if stripped.startswith("{") and _contains_protocol_field(stripped):
        return True
    if _starts_with_persona_attribution(stripped):
        return True
    lowered = stripped[:4000].casefold()
    return sum(1 for field_name in _PROTOCOL_FIELD_NAMES if field_name in lowered) >= 2


def _contains_protocol_field(text: str) -> bool:
    lowered = text[:4000].casefold()
    for field_name in _PROTOCOL_FIELD_NAMES:
        if f'"{field_name}"' in lowered or f"{field_name}:" in lowered:
            return True
    return False


def _is_user_facing_safe(answer: str) -> bool:
    return not _leaks_response_protocol(answer)


def _is_parsed_user_facing_safe(response: ParsedChatResponse) -> bool:
    if response.tool is not None and response.answer.strip() == "":
        return False
    return _is_user_facing_safe(response.answer)


def _starts_with_persona_attribution(text: str) -> bool:
    prefixes = ("(", "（")
    stripped = text.strip()
    if not stripped.startswith(prefixes):
        return False
    head = stripped[:240]
    return "_self" in head and (")" in head or "）" in head)


def _presentation_hints(user_message: str) -> tuple[str, ...]:
    normalized = user_message.casefold()
    hints: list[str] = []
    if any(marker in normalized for marker in ("简单", "短", "太多", "想不过来", "simple", "short", "too much")):
        hints.append("The user is asking for a shorter, simpler answer. Prefer compression and one concrete next step.")
    return tuple(hints)


def _parse_markdown_chat_response(raw: str) -> ParsedChatResponse | None:
    lines = raw.strip().splitlines()
    fields: dict[str, list[str]] = {}
    preface: list[str] = []
    current_field: str | None = None
    saw_structured_field = False
    for line in lines:
        field_name, value = _markdown_response_field(line)
        if field_name is not None:
            saw_structured_field = True
            current_field = field_name
            fields.setdefault(field_name, [])
            if value:
                fields[field_name].append(value)
            continue
        if current_field is None:
            preface.append(line)
        else:
            fields[current_field].append(line)
    answer_lines = fields.get("answer")
    if not saw_structured_field or not answer_lines:
        return None
    answer = "\n".join([*preface, *answer_lines]).strip()
    if answer == "":
        return None
    return ParsedChatResponse(
        answer=answer,
        evidence_references=_parse_markdown_evidence_references("\n".join(fields.get("evidence_references", []))),
        confidence=_optional_float("\n".join(fields.get("confidence", []))),
        epistemic_status=(
            _string_field("\n".join(fields.get("epistemic_status", [])).strip(), default="inferred") or "inferred"
        ),
        tool=_string_field("\n".join(fields.get("tool", [])).strip()),
    )


def _markdown_response_field(line: str) -> tuple[str | None, str]:
    left, separator, right = line.partition(":")
    if not separator:
        return (None, "")
    normalized = left.strip().strip("*").strip().casefold()
    normalized = normalized.replace("-", "_").replace(" ", "_")
    if normalized in {"answer", "evidence_references", "confidence", "epistemic_status", "tool"}:
        return (normalized, right.strip())
    return (None, "")


def _parse_markdown_evidence_references(value: str) -> tuple[str, ...]:
    stripped = value.strip()
    if stripped == "":
        return ()
    if stripped.startswith("[") and stripped.endswith("]"):
        stripped = stripped[1:-1].strip()
    if stripped == "":
        return ()
    return tuple(part.strip().strip("\"'") for part in stripped.split(",") if part.strip())


def _apply_unsupported_claim_guard(response: PresentedResponse) -> PresentedResponse:
    if response.evidence_references:
        return response
    if not _looks_like_personal_claim(response.answer):
        return response
    confidence = response.confidence if response.confidence is not None else 0.25
    return PresentedResponse(
        answer=response.answer,
        evidence_references=response.evidence_references,
        confidence=min(confidence, 0.25),
        epistemic_status="unsupported",
    )


def _looks_like_personal_claim(answer: str) -> bool:
    normalized = answer.casefold()
    claim_markers = (
        "you ",
        "your ",
        "remember",
        "prefer",
        "like",
        "believe",
        "think",
        "previously",
        "earlier",
        "always",
        "never",
        "history",
        "memory",
    )
    return any(marker in normalized for marker in claim_markers)


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    result: list[str] = []
    for item in cast(list[object], value):
        if isinstance(item, str) and item.strip() != "":
            result.append(item.strip())
    return tuple(result)


def _optional_float(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip() != "":
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _string_field(value: object, *, default: str | None = None) -> str | None:
    if isinstance(value, str) and value.strip() != "":
        return value
    return default
