"""Structured response synthesis for the conversation runtime."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, Protocol, cast

from langchain.agents import create_agent as _create_agent  # pyright: ignore[reportUnknownVariableType]
from langchain.agents.structured_output import ToolStrategy as _ToolStrategy
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.tools import BaseTool

from nuself.agent.errors import AgentInvalidOutputError
from nuself.agent.chat.types import (
    ChatStructuredOutput,
    ConversationTurnState,
)
from nuself.agent.chat.audit import (
    report_chat_failure,
    write_chat_audit,
)
from nuself.agent.failover import (
    invoke_agent_endpoint,
    is_recoverable_agent_failure,
)
from nuself.agent.middleware import (
    ToolCaptureMiddleware,
    ToolOutcome,
    ToolOutcomeLogger,
)
from nuself.agent.structured import require_structured_response
from nuself.llm import (
    LangChainLLMEndpoint,
    is_endpoint_availability_error,
    redacted_llm_diagnostic,
)
class ConversationResponseService(Protocol):
    """Typed response capability consumed by the conversation pipeline."""

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
        log_tool_outcome: ToolOutcomeLogger,
        report_tool_log_failure: Callable[[Exception], None] | None = None,
    ) -> None:
        self._project_root = project_root
        self._langchain_models = langchain_models
        self._tools = tuple(tools)
        self._log_tool_outcome = log_tool_outcome
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
        write_chat_audit(
            "final_response_completed",
            project_root=self._project_root,
            conversation_id=state.conversation_id,
            metadata={"epistemic_status": draft.epistemic_status},
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
                log_tool_outcome=self._log_tool_outcome,
                report_tool_log_failure=self._report_tool_log_failure,
            )
            try:
                return supervisor.complete(prompt)
            except Exception:
                if supervisor.has_mutating_tool_outcomes:
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
                    and is_recoverable_agent_failure(exc)
                ),
                failover_if=lambda exc: (
                    not retry_suppressed
                    and is_recoverable_agent_failure(exc)
                    and is_endpoint_availability_error(exc)
                ),
                on_retry=self._log_retry,
                retry_delay_seconds=0.25,
            )
        except Exception as exc:
            if retry_suppressed:
                self._log_retry_suppressed(
                    failed_endpoint,
                    exc,
                )
                if not is_recoverable_agent_failure(exc):
                    raise
                return _configured_failure_response_output(prompt)
            if not is_recoverable_agent_failure(exc):
                raise
            report_chat_failure(
                redacted_llm_diagnostic(exc),
                event="llm_endpoints_exhausted",
                project_root=self._project_root,
            )
        return _configured_failure_response_output(prompt)

    def _log_retry_suppressed(
        self,
        endpoint: LangChainLLMEndpoint,
        error: Exception,
    ) -> None:
        report_chat_failure(
            redacted_llm_diagnostic(error),
            event="llm_retry_suppressed_after_tool_call",
            project_root=self._project_root,
            metadata=_endpoint_metadata(endpoint),
        )

    def _log_retry(
        self,
        endpoint: LangChainLLMEndpoint,
        error: Exception,
    ) -> None:
        report_chat_failure(
            redacted_llm_diagnostic(error),
            event="llm_endpoint_retry",
            project_root=self._project_root,
            metadata=_endpoint_metadata(endpoint),
        )

class _LangChainChatSupervisor:
    """Runs one chat turn through LangChain's native agent runtime."""

    def __init__(
        self,
        *,
        endpoint: LangChainLLMEndpoint,
        tools: Iterable[BaseTool],
        log_tool_outcome: ToolOutcomeLogger,
        report_tool_log_failure: Callable[[Exception], None] | None,
    ) -> None:
        self._endpoint = endpoint
        self._tools = tuple(tools)
        self._log_tool_outcome = log_tool_outcome
        self._report_tool_log_failure = report_tool_log_failure
        self._tool_outcomes: list[ToolOutcome] = []

    @property
    def has_tool_outcomes(self) -> bool:
        return bool(self._tool_outcomes)

    @property
    def has_mutating_tool_outcomes(self) -> bool:
        readonly_names = {
            tool.name
            for tool in self._tools
            if "readonly" in (tool.tags or ())
        }
        return any(
            outcome.name not in readonly_names
            for outcome in self._tool_outcomes
        )

    def complete(
        self,
        prompt: list[BaseMessage],
    ) -> ChatStructuredOutput:
        system_prompt, messages = _split_prompt(prompt)
        middleware = ToolCaptureMiddleware(
            log_callback=self._log_tool_outcome,
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
        "model": endpoint.settings.model,
    }


def _structured_output_from_state(
    result: object,
) -> ChatStructuredOutput:
    compatible = _compatible_final_message(result)
    if compatible is not None:
        return compatible
    structured = require_structured_response(
        result,
        ChatStructuredOutput,
    )
    _reject_visible_tool_call(structured)
    return structured


def _compatible_final_message(
    result: object,
) -> ChatStructuredOutput | None:
    """Preserve a framework-native final message when structured state is absent."""

    if not isinstance(result, dict) or "structured_response" in result:
        return None
    state = cast(dict[str, object], result)
    messages = state.get("messages")
    if not isinstance(messages, list):
        return None
    message_items = cast(list[object], messages)
    for message in reversed(message_items):
        if not isinstance(message, AIMessage):
            continue
        if message.tool_calls or message.invalid_tool_calls:
            return None
        answer = message.text.strip()
        if not answer:
            return None
        response = ChatStructuredOutput(answer=answer)
        _reject_visible_tool_call(response)
        return response
    return None


def _local_response_output(
    prompt: list[BaseMessage],
) -> ChatStructuredOutput:
    last_user = _last_user_text(prompt)
    return ChatStructuredOutput(
        answer=(
            "LLM API is not configured yet. I saved the message and can use "
            "local memory/context, but real reasoning needs an API key. "
            f"Last message: {last_user}"
        )
    )


def _configured_failure_response_output(
    prompt: list[BaseMessage],
) -> ChatStructuredOutput:
    last_user = _last_user_text(prompt)
    return ChatStructuredOutput(
        answer=(
            "The configured LLM request failed, so I could not generate a "
            "model-backed reply. Check `nuself dev logs --component chat` "
            "and the endpoint provider/protocol configuration. "
            f"Last message: {last_user}"
        ),
        epistemic_status="unsupported",
    )


def _last_user_text(prompt: list[BaseMessage]) -> str:
    return next(
        (
            message.text
            for message in reversed(prompt)
            if isinstance(message, HumanMessage)
        ),
        "",
    )


def _reject_visible_tool_call(
    response: ChatStructuredOutput,
) -> None:
    if "minimax:tool_call" in response.answer:
        raise AgentInvalidOutputError(
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
