from __future__ import annotations

# pyright: reportPrivateUsage=false

from types import SimpleNamespace
from typing import Any, cast

import pytest
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from nuself.agent.middleware import (
    ExecutedTool,
    ToolCaptureMiddleware,
    _tool_cache_key,
)
from nuself.runtime.feature.approval import ApprovalEffectRequest
from nuself.runtime.feature.protocol import ToolEffectRequired


def _request(
    args: dict[str, Any],
    *,
    call_id: str,
    execution: str = "readonly",
) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call=cast(Any, {
            "name": "memory_count",
            "args": args,
            "id": call_id,
            "type": "tool_call",
        }),
        tool=cast(Any, SimpleNamespace(
            metadata={"execution": execution},
        )),
        state={},
        runtime=cast(Any, None),
    )


def _content(message: ToolMessage) -> str:
    content: Any = message.content  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
    assert isinstance(content, str)
    return content


def test_tool_cache_key_is_canonical_for_json_arguments() -> None:
    first = _tool_cache_key(
        "memory_search",
        {"query": "test", "filters": {"type": "fact", "limit": 3}},
    )
    reordered = _tool_cache_key(
        "memory_search",
        {"filters": {"limit": 3, "type": "fact"}, "query": "test"},
    )

    assert first == reordered
    assert first == (
        'memory_search:{"filters":{"limit":3,"type":"fact"},'
        '"query":"test"}'
    )


def test_tool_cache_key_rejects_non_json_values() -> None:
    assert _tool_cache_key("tool", {"value": object()}) is None
    assert _tool_cache_key("tool", {"value": float("nan")}) is None


def test_middleware_deduplicates_only_within_its_own_cache() -> None:
    calls = 0

    def handler(request: ToolCallRequest) -> ToolMessage:
        nonlocal calls
        calls += 1
        return ToolMessage(
            content=f"result-{calls}",
            name="memory_count",
            tool_call_id=request.tool_call["id"] or "",
        )

    first_runtime = ToolCaptureMiddleware(cache={})
    first = first_runtime.wrap_tool_call(
        _request({}, call_id="call-1"),
        handler,
    )
    repeated = first_runtime.wrap_tool_call(
        _request({}, call_id="call-2"),
        handler,
    )
    second = ToolCaptureMiddleware(cache={}).wrap_tool_call(
        _request({}, call_id="call-3"),
        handler,
    )

    assert calls == 2
    assert isinstance(first, ToolMessage)
    assert isinstance(repeated, ToolMessage)
    assert isinstance(second, ToolMessage)
    assert _content(first) == _content(repeated) == "result-1"
    assert _content(second) == "result-2"


def test_middleware_tracks_declared_execution_and_success() -> None:
    captured: list[ExecutedTool] = []
    middleware = ToolCaptureMiddleware(captured=captured)

    result = middleware.wrap_tool_call(
        _request({}, call_id="call-1", execution="mutating"),
        lambda request: ToolMessage(
            content="done",
            name="memory_count",
            tool_call_id=request.tool_call["id"] or "",
        ),
    )

    assert isinstance(result, ToolMessage)
    assert captured == [ExecutedTool("memory_count", "mutating", True)]


def test_middleware_tracks_failure_without_logging_payloads() -> None:
    captured: list[ExecutedTool] = []
    middleware = ToolCaptureMiddleware(captured=captured)

    with pytest.raises(LookupError, match="private failure"):
        middleware.wrap_tool_call(
            _request({"secret": "private"}, call_id="call-1"),
            lambda _request: (_ for _ in ()).throw(
                LookupError("private failure")
            ),
        )

    assert captured == [ExecutedTool("memory_count", "readonly", False)]
    assert "private" not in repr(captured)


def test_suspension_is_not_a_failed_tool_execution() -> None:
    captured: list[ExecutedTool] = []
    middleware = ToolCaptureMiddleware(captured=captured)
    request = ApprovalEffectRequest(
        component="memory",
        operation="memory_create",
        action="create",
        resource="memory",
        risk="reversible",
        summary="Create memory",
    )

    with pytest.raises(ToolEffectRequired):
        middleware.wrap_tool_call(
            _request({}, call_id="call-1", execution="mutating"),
            lambda _request: (_ for _ in ()).throw(
                ToolEffectRequired(request)
            ),
        )

    assert captured == []
