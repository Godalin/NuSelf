from __future__ import annotations

# pyright: reportPrivateUsage=false

from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from typing import Any, cast

import pytest
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from nuself.agent.middleware import (
    ToolCaptureMiddleware,
    _tool_cache_key,
)
from nuself.agent.outcome import ToolOutcome
from nuself.agent.projection import LogToolOutcomeProjection
from nuself.log.reader import read_log_events
from nuself.log.record import LogEvent
from nuself.log.store import project_log_events
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
            metadata={
                "execution": execution,
                "service_component": "memory",
            },
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
    captured: list[ToolOutcome] = []
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
    assert captured == [ToolOutcome(
        name="memory_count",
        execution="mutating",
        args={},
        result="done",
    )]


def test_middleware_tracks_structured_failure_outcome() -> None:
    captured: list[ToolOutcome] = []
    middleware = ToolCaptureMiddleware(captured=captured)

    with pytest.raises(LookupError, match="private failure"):
        middleware.wrap_tool_call(
            _request({"secret": "private"}, call_id="call-1"),
            lambda _request: (_ for _ in ()).throw(
                LookupError("private failure")
            ),
        )

    assert captured == [ToolOutcome(
        name="memory_count",
        execution="readonly",
        args={"secret": "private"},
        error="private failure",
    )]


def test_suspension_is_not_a_failed_tool_execution() -> None:
    captured: list[ToolOutcome] = []
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


def test_middleware_projects_one_structured_success_outcome(
    tmp_path: Path,
) -> None:
    middleware = ToolCaptureMiddleware(
        outcomes=LogToolOutcomeProjection(
            component="chat",
            project_root=tmp_path,
        )
    )

    live: list[LogEvent] = []
    with project_log_events(live.append):
        result = middleware.wrap_tool_call(
            _request({"query": "important"}, call_id="call-1"),
            lambda request: ToolMessage(
                content="Found one memory",
                name="memory_count",
                tool_call_id=request.tool_call["id"] or "",
            ),
        )

    assert isinstance(result, ToolMessage)
    events = read_log_events(project_root=tmp_path, component="chat")
    assert [event.event for event in events] == ["service_tool_called"]
    assert live == events
    assert events[0].status == "completed"
    assert events[0].error is None
    assert events[0].metadata == {
        "service_component": "memory",
        "tool": "memory_count",
        "args": {"query": "important"},
        "result": "Found one memory",
    }


def test_middleware_projects_failure_without_replacing_exception(
    tmp_path: Path,
) -> None:
    middleware = ToolCaptureMiddleware(
        outcomes=LogToolOutcomeProjection(
            component="chat",
            project_root=tmp_path,
        )
    )

    with pytest.raises(LookupError, match="not found"):
        middleware.wrap_tool_call(
            _request({"entry_id": "m1"}, call_id="call-1"),
            lambda _request: (_ for _ in ()).throw(
                LookupError("not found")
            ),
        )

    events = read_log_events(project_root=tmp_path, component="chat")
    assert [event.event for event in events] == ["service_tool_called"]
    assert events[0].status == "failed"
    assert events[0].error == "not found"
    assert events[0].metadata == {
        "service_component": "memory",
        "tool": "memory_count",
        "args": {"entry_id": "m1"},
        "error": "not found",
    }


def test_projection_failure_does_not_replace_tool_result() -> None:
    class BrokenProjection:
        def __init__(self) -> None:
            self.failures: list[tuple[str, Exception]] = []

        def project_best_effort(
            self,
            outcome: ToolOutcome,
            *,
            service_component: str,
        ) -> None:
            del outcome, service_component
            raise OSError("log unavailable")

        def report_capture_failure(
            self,
            error: Exception,
            *,
            tool: str,
        ) -> None:
            self.failures.append((tool, error))

    projection = BrokenProjection()
    middleware = ToolCaptureMiddleware(outcomes=projection)

    result = middleware.wrap_tool_call(
        _request({}, call_id="call-1"),
        lambda request: ToolMessage(
            content="authoritative result",
            name="memory_count",
            tool_call_id=request.tool_call["id"] or "",
        ),
    )

    assert isinstance(result, ToolMessage)
    assert _content(result) == "authoritative result"
    assert len(projection.failures) == 1
    assert projection.failures[0][0] == "memory_count"
    assert isinstance(projection.failures[0][1], OSError)


def test_explicit_live_projection_crosses_worker_thread(
    tmp_path: Path,
) -> None:
    live: list[LogEvent] = []
    middleware = ToolCaptureMiddleware(
        outcomes=LogToolOutcomeProjection(
            component="chat",
            project_root=tmp_path,
            activity_sink=live.append,
        )
    )

    worker = Thread(
        target=lambda: middleware.wrap_tool_call(
            _request({"query": "threaded"}, call_id="call-1"),
            lambda request: ToolMessage(
                content="thread result",
                name="memory_count",
                tool_call_id=request.tool_call["id"] or "",
            ),
        )
    )
    worker.start()
    worker.join(timeout=2)

    assert not worker.is_alive()
    persisted = read_log_events(project_root=tmp_path, component="chat")
    assert len(persisted) == 1
    assert live == persisted
    assert live[0].metadata == {
        "service_component": "memory",
        "tool": "memory_count",
        "args": {"query": "threaded"},
        "result": "thread result",
    }
