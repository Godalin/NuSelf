"""Memory-aware chat pipeline around a LangChain agent."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
import time

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.tools import BaseTool
from nuself.agent.chat.audit import report_chat_failure
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
from nuself.agent.chat.response import (
    ConversationResponseService,
    ConversationResponseSynthesizer,
)
from nuself.agent.chat.resources import ConversationResources
from nuself.agent.chat.state import ConversationStateManager
from nuself.agent.chat.tool_runtime import ConversationToolRuntime
from nuself.conversation import (
    CompletedTurn,
    ConversationTurnConflictError,
    ConversationMessage,
    ConversationState,
)
from nuself.agent.text import LangChainTextAgent, TextAgent
from nuself.llm import (
    LangChainLLMEndpoint,
)
from nuself.memory.audit import run_memory_observed
from nuself.runtime.context import runtime_context
from nuself.runtime.event_payloads import (
    RuntimeLogEventPayload,
    RuntimeLogLevel,
)
from nuself.runtime.events import EventPublisher
from nuself.runtime.feature_execution import FeatureExecutor
from nuself.runtime.frontend import ApprovalPort
from nuself.runtime.diagnostics import diagnostic_exception_chain
from nuself.runtime.observability import (
    publish_observed_event,
)

# ------------------------------------------------------------------
# Response types, parsing, and user-facing boundary checks
# ------------------------------------------------------------------

def trace_summary(text: str, limit: int = 240) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


# ------------------------------------------------------------------
# Conversation pipeline
# ------------------------------------------------------------------


class ConversationGraphRuntime:
    """Graph-ready conversation runtime.

    Delegates response generation (including tool calling) to LangChain
    ``create_agent`` via ``_LangChainChatSupervisor``. NuSelf owns only the
    boundaries: context preparation, response validation, state persistence,
    and conversation compression.
    """

    def __init__(
        self,
        resources: ConversationResources,
        *,
        langchain_models: tuple[LangChainLLMEndpoint, ...],
        settings: ChatAgentSettings,
        event_publisher: EventPublisher,
        response_service: ConversationResponseService | None = None,
        compression_agent: TextAgent | None = None,
        approval_port: ApprovalPort | None = None,
    ) -> None:
        project_root = resources.tools.project_root
        self._langchain_models = langchain_models
        self._settings = settings
        self._project_root = project_root
        self._event_publisher = event_publisher
        self._conversation_store = resources.conversation_store
        self._language_preference = resources.language_preference
        self._trace_recorder = resources.trace_recorder
        memory_query_service = resources.tools.memory
        self._context_preparer = ConversationContextPreparer(
            memory_query_service
        )
        self._state_manager = ConversationStateManager(
            text_agent=(
                compression_agent
                if compression_agent is not None
                else (
                    LangChainTextAgent(
                        endpoints=self._langchain_models,
                        project_root=project_root,
                        component="chat",
                    )
                    if self._langchain_models
                    else None
                )
            ),
            settings=self._settings,
            report_compression_fallback=lambda exc: report_chat_failure(
                exc,
                event="compression_fallback",
                project_root=self._project_root,
            ),
        )
        self._persona_orchestrator = ConversationPersonaOrchestrator(
            project_root=project_root,
            langchain_models=self._langchain_models,
            language_preference=self._language_preference,
            reflection_settings=resources.reflection_settings,
            memory_query_service=memory_query_service,
            persona_definitions=resources.personas,
        )
        self._tool_runtime = ConversationToolRuntime(
            resources=resources.tools,
            selves_consult=self._consult_selves_tool,
            feature_executor=FeatureExecutor(
                approvals=approval_port,
                events=self._event_publisher,
            ),
            event_publisher=self._event_publisher,
        )
        tools = self._tool_runtime.tools
        self._response_synthesizer = (
            response_service
            if response_service is not None
            else ConversationResponseSynthesizer(
                project_root=project_root,
                langchain_models=self._langchain_models,
                tools=tools.values(),
                log_tool_outcome=self._tool_runtime.log_outcome,
                report_tool_log_failure=self._tool_runtime.report_log_failure,
            )
        )
    def readonly_tools(self) -> tuple[BaseTool, ...]:
        """Return immutable readonly-tool membership."""

        return tuple(
            tool
            for tool in self._tool_runtime.tools.values()
            if "readonly" in (tool.tags or [])
        )

    def respond(
        self,
        message: str,
        conversation_id: str = "default",
        *,
        turn_id: str | None = None,
    ) -> ChatResult:
        started_at = time.monotonic()
        reused = False
        node_trace: tuple[ConversationNodeName, ...] = ()
        stage_durations_ms: tuple[tuple[str, int], ...] = ()
        context_metadata: dict[str, object] = {}
        commit_duration_ms = 0

        def update(state: ConversationState) -> tuple[ConversationState, ChatResult]:
            nonlocal reused, node_trace, stage_durations_ms, context_metadata
            completed = _completed_turn_result(
                state,
                message=message,
                conversation_id=conversation_id,
                turn_id=turn_id,
            )
            if completed is not None:
                reused = True
                return state, completed
            self._publish_turn_event(
                event="turn.started",
                message="chat turn started",
                status="started",
            )
            state, result, node_trace = self.run_turn(
                state,
                message,
                conversation_id,
                turn_id=turn_id,
                metrics_observer=observe_turn_metrics,
            )
            return state, result

        def observe_turn_metrics(
            durations: tuple[tuple[str, int], ...],
            metadata: dict[str, object],
        ) -> None:
            nonlocal stage_durations_ms, context_metadata
            stage_durations_ms = durations
            context_metadata = metadata

        def observe_commit(duration_ms: int) -> None:
            nonlocal commit_duration_ms
            commit_duration_ms = duration_ms

        with runtime_context(
            conversation_id=conversation_id,
            turn_id=turn_id,
            source="chat_runtime",
        ):
            try:
                result = self._conversation_store.update(
                    conversation_id,
                    update,
                    turn_id=turn_id,
                    user_message=(message if turn_id is not None else None),
                    commit_observer=observe_commit,
                )
            except Exception as exc:
                self._publish_turn_event(
                    event="turn.failed",
                    message="chat turn failed",
                    status="error",
                    level="error",
                    error=diagnostic_exception_chain(exc),
                    metadata={"error_type": type(exc).__name__},
                )
                raise
            duration_ms = int((time.monotonic() - started_at) * 1000)
            if reused:
                self._publish_turn_event(
                    event="turn.reused",
                    message="chat turn reused existing completed result",
                    status="completed",
                    duration_ms=duration_ms,
                )
            else:
                trace_id = self._record_chat_turn_trace(
                    user_message=message,
                    result=result,
                    conversation_id=conversation_id,
                    node_trace=node_trace,
                )
                result = replace(result, trace_id=trace_id)
                self._publish_turn_event(
                    event="turn.completed",
                    message="chat turn completed",
                    status="completed",
                    duration_ms=duration_ms,
                    metadata={
                        "node_trace": list(node_trace),
                        "stage_durations_ms": dict(stage_durations_ms),
                        "commit_duration_ms": commit_duration_ms,
                        **context_metadata,
                    },
                )
            return result

    def _publish_turn_event(
        self,
        *,
        event: str,
        message: str,
        status: str,
        level: RuntimeLogLevel = "info",
        duration_ms: int | None = None,
        error: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        payload = RuntimeLogEventPayload(
            message=message,
            level=level,
            status=status,
            duration_ms=duration_ms,
            error=error,
            metadata=metadata,
        )
        publish_observed_event(
            self._event_publisher,
            name=event,
            producer="chat",
            payload=payload.to_mapping(),
            project_root=self._project_root,
            failure_component="chat",
        )

    def run_turn(
        self,
        state: ConversationState,
        message: str,
        conversation_id: str,
        *,
        turn_id: str | None = None,
        metrics_observer: Callable[
            [tuple[tuple[str, int], ...], dict[str, object]], None
        ]
        | None = None,
    ) -> tuple[ConversationState, ChatResult, tuple[ConversationNodeName, ...]]:
        with runtime_context(
            conversation_id=conversation_id,
            turn_id=turn_id,
            source="chat_runtime",
        ):
            return self._execute_turn(
                state,
                message,
                conversation_id,
                turn_id=turn_id,
                metrics_observer=metrics_observer,
            )

    def _execute_turn(
        self,
        state: ConversationState,
        message: str,
        conversation_id: str,
        *,
        turn_id: str | None,
        metrics_observer: Callable[
            [tuple[tuple[str, int], ...], dict[str, object]], None
        ]
        | None,
    ) -> tuple[ConversationState, ChatResult, tuple[ConversationNodeName, ...]]:
        turn_state = ConversationTurnState.start(
            state,
            message,
            conversation_id,
            turn_id=turn_id,
        )
        turn_state = self._run_node(
            "prepare_context", turn_state, self.prepare_context_node
        )
        turn_state = self._run_node(
            "respond", turn_state, self.respond_node
        )
        turn_state = self._run_node(
            "state_update", turn_state, self.state_update_node
        )
        updated = _require_conversation_state(turn_state.updated_conversation_state)
        final_response = _require_final_response(turn_state.final_response)
        state = updated
        context_metadata: dict[str, object] = {
            "recent_message_count": turn_state.recent_message_count,
            "summary_present": bool(turn_state.persisted_state.summary),
            "memory_match_count": turn_state.memory_match_count,
            "profile_match_count": turn_state.profile_match_count,
            "source_match_count": turn_state.source_match_count,
            "prompt_message_count": turn_state.prompt_message_count,
        }
        if metrics_observer is not None:
            metrics_observer(
                turn_state.stage_durations_ms,
                context_metadata,
            )
        return state, ChatResult(
            answer=final_response.answer,
            conversation_id=conversation_id,
            evidence_references=tuple(final_response.evidence_references),
            confidence=final_response.confidence,
            epistemic_status=final_response.epistemic_status,
            completed_turn=CompletedTurn(
                conversation_id=conversation_id,
                start_index=state.next_message_index - 2,
                end_index=state.next_message_index,
                user_content=message,
                assistant_content=final_response.answer,
                turn_id=turn_id,
            ),
        ), turn_state.node_trace

    def _record_chat_turn_trace(
        self,
        *,
        user_message: str,
        result: ChatResult,
        conversation_id: str,
        node_trace: tuple[ConversationNodeName, ...],
    ) -> str | None:
        if not result.evidence_references:
            return None
        evidence_refs = list(result.evidence_references)
        trace = run_memory_observed(
            lambda: self._trace_recorder.record_chat_turn(
                title=f"Chat turn cited {evidence_refs[0]}",
                summary="Assistant reply used retrieved context cited by the final response.",
                user_input=trace_summary(user_message),
                assistant_output=trace_summary(result.answer),
                conversation_id=conversation_id,
                evidence_refs=evidence_refs,
                participants=["chat_agent"],
                decision_points=["Recorded because the final response cited evidence references."],
                metadata={"node_trace": list(node_trace), "epistemic_status": result.epistemic_status},
            ),
            event="chat_trace_recording_failed",
            project_root=self._project_root,
            metadata={},
        )
        return trace.id if trace is not None else None

    # ------------------------------------------------------------------
    # Typed stage wrapper
    # ------------------------------------------------------------------

    def _run_node(
        self,
        node_name: ConversationNodeName,
        state: ConversationTurnState,
        run: Callable[
            [ConversationTurnState],
            ConversationNodeResult,
        ],
    ) -> ConversationTurnState:
        started_at = time.monotonic()
        try:
            completed = run(state).state
            duration_ms = int((time.monotonic() - started_at) * 1000)
            return replace(
                completed,
                stage_durations_ms=(
                    *completed.stage_durations_ms,
                    (node_name, duration_ms),
                ),
            )
        except ConversationGraphRuntimeError:
            raise
        except Exception as exc:
            raise ConversationGraphRuntimeError(
                f"conversation graph node '{node_name}' failed while handling conversation '{state.conversation_id}'",
                node=node_name,
                node_trace=(*state.node_trace, node_name),
            ) from exc

    # ------------------------------------------------------------------
    # Pipeline stage methods
    # ------------------------------------------------------------------

    def prepare_context_node(self, state: ConversationTurnState) -> ConversationNodeResult:
        return self._context_preparer.prepare(state)

    def respond_node(self, state: ConversationTurnState) -> ConversationNodeResult:
        prompt = self._build_prompt(state)
        response = self._response_synthesizer.complete(prompt)
        final = self._response_synthesizer.finalize(state, response)
        saved = (
            *state.active_messages,
            ConversationMessage(role="assistant", content=final.answer, turn_id=state.turn_id),
        )
        return ConversationNodeResult(
            state=replace(
                state,
                final_response=final,
                saved_messages=saved,
                prompt_message_count=len(prompt),
                node_trace=(*state.node_trace, "respond"),
            ),
        )

    def state_update_node(self, state: ConversationTurnState) -> ConversationNodeResult:
        return self._state_manager.update(state)

    def compress_conversation(self, conversation_id: str) -> None:
        """Compress one committed conversation outside reply delivery."""

        def compress(
            state: ConversationState,
        ) -> tuple[ConversationState, None]:
            return self._state_manager.compress_conversation(state), None

        self._conversation_store.update(conversation_id, compress)

    def conversations_requiring_compression(self) -> tuple[str, ...]:
        """Return durable conversation work discoverable after lost wake-ups."""

        return tuple(
            conversation_id
            for conversation_id in self._conversation_store.list()
            if len(self._conversation_store.load(conversation_id).messages)
            > self._settings.summary_trigger_messages
        )

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def _build_prompt(self, state: ConversationTurnState) -> list[BaseMessage]:
        prompt: list[BaseMessage] = [
            SystemMessage(content=self._system_prompt(state))
        ]
        for message in state.active_messages[-self._settings.recent_messages :]:
            if message.role == "assistant":
                prompt.append(AIMessage(content=message.content))
            else:
                prompt.append(HumanMessage(content=message.content))
        return prompt

    def _system_prompt(self, state: ConversationTurnState) -> str:
        parts = [
            "You are NuSelf, a private AI mirror for one person.",
            "Use the user's memory entries and source chunks as durable context. Do not invent memories.",
            "Populate the structured response fields answer, evidence_references, confidence, and epistemic_status.",
            "answer must be the user-facing text. evidence_references must cite relevant memory ids or source refs when available.",
            "Use internal persona synthesis as private context only. "
            "Do not narrate internal persona composition or say which self contributed what in the user-facing answer, "
            "unless the user explicitly asks about the internal persona mechanism.",
            "The answer field must contain only the text to show to the user; "
            "do not include serialization syntax, fenced code blocks, or structured field names inside answer.",
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
    # Selves consultation (exposed as the selves_consult tool)
    # ------------------------------------------------------------------

    def _consult_selves_tool(self, topic: str, mode: str = "consult", context: str | None = None) -> str:
        return self._persona_orchestrator.consult(
            topic,
            mode=mode,
            context=context,
        )

# Module-level helpers
# ======================================================================


def _require_conversation_state(state: ConversationState | None) -> ConversationState:
    if state is None:
        raise RuntimeError("conversation runtime conversation state is missing")
    return state


def _require_final_response(response: ChatStructuredOutput | None) -> ChatStructuredOutput:
    if response is None:
        raise RuntimeError("conversation runtime presented response is missing")
    return response


def _completed_turn_result(
    state: ConversationState,
    *,
    message: str,
    conversation_id: str,
    turn_id: str | None,
) -> ChatResult | None:
    if turn_id is None or len(state.messages) < 2:
        return None
    assistant_message: ConversationMessage | None = None
    for item in reversed(state.messages):
        if item.turn_id == turn_id and item.role == "assistant":
            assistant_message = item
            break
    if assistant_message is None:
        return None
    for item in reversed(state.messages):
        if item.turn_id == turn_id and item.role == "user":
            if item.content == message:
                assistant_index = state.messages.index(assistant_message)
                user_index = state.messages.index(item)
                return ChatResult(
                    answer=assistant_message.content,
                    conversation_id=conversation_id,
                    completed_turn=CompletedTurn(
                        conversation_id=conversation_id,
                        start_index=state.message_start_index + user_index,
                        end_index=state.message_start_index + assistant_index + 1,
                        user_content=item.content,
                        assistant_content=assistant_message.content,
                        turn_id=turn_id,
                    ),
                )
            raise ConversationTurnConflictError(
                f"turn ID {turn_id!r} is already bound to different input"
            )
    return None
