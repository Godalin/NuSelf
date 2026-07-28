"""Typed daemon request handlers and registry composition."""

from __future__ import annotations

from pathlib import Path
import threading
import time
from typing import Protocol

from nuself.agent.chat import ChatAgent
from nuself.daemon.protocol import (
    REQUEST_TYPES,
    DaemonRequest,
    DaemonResponse,
    JsonValue,
    RequestType,
)
from nuself.daemon.types import WorkerHealth
from nuself.logs import log_context, write_log_event
from nuself.memory.curator import MemoryCurator, MemoryCuratorResult
from nuself.runtime.handlers import HandlerRegistry, UnknownHandlerError


class DaemonRequestState(Protocol):
    project_root: Path
    chat_agent: ChatAgent
    memory_curator: MemoryCurator
    shutdown_requested: threading.Event

    def worker_health(self) -> tuple[WorkerHealth, ...]: ...


DaemonRequestRegistry = HandlerRegistry[
    RequestType,
    [DaemonRequest, DaemonRequestState],
    DaemonResponse,
]


def build_daemon_request_registry() -> DaemonRequestRegistry:
    registry: DaemonRequestRegistry = HandlerRegistry()
    registry.register("ping", _handle_ping)
    registry.register("health", _handle_health)
    registry.register("echo", _handle_echo)
    registry.register("chat", _handle_chat)
    registry.register("shutdown", _handle_shutdown)
    if set(registry.registered_keys) != set(REQUEST_TYPES):
        missing = set(REQUEST_TYPES) - set(registry.registered_keys)
        extra = set(registry.registered_keys) - set(REQUEST_TYPES)
        raise RuntimeError(
            "daemon request registry does not match protocol: "
            f"missing={sorted(missing)} extra={sorted(extra)}"
        )
    return registry.seal()


def handle_request(
    request: DaemonRequest,
    state: DaemonRequestState,
) -> DaemonResponse:
    """Dispatch a validated daemon request through the sealed registry."""
    try:
        return DAEMON_REQUEST_HANDLERS.dispatch(
            request.type,
            request,
            state,
        )
    except UnknownHandlerError:
        return DaemonResponse.fail(
            request.request_id,
            f"unsupported request type: {request.type}",
        )


def _handle_ping(
    request: DaemonRequest,
    state: DaemonRequestState,
) -> DaemonResponse:
    del state
    return DaemonResponse.ok(request, {"message": "pong"})


def _handle_health(
    request: DaemonRequest,
    state: DaemonRequestState,
) -> DaemonResponse:
    workers: list[JsonValue] = [
        {
            "name": item.name,
            "alive": item.alive,
            "last_success_at": item.last_success_at,
            "last_error": item.last_error,
            "consecutive_failures": item.consecutive_failures,
        }
        for item in state.worker_health()
    ]
    return DaemonResponse.ok(request, {"workers": workers})


def _handle_echo(
    request: DaemonRequest,
    state: DaemonRequestState,
) -> DaemonResponse:
    del state
    return DaemonResponse.ok(request, request.payload)


def _handle_chat(
    request: DaemonRequest,
    state: DaemonRequestState,
) -> DaemonResponse:
    message = request.payload.get("message")
    if not isinstance(message, str):
        error = "chat request requires string payload field 'message'"
        write_log_event(
            "daemon",
            "request_failed",
            "chat request rejected",
            project_root=state.project_root,
            level="warning",
            request_id=request.request_id,
            status="error",
            error=error,
        )
        return DaemonResponse.fail(request.request_id, error)
    thread_id_raw = request.payload.get("thread_id")
    thread_id = (
        thread_id_raw
        if isinstance(thread_id_raw, str)
        else "default"
    )
    turn_id_raw = request.payload.get("turn_id")
    turn_id = (
        turn_id_raw if isinstance(turn_id_raw, str) else None
    )
    started_at = time.monotonic()
    with log_context(
        request_id=request.request_id,
        thread_id=thread_id,
        turn_id=turn_id,
        source="daemon",
    ):
        try:
            result = state.chat_agent.respond(
                message,
                thread_id=thread_id,
                turn_id=turn_id,
            )
            memory_update = _run_memory_curator_once(
                state.memory_curator,
                source_trace_id=result.trace_id,
            )
        except RuntimeError as exc:
            error_detail = _format_exception_chain(exc)
            write_log_event(
                "daemon",
                "chat_turn_failed",
                "daemon chat turn failed",
                project_root=state.project_root,
                level="error",
                status="error",
                error=error_detail,
            )
            return DaemonResponse.fail(
                request.request_id,
                error_detail,
            )
    duration_ms = int((time.monotonic() - started_at) * 1000)
    payload: dict[str, JsonValue] = {
        "answer": result.answer,
        "reply": result.reply,
        "thread_id": result.thread_id,
        "evidence_references": list(result.evidence_references),
        "epistemic_status": result.epistemic_status,
    }
    if result.confidence is not None:
        payload["confidence"] = result.confidence
    if memory_update is not None and memory_update.changed:
        payload["memory_update"] = memory_update.summary()
    with log_context(
        request_id=request.request_id,
        thread_id=result.thread_id,
        turn_id=turn_id,
        source="daemon",
    ):
        write_log_event(
            "daemon",
            "chat_turn_completed",
            "daemon chat turn completed",
            project_root=state.project_root,
            duration_ms=duration_ms,
            status="ok",
            metadata={
                "evidence_references": len(
                    result.evidence_references
                ),
                "memory_changed": (
                    memory_update.changed
                    if memory_update is not None
                    else False
                ),
            },
        )
    return DaemonResponse.ok(request, payload)


def _handle_shutdown(
    request: DaemonRequest,
    state: DaemonRequestState,
) -> DaemonResponse:
    write_log_event(
        "daemon",
        "shutdown_requested",
        "daemon shutdown requested",
        project_root=state.project_root,
        request_id=request.request_id,
    )
    state.shutdown_requested.set()
    return DaemonResponse.ok(
        request,
        {"message": "shutdown requested"},
    )


def _run_memory_curator_once(
    memory_curator: MemoryCurator,
    *,
    source_trace_id: str | None = None,
) -> MemoryCuratorResult | None:
    try:
        return memory_curator.run_once(
            source_trace_id=source_trace_id
        )
    except RuntimeError:
        return None


def _format_exception_chain(exc: BaseException) -> str:
    messages: list[str] = []
    current: BaseException | None = exc
    while current is not None:
        message = str(current)
        if message:
            messages.append(message)
        current = current.__cause__ or current.__context__
    return (
        " <- ".join(messages)
        if messages
        else exc.__class__.__name__
    )


DAEMON_REQUEST_HANDLERS = build_daemon_request_registry()
