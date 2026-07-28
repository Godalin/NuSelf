"""Memory-aware LangGraph-backed chat agent."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
import json
import logging
import time
from pathlib import Path
from typing import Any, TypedDict, cast

from langchain.agents import create_agent as _create_agent  # pyright: ignore[reportUnknownVariableType]
from langchain.agents.structured_output import ToolStrategy as _ToolStrategy
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph  # type: ignore[reportMissingTypeStubs]
from nuself.agent.middleware import ToolCaptureMiddleware
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
from nuself.agent.chat.state import ConversationStateManager
from nuself.agent.skills import AgentSkill, load_agent_skills, render_tool_placeholders
from nuself.agent.chat.thread import ThreadMessage, ThreadState, ThreadStore
from nuself.agent.tools import build_langchain_chat_tools
from nuself.agent.tool_utils import tool_log_metadata
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
from nuself.logs import log_context, write_log_event
from nuself.memory.query import MemoryQueryService
from nuself.memory.repository import MemoryEntryRepository
from nuself.memory.source_repository import SourceRepository
from nuself.profile.repository import ProfileItemRepository
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
            skill.name: _tools_for_skill(skill, self._tools)
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
        parts.extend(_tool_prompt_sections(self._tools.values()))
        if any(tool.name == "reason_propose" for tool in self._tools.values()):
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
        tool = self._tools.get(tool_name)
        if tool is None or not tool.metadata:
            return
        service_component = tool.metadata.get("service_component")
        if not isinstance(service_component, str):
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
        return self._persona_orchestrator.consult(
            topic,
            mode=mode,
            context=context,
        )

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Tool logging
    # ------------------------------------------------------------------

    def _write_service_tool_log(
        self,
        tool_name: str,
        service_component: str,
        status: str,
        *,
        args: dict[str, Any],
        result: str | None = None,
        error: str | None = None,
    ) -> None:
        write_log_event(
            "chat",
            "service_tool_called",
            f"{tool_name} {status}",
            project_root=self._project_root,
            status=status,
            error=error,
            metadata=tool_log_metadata(
                args=args,
                result=result,
                error=error,
                service_component=service_component,
                tool_name=tool_name,
            ),
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
            metadata={"service_component": "skill"},
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


def _tools_for_skill(skill: AgentSkill, tools: dict[str, BaseTool]) -> tuple[str, ...]:
    explicit = tuple(name for name in skill.allowed_tools if name in tools)
    if explicit:
        return explicit
    service_component = "reasoning" if skill.name == "reason" else skill.name
    return tuple(
        name for name, tool in tools.items()
        if tool.metadata and tool.metadata.get("service_component") == service_component
    )


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
