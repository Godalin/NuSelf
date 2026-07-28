"""Structured response synthesis for the conversation runtime."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, Protocol, cast

from langchain.agents import create_agent as _create_agent  # pyright: ignore[reportUnknownVariableType]
from langchain.agents.structured_output import ToolStrategy as _ToolStrategy
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import BaseTool

from nuself.agent.chat.types import (
    ChatStructuredOutput,
    ConversationTurnState,
)
from nuself.agent.middleware import ToolCaptureMiddleware
from nuself.llm import (
    ChatLLM,
    ChatMessage,
    LangChainLLMEndpoint,
    is_endpoint_availability_error,
    record_llm_endpoint_success,
    redact_llm_error,
)
from nuself.logs import write_log_event
from nuself.runtime.observability import (
    report_observed_failure,
    run_observed_best_effort,
)


class ConversationResponseService(Protocol):
    """Typed response capability consumed by the conversation graph."""

    def complete(
        self,
        prompt: list[ChatMessage],
    ) -> ChatStructuredOutput: ...

    def finalize(
        self,
        state: ConversationTurnState,
        draft: ChatStructuredOutput,
    ) -> ChatStructuredOutput: ...


class ConversationResponseSynthesizer:
    """Runs model failover, native tool calling, and output validation."""

    def __init__(
        self,
        *,
        project_root: Path | None,
        llm: ChatLLM,
        langchain_models: tuple[LangChainLLMEndpoint, ...],
        tools: Iterable[BaseTool],
        log_tool_call: Callable[..., None],
        report_tool_log_failure: Callable[[Exception], None] | None = None,
    ) -> None:
        self._project_root = project_root
        self._llm = llm
        self._langchain_models = langchain_models
        self._tools = tuple(tools)
        self._log_tool_call = log_tool_call
        self._report_tool_log_failure = report_tool_log_failure

    def complete(
        self,
        prompt: list[ChatMessage],
    ) -> ChatStructuredOutput:
        if self._langchain_models:
            return self._complete_with_langchain_tools(prompt)
        return _plain_fallback_output(self._llm.complete(prompt))

    def finalize(
        self,
        state: ConversationTurnState,
        draft: ChatStructuredOutput,
    ) -> ChatStructuredOutput:
        run_observed_best_effort(
            lambda: write_log_event(
                "chat",
                "final_response_completed",
                "final response accepted from chat supervisor",
                project_root=self._project_root,
                thread_id=state.thread_id,
                status="completed",
                metadata={
                    "epistemic_status": draft.epistemic_status
                },
            ),
            component="chat",
            event="final_response_log_failed",
            message="Could not record accepted final response",
            project_root=self._project_root,
            metadata={"thread_id": state.thread_id},
        )
        return draft

    def _complete_with_langchain_tools(
        self,
        prompt: list[ChatMessage],
    ) -> ChatStructuredOutput:
        last_error: Exception | None = None
        for position, endpoint in enumerate(self._langchain_models):
            for attempt in range(2):
                try:
                    response = _LangChainChatSupervisor(
                        endpoint=endpoint,
                        tools=self._tools,
                        log_tool_call=self._log_tool_call,
                        report_tool_log_failure=self._report_tool_log_failure,
                    ).complete(prompt)
                except Exception as exc:
                    last_error = exc
                    if (
                        attempt == 0
                        and not is_endpoint_availability_error(str(exc))
                    ):
                        self._log_retry(endpoint, exc)
                        continue
                    remaining = self._langchain_models[position + 1 :]
                    if remaining:
                        self._log_failover(
                            endpoint,
                            next_endpoint=remaining[0],
                            error=exc,
                        )
                    break
                else:
                    record_llm_endpoint_success(
                        self._project_root,
                        endpoint.index,
                    )
                    return response
        if last_error is not None:
            report_observed_failure(
                RuntimeError(redact_llm_error(str(last_error))),
                component="chat",
                event="llm_endpoints_exhausted",
                message=(
                    "All LLM endpoints failed; falling back to local LLM"
                ),
                project_root=self._project_root,
                level="warning",
                status="fallback",
                metadata=None,
            )
        return _plain_fallback_output(self._llm.complete(prompt))

    def _log_retry(
        self,
        endpoint: LangChainLLMEndpoint,
        error: Exception,
    ) -> None:
        report_observed_failure(
            RuntimeError(redact_llm_error(str(error))),
            component="chat",
            event="llm_endpoint_retry",
            message="LLM endpoint error; retrying",
            project_root=self._project_root,
            level="warning",
            status="retry",
            metadata=_endpoint_metadata(endpoint),
        )

    def _log_failover(
        self,
        endpoint: LangChainLLMEndpoint,
        *,
        next_endpoint: LangChainLLMEndpoint,
        error: Exception,
    ) -> None:
        unavailable = is_endpoint_availability_error(str(error))
        report_observed_failure(
            RuntimeError(redact_llm_error(str(error))),
            component="chat",
            event=(
                "llm_endpoint_failed_over"
                if unavailable
                else "llm_endpoint_error"
            ),
            message=(
                "LLM endpoint failed; trying next configured endpoint"
            ),
            project_root=self._project_root,
            level="warning",
            status="failed_over" if unavailable else "error",
            metadata={
                **_endpoint_metadata(endpoint),
                "next_endpoint_index": next_endpoint.index,
            },
        )


class _LangChainChatSupervisor:
    """Runs one chat turn through LangChain's native agent runtime."""

    def __init__(
        self,
        *,
        endpoint: LangChainLLMEndpoint,
        tools: Iterable[BaseTool],
        log_tool_call: Callable[..., None],
        report_tool_log_failure: Callable[[Exception], None] | None,
    ) -> None:
        self._endpoint = endpoint
        self._tools = tuple(tools)
        self._log_tool_call = log_tool_call
        self._report_tool_log_failure = report_tool_log_failure

    def complete(
        self,
        prompt: list[ChatMessage],
    ) -> ChatStructuredOutput:
        system_prompt, messages = _split_prompt(prompt)
        middleware = ToolCaptureMiddleware(
            log_callback=self._log_tool_call,
            log_error_callback=self._report_tool_log_failure,
            cache={},
        )
        create_agent = cast(Any, _create_agent)
        agent = create_agent(
            model=self._endpoint.model,
            tools=list(self._tools),
            system_prompt=system_prompt,
            response_format=_ToolStrategy(
                schema=ChatStructuredOutput
            ),
            middleware=[middleware],
        )
        result = agent.invoke({"messages": messages})
        return _structured_output_from_state(result)


def _endpoint_metadata(
    endpoint: LangChainLLMEndpoint,
) -> dict[str, object]:
    return {
        "endpoint_index": endpoint.index,
        "base_url": endpoint.settings.base_url,
        "model": endpoint.settings.model,
    }


def _structured_output_from_state(
    result: object,
) -> ChatStructuredOutput:
    if not isinstance(result, dict):
        raise ValueError(
            "LangChain agent returned invalid state: "
            f"{type(result).__name__}"
        )
    state = cast(dict[str, object], result)
    if "structured_response" in state:
        structured = state["structured_response"]
        if not isinstance(structured, ChatStructuredOutput):
            raise ValueError(
                "LangChain agent returned invalid structured_response: "
                f"{type(structured).__name__}"
            )
        _reject_visible_tool_call(structured)
        return structured

    raise ValueError("LangChain agent state is missing structured_response")


def _looks_like_tool_call(text: str) -> bool:
    return "minimax:tool_call" in text


def _plain_fallback_output(raw: str) -> ChatStructuredOutput:
    if _looks_like_response_protocol(raw):
        raise ValueError(
            "Local chat fallback returned forbidden response protocol text"
        )
    parsed = ChatStructuredOutput(answer=raw)
    _reject_visible_tool_call(parsed)
    return parsed


def _looks_like_response_protocol(text: str) -> bool:
    stripped = text.lstrip()
    first_line = stripped.splitlines()[0].strip().lower() if stripped else ""
    if first_line == "```json":
        return True
    if stripped.startswith("```"):
        stripped = "\n".join(stripped.splitlines()[1:]).lstrip()
    if not stripped.startswith("{"):
        return False
    prefix = stripped[:500]
    return any(
        f'"{field_name}"' in prefix
        for field_name in (
            "answer",
            "evidence_references",
            "confidence",
            "epistemic_status",
        )
    )


def _reject_visible_tool_call(
    response: ChatStructuredOutput,
) -> None:
    if _looks_like_tool_call(response.answer):
        raise ValueError(
            "Agent produced visible tool call text instead of "
            "a structured response"
        )


def _split_prompt(
    prompt: list[ChatMessage],
) -> tuple[str | None, list[BaseMessage]]:
    system_parts: list[str] = []
    messages: list[BaseMessage] = []
    for message in prompt:
        if message.role == "system":
            system_parts.append(message.content)
        elif message.role == "assistant":
            messages.append(AIMessage(content=message.content))
        else:
            messages.append(HumanMessage(content=message.content))
    return (
        "\n\n".join(system_parts) if system_parts else None,
        messages,
    )
