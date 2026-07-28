"""Structured response synthesis for the conversation runtime."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, Protocol, cast

from langchain.agents import create_agent as _create_agent  # pyright: ignore[reportUnknownVariableType]
from langchain.agents.structured_output import ToolStrategy as _ToolStrategy
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.tools import BaseTool

from nuself.agent.chat.types import (
    ChatStructuredOutput,
    ConversationTurnState,
)
from nuself.agent.failover import invoke_agent_endpoint
from nuself.agent.middleware import ToolCaptureMiddleware, ToolOutcome
from nuself.llm import (
    LangChainLLMEndpoint,
    is_endpoint_availability_error,
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
        prompt: list[BaseMessage],
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
        langchain_models: tuple[LangChainLLMEndpoint, ...],
        tools: Iterable[BaseTool],
        log_tool_call: Callable[..., None],
        report_tool_log_failure: Callable[[Exception], None] | None = None,
    ) -> None:
        self._project_root = project_root
        self._langchain_models = langchain_models
        self._tools = tuple(tools)
        self._log_tool_call = log_tool_call
        self._report_tool_log_failure = report_tool_log_failure

    def complete(
        self,
        prompt: list[BaseMessage],
    ) -> ChatStructuredOutput:
        if self._langchain_models:
            return self._complete_with_langchain_tools(prompt)
        return _local_response_output(prompt)

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
        prompt: list[BaseMessage],
    ) -> ChatStructuredOutput:
        retry_suppressed = False
        failed_endpoint = self._langchain_models[0]

        def complete(
            endpoint: LangChainLLMEndpoint,
        ) -> ChatStructuredOutput:
            nonlocal failed_endpoint, retry_suppressed
            failed_endpoint = endpoint
            supervisor = _LangChainChatSupervisor(
                endpoint=endpoint,
                tools=self._tools,
                log_tool_call=self._log_tool_call,
                report_tool_log_failure=self._report_tool_log_failure,
            )
            try:
                return supervisor.complete(prompt)
            except Exception:
                if supervisor.has_tool_outcomes:
                    retry_suppressed = True
                raise

        try:
            return invoke_agent_endpoint(
                self._langchain_models,
                complete,
                project_root=self._project_root,
                component="chat",
                attempts_per_endpoint=2,
                retry_if=lambda exc: (
                    not retry_suppressed
                    and not is_endpoint_availability_error(str(exc))
                ),
                failover_if=lambda exc: (
                    not retry_suppressed
                    and is_endpoint_availability_error(str(exc))
                ),
                on_retry=self._log_retry,
            )
        except Exception as exc:
            if retry_suppressed:
                self._log_retry_suppressed(
                    failed_endpoint,
                    exc,
                )
                return _local_response_output(prompt)
            report_observed_failure(
                RuntimeError(redact_llm_error(str(exc))),
                component="chat",
                event="llm_endpoints_exhausted",
                message=(
                    "All LLM endpoints failed; using local response policy"
                ),
                project_root=self._project_root,
                level="warning",
                status="fallback",
                metadata=None,
            )
        return _local_response_output(prompt)

    def _log_retry_suppressed(
        self,
        endpoint: LangChainLLMEndpoint,
        error: Exception,
    ) -> None:
        report_observed_failure(
            RuntimeError(redact_llm_error(str(error))),
            component="chat",
            event="llm_retry_suppressed_after_tool_call",
            message=(
                "LLM retry and endpoint failover suppressed after tool "
                "execution"
            ),
            project_root=self._project_root,
            level="warning",
            status="fallback",
            metadata=_endpoint_metadata(endpoint),
        )

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
        self._tool_outcomes: list[ToolOutcome] = []

    @property
    def has_tool_outcomes(self) -> bool:
        return bool(self._tool_outcomes)

    def complete(
        self,
        prompt: list[BaseMessage],
    ) -> ChatStructuredOutput:
        system_prompt, messages = _split_prompt(prompt)
        middleware = ToolCaptureMiddleware(
            log_callback=self._log_tool_call,
            log_error_callback=self._report_tool_log_failure,
            captured=self._tool_outcomes,
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


def _local_response_output(
    prompt: list[BaseMessage],
) -> ChatStructuredOutput:
    last_user = next(
        (
            message.text
            for message in reversed(prompt)
            if isinstance(message, HumanMessage)
        ),
        "",
    )
    return ChatStructuredOutput(
        answer=(
            "LLM API is not configured yet. I saved the message and can use "
            "local memory/context, but real reasoning needs an API key. "
            f"Last message: {last_user}"
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
    prompt: list[BaseMessage],
) -> tuple[str | None, list[BaseMessage]]:
    system_parts: list[str] = []
    messages: list[BaseMessage] = []
    for message in prompt:
        if isinstance(message, SystemMessage):
            system_parts.append(message.text)
        else:
            messages.append(message)
    return (
        "\n\n".join(system_parts) if system_parts else None,
        messages,
    )
