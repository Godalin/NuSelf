"""Typed daemon request handlers and registry composition."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Protocol

from nuself.agent.chat import ChatAgent
from nuself.daemon.activity import (
    ActivityBroker,
    ActivitySubscriptionNotFound,
)
from nuself.daemon.payloads import (
    ActivityCloseRequestPayload,
    ActivityCloseResponsePayload,
    ActivityEventsResponsePayload,
    ActivityNextRequestPayload,
    ActivityOpenRequestPayload,
    ActivityOpenResponsePayload,
    ChatRequestPayload,
    ChatResponsePayload,
    HealthResponsePayload,
    MessagePayload,
    WorkerHealthPayload,
)
from nuself.daemon.protocol import (
    REQUEST_TYPES,
    DaemonRequest,
    DaemonResponse,
    ProtocolError,
    RequestType,
)
from nuself.daemon.types import WorkerHealth
from nuself.logs import (
    log_context,
    observe_log_events,
    write_log_event,
)
from nuself.memory.curator import MemoryCurator, MemoryCuratorResult
from nuself.runtime.handlers import HandlerRegistry, UnknownHandlerError
from nuself.runtime.observability import run_observed_best_effort


class DaemonRequestState(Protocol):
    project_root: Path
    chat_agent: ChatAgent
    memory_curator: MemoryCurator
    shutdown_requested: threading.Event
    activity_broker: ActivityBroker

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
    registry.register("activity_open", _handle_activity_open)
    registry.register("activity_next", _handle_activity_next)
    registry.register("activity_close", _handle_activity_close)
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
        with observe_log_events(state.activity_broker.publish):
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
    return DaemonResponse.ok(
        request,
        MessagePayload("pong").to_wire(),
    )


def _handle_health(
    request: DaemonRequest,
    state: DaemonRequestState,
) -> DaemonResponse:
    payload = HealthResponsePayload(
        tuple(WorkerHealthPayload.from_health(item) for item in state.worker_health())
    )
    return DaemonResponse.ok(request, payload.to_wire())


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
    try:
        chat_request = ChatRequestPayload.from_wire(request.payload)
    except ProtocolError as exc:
        error = str(exc)
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
    started_at = time.monotonic()
    with log_context(
        request_id=request.request_id,
        thread_id=chat_request.thread_id,
        turn_id=chat_request.turn_id,
        source="daemon",
    ):
        try:
            result = state.chat_agent.respond(
                chat_request.message,
                thread_id=chat_request.thread_id,
                turn_id=chat_request.turn_id,
            )
            memory_update = _run_memory_curator_once(
                state.memory_curator,
                project_root=state.project_root,
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
    payload = ChatResponsePayload(
        answer=result.answer,
        reply=result.reply,
        thread_id=result.thread_id,
        evidence_references=result.evidence_references,
        epistemic_status=result.epistemic_status,
        confidence=result.confidence,
        memory_update=(
            memory_update.summary()
            if memory_update is not None and memory_update.changed
            else None
        ),
    )
    with log_context(
        request_id=request.request_id,
        thread_id=result.thread_id,
        turn_id=chat_request.turn_id,
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
                "evidence_references": len(result.evidence_references),
                "memory_changed": (
                    memory_update.changed if memory_update is not None else False
                ),
            },
        )
    return DaemonResponse.ok(request, payload.to_wire())


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
        MessagePayload("shutdown requested").to_wire(),
    )


def _handle_activity_open(
    request: DaemonRequest,
    state: DaemonRequestState,
) -> DaemonResponse:
    try:
        payload = ActivityOpenRequestPayload.from_wire(request.payload)
    except ProtocolError as exc:
        return DaemonResponse.fail(request.request_id, str(exc))
    subscription_id = state.activity_broker.open(payload.turn_id)
    return DaemonResponse.ok(
        request,
        ActivityOpenResponsePayload(subscription_id).to_wire(),
    )


def _handle_activity_next(
    request: DaemonRequest,
    state: DaemonRequestState,
) -> DaemonResponse:
    try:
        payload = ActivityNextRequestPayload.from_wire(request.payload)
        events = state.activity_broker.next_events(
            payload.subscription_id,
            timeout_seconds=payload.timeout_ms / 1000,
            limit=payload.limit,
        )
    except (ProtocolError, ActivitySubscriptionNotFound) as exc:
        return DaemonResponse.fail(request.request_id, str(exc))
    return DaemonResponse.ok(
        request,
        ActivityEventsResponsePayload(events).to_wire(),
    )


def _handle_activity_close(
    request: DaemonRequest,
    state: DaemonRequestState,
) -> DaemonResponse:
    try:
        payload = ActivityCloseRequestPayload.from_wire(request.payload)
    except ProtocolError as exc:
        return DaemonResponse.fail(request.request_id, str(exc))
    return DaemonResponse.ok(
        request,
        ActivityCloseResponsePayload(
            state.activity_broker.close(payload.subscription_id)
        ).to_wire(),
    )


def _run_memory_curator_once(
    memory_curator: MemoryCurator,
    *,
    project_root: Path,
    source_trace_id: str | None = None,
) -> MemoryCuratorResult | None:
    return run_observed_best_effort(
        lambda: memory_curator.run_once(
            source_trace_id=source_trace_id
        ),
        component="memory",
        event="post_chat_curation_failed",
        message="post-chat memory curation failed",
        project_root=project_root,
        metadata={"source_trace_id": source_trace_id},
        errors=(RuntimeError,),
    )


def _format_exception_chain(exc: BaseException) -> str:
    messages: list[str] = []
    current: BaseException | None = exc
    while current is not None:
        message = str(current)
        if message:
            messages.append(message)
        current = current.__cause__ or current.__context__
    return " <- ".join(messages) if messages else exc.__class__.__name__


DAEMON_REQUEST_HANDLERS = build_daemon_request_registry()
