"""LangChain-backed chat supervisor boundary."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterable
from typing import Any, Protocol, cast

from langchain.agents import create_agent as _create_agent  # pyright: ignore[reportUnknownVariableType]
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, PrivateAttr

from nuself.llm import ChatMessage, LangChainLLMEndpoint


class ChatStructuredOutput(BaseModel):
    """Structured chat response returned by the LangChain chat supervisor."""

    answer: str = Field(description="Plain user-facing answer text. Do not include internal protocol fields.")
    evidence_references: list[str] = Field(default_factory=list, description="Memory, source, or trace ids used.")
    confidence: float | None = Field(default=None, description="Optional confidence from 0.0 to 1.0.")
    epistemic_status: str = Field(default="inferred", description="One of grounded, inferred, uncertain, unsupported.")


class ToolCallLogger(Protocol):
    """Records one service tool execution."""

    def __call__(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        result: str | None = None,
        error: str | None = None,
    ) -> None: ...


class LoggedTool(BaseTool):
    """LangChain tool wrapper that logs real service executions."""

    _inner: BaseTool = PrivateAttr()
    _log_call: ToolCallLogger = PrivateAttr()
    _cache: dict[str, str] = PrivateAttr(default_factory=dict)
    _cache_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)

    def __init__(self, inner: BaseTool, *, log_call: ToolCallLogger, cache: dict[str, str]) -> None:
        super().__init__(
            name=inner.name,
            description=inner.description,
            args_schema=inner.args_schema,
            return_direct=inner.return_direct,
            response_format=inner.response_format,
        )
        self._inner = inner
        self._log_call = log_call
        self._cache = cache

    @property
    def args(self) -> dict[str, Any]:
        inner = cast(Any, self._inner)
        args = cast(object, inner.args)
        return cast(dict[str, Any], args) if isinstance(args, dict) else {}

    def invoke(self, input: Any, config: Any | None = None, **kwargs: Any) -> Any:
        tool_args = _tool_args_from_input(input)
        cache_key = _tool_call_cache_key(self.name, tool_args)
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return _cached_tool_response(input, self.name, cached)
            try:
                inner = cast(Any, self._inner)
                invoke_inner = inner.invoke
                result = invoke_inner(input, config=config, **kwargs)
            except Exception as exc:
                self._log_call(self.name, tool_args, error=str(exc))
                raise
            result_text = _tool_result_text(result)
            self._cache[cache_key] = result_text
            self._log_call(self.name, tool_args, result=result_text)
            return result

    async def ainvoke(self, input: Any, config: Any | None = None, **kwargs: Any) -> Any:
        tool_args = _tool_args_from_input(input)
        cache_key = _tool_call_cache_key(self.name, tool_args)
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return _cached_tool_response(input, self.name, cached)
            try:
                inner = cast(Any, self._inner)
                ainvoke_inner = inner.ainvoke
                result = await ainvoke_inner(input, config=config, **kwargs)
            except Exception as exc:
                self._log_call(self.name, tool_args, error=str(exc))
                raise
            result_text = _tool_result_text(result)
            self._cache[cache_key] = result_text
            self._log_call(self.name, tool_args, result=result_text)
            return result

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        inner = cast(Any, self._inner)
        invoke_inner = inner.invoke
        return invoke_inner(kwargs if kwargs else (args[0] if args else {}))


class LangChainChatSupervisor:
    """Runs one chat turn through LangChain's agent/tool runtime."""

    def __init__(
        self,
        *,
        endpoint: LangChainLLMEndpoint,
        tools: Iterable[BaseTool],
        log_tool_call: ToolCallLogger,
    ) -> None:
        self._endpoint = endpoint
        self._tools = tuple(tools)
        self._log_tool_call = log_tool_call

    def complete(self, prompt: list[ChatMessage]) -> ChatStructuredOutput:
        system_prompt, messages = _split_prompt(prompt)
        tool_cache: dict[str, str] = {}
        tools = [
            LoggedTool(tool, log_call=self._log_tool_call, cache=tool_cache)
            for tool in self._tools
        ]
        create_agent = cast(Any, _create_agent)
        agent = create_agent(
            model=self._endpoint.model,
            tools=tools,
            system_prompt=system_prompt,
            response_format=ChatStructuredOutput,
        )
        result = agent.invoke({"messages": messages})
        return _structured_response_from_agent_state(result)


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


def _structured_response_from_agent_state(result: object) -> ChatStructuredOutput:
    if not isinstance(result, dict):
        raise TypeError(f"LangChain agent returned invalid state: {type(result).__name__}")
    state = cast(dict[str, object], result)
    structured = state.get("structured_response")
    if isinstance(structured, ChatStructuredOutput):
        return structured
    if isinstance(structured, dict):
        return ChatStructuredOutput.model_validate(structured)
    messages = state.get("messages")
    if isinstance(messages, list) and messages:
        last = cast(object, messages[-1])
        content = getattr(last, "content", None)
        if isinstance(content, str):
            return ChatStructuredOutput.model_validate_json(content)
    raise ValueError("LangChain agent did not return a structured_response")


def _tool_args_from_input(input_value: object) -> dict[str, Any]:
    if isinstance(input_value, dict):
        input_dict = cast(dict[object, object], input_value)
        maybe_args = input_dict.get("args")
        if isinstance(maybe_args, dict):
            return cast(dict[str, Any], maybe_args)
        return cast(dict[str, Any], input_dict)
    return {}


def _cached_tool_response(input_value: object, tool_name: str, content: str) -> str | ToolMessage:
    if isinstance(input_value, dict):
        input_dict = cast(dict[object, object], input_value)
        call_id = input_dict.get("id")
        name = input_dict.get("name")
        if isinstance(call_id, str):
            return ToolMessage(
                content=content,
                name=name if isinstance(name, str) else tool_name,
                tool_call_id=call_id,
            )
    return content


def _tool_call_cache_key(tool_name: str, args: dict[str, Any]) -> str:
    return f"{tool_name}:{json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)}"


def _tool_result_text(result: object) -> str:
    content = getattr(result, "content", None)
    if isinstance(content, str):
        return content
    return str(result)
