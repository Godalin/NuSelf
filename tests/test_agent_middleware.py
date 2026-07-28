from __future__ import annotations

# pyright: reportPrivateUsage=false

from typing import Any, cast

import pytest
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from nuself.agent.middleware import (
    ToolCaptureMiddleware,
    ToolOutcome,
    _tool_cache_key,
)


def _message_content(message: ToolMessage) -> str:
    content: Any = message.content  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    assert isinstance(content, str)
    return content


def _request(
    args: dict[str, Any],
    *,
    call_id: str,
) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call=cast(
            Any,
            {
                "name": "memory_count",
                "args": args,
                "id": call_id,
                "type": "tool_call",
            },
        ),
        tool=None,
        state={},
        runtime=cast(Any, None),
    )


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


def test_tool_cache_key_rejects_coercive_values() -> None:
    assert _tool_cache_key("tool", {"value": object()}) is None
    assert _tool_cache_key("tool", {"value": float("nan")}) is None
    assert _tool_cache_key("tool", cast(Any, {1: "value"})) is None


def test_tool_middleware_reuses_valid_identical_call_result() -> None:
    middleware = ToolCaptureMiddleware(cache={})
    calls = 0

    def handler(request: ToolCallRequest) -> ToolMessage:
        nonlocal calls
        calls += 1
        return ToolMessage(
            content=f"result-{calls}",
            name="memory_count",
            tool_call_id=request.tool_call["id"] or "",
        )

    first = middleware.wrap_tool_call(
        _request({"scope": "all"}, call_id="call-1"),
        handler,
    )
    second = middleware.wrap_tool_call(
        _request({"scope": "all"}, call_id="call-2"),
        handler,
    )

    assert calls == 1
    assert isinstance(first, ToolMessage)
    assert isinstance(second, ToolMessage)
    assert _message_content(first) == "result-1"
    assert _message_content(second) == "result-1"
    assert second.tool_call_id == "call-2"


def test_tool_middleware_bypasses_cache_for_non_json_arguments() -> None:
    middleware = ToolCaptureMiddleware(cache={})
    calls = 0
    invalid = object()

    def handler(request: ToolCallRequest) -> ToolMessage:
        nonlocal calls
        calls += 1
        return ToolMessage(
            content=f"result-{calls}",
            name="memory_count",
            tool_call_id=request.tool_call["id"] or "",
        )

    first = middleware.wrap_tool_call(
        _request({"value": invalid}, call_id="call-1"),
        handler,
    )
    second = middleware.wrap_tool_call(
        _request({"value": invalid}, call_id="call-2"),
        handler,
    )

    assert calls == 2
    assert isinstance(first, ToolMessage)
    assert isinstance(second, ToolMessage)
    assert _message_content(first) == "result-1"
    assert _message_content(second) == "result-2"


def test_tool_log_failure_does_not_replace_successful_result() -> None:
    observed: list[Exception] = []

    def fail_log(*_args: object, **_kwargs: object) -> None:
        raise OSError("audit unavailable")

    middleware = ToolCaptureMiddleware(
        log_callback=fail_log,
        log_error_callback=observed.append,
    )

    result = middleware.wrap_tool_call(
        _request({}, call_id="call-1"),
        lambda request: ToolMessage(
            content="completed",
            name="memory_count",
            tool_call_id=request.tool_call["id"] or "",
        ),
    )

    assert isinstance(result, ToolMessage)
    assert _message_content(result) == "completed"
    assert len(observed) == 1
    assert str(observed[0]) == "audit unavailable"


def test_tool_capture_preserves_success_and_failure_semantics() -> None:
    captured: list[ToolOutcome] = []
    middleware = ToolCaptureMiddleware(captured=captured)

    middleware.wrap_tool_call(
        _request({"nested": {"value": 1}}, call_id="success"),
        lambda request: ToolMessage(
            content="completed",
            name="memory_count",
            tool_call_id=request.tool_call["id"] or "",
        ),
    )

    def fail_tool(_request: ToolCallRequest) -> ToolMessage:
        raise LookupError("primary failure")

    with pytest.raises(LookupError, match="primary failure"):
        middleware.wrap_tool_call(
            _request({"target": "x"}, call_id="failure"),
            fail_tool,
        )

    assert captured[0].result == "completed"
    assert captured[0].error is None
    assert captured[1].result is None
    assert captured[1].error == "primary failure"
    with pytest.raises(TypeError):
        captured[0].args["new"] = "mutation"  # type: ignore[index]


def test_tool_outcome_requires_exactly_one_result_kind() -> None:
    with pytest.raises(ValueError):
        ToolOutcome(name="tool", args={})
    with pytest.raises(ValueError):
        ToolOutcome(
            name="tool",
            args={},
            result="ok",
            error="failed",
        )


def test_tool_log_failure_does_not_replace_tool_exception() -> None:
    observed: list[Exception] = []

    def fail_log(*_args: object, **_kwargs: object) -> None:
        raise OSError("audit unavailable")

    def fail_tool(_request: ToolCallRequest) -> ToolMessage:
        raise LookupError("primary tool failure")

    middleware = ToolCaptureMiddleware(
        log_callback=fail_log,
        log_error_callback=observed.append,
    )

    with pytest.raises(LookupError, match="primary tool failure"):
        middleware.wrap_tool_call(
            _request({}, call_id="call-1"),
            fail_tool,
        )

    assert len(observed) == 1
    assert str(observed[0]) == "audit unavailable"


def test_unreported_tool_log_failure_warns_without_changing_result() -> None:
    def fail_log(*_args: object, **_kwargs: object) -> None:
        raise OSError("audit unavailable")

    middleware = ToolCaptureMiddleware(log_callback=fail_log)

    with pytest.warns(RuntimeWarning, match="audit unavailable"):
        result = middleware.wrap_tool_call(
            _request({}, call_id="call-1"),
            lambda request: ToolMessage(
                content="completed",
                name="memory_count",
                tool_call_id=request.tool_call["id"] or "",
            ),
        )

    assert isinstance(result, ToolMessage)
    assert _message_content(result) == "completed"
