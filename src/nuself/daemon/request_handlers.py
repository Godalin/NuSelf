"""Typed daemon request handlers and registry composition."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, TypeVar

from nuself.agent.chat import ConversationGraphRuntime
from nuself.daemon.activity import (
    ActivityBroker,
    ActivitySubscriptionNotFound,
)
from nuself.daemon.payloads import (
    DaemonIdentityPayload,
    ActivityCloseRequestPayload,
    ActivityCloseResponsePayload,
    ActivityEventsResponsePayload,
    ActivityNextRequestPayload,
    ActivityOpenRequestPayload,
    ActivityOpenResponsePayload,
    ChatRequestPayload,
    ChatResponsePayload,
    EmptyRequestPayload,
    HealthResponsePayload,
    MessagePayload,
    WorkerHealthPayload,
)
from nuself.daemon.protocol import (
    REQUEST_TYPES,
    DaemonRequest,
    DaemonResponse,
    JsonValue,
    ProtocolError,
    RequestType,
)
from nuself.daemon.request_audit import (
    report_daemon_request_failure,
    write_daemon_request_audit,
)
from nuself.daemon.types import WorkerHealth
from nuself.logs import project_log_events
from nuself.runtime.handlers import HandlerRegistry
from nuself.runtime.context import runtime_context
from nuself.runtime.diagnostics import diagnostic_exception_message

RequestPayload = TypeVar("RequestPayload")


class DaemonRequestPayloadError(ProtocolError):
    """A direct request-specific payload codec rejected its input."""


class DaemonRequestState(Protocol):
    project_root: Path
    authority_id: str
    conversation_runtime: ConversationGraphRuntime
    shutdown_requested: threading.Event
    activity_broker: ActivityBroker

    def worker_health(self) -> tuple[WorkerHealth, ...]: ...
    def request_memory_curation(self, thread_id: str) -> None: ...


DaemonRequestRegistry = HandlerRegistry[
    RequestType,
    [DaemonRequest, DaemonRequestState],
    DaemonResponse,
]


def build_daemon_request_registry() -> DaemonRequestRegistry:
    registry: DaemonRequestRegistry = HandlerRegistry()
    registry.use(_daemon_request_scope)
    registry.register("ping", _handle_ping)
    registry.register("health", _handle_health)
    registry.register("echo", _handle_echo)
    registry.register("chat", _handle_chat)
    registry.register("shutdown", _handle_shutdown)
    registry.register("activity_open", _handle_activity_open)
    registry.register("activity_next", _handle_activity_next)
    registry.register("activity_close", _handle_activity_close)
    return registry.seal(expected_keys=REQUEST_TYPES)


def _daemon_request_scope(
    request_type: RequestType,
    next_handler: Callable[
        [DaemonRequest, DaemonRequestState],
        DaemonResponse,
    ],
    request: DaemonRequest,
    state: DaemonRequestState,
) -> DaemonResponse:
    del request_type
    with runtime_context(
        request_id=request.request_id,
        source="daemon",
    ), project_log_events(state.activity_broker.publish):
        return next_handler(request, state)


def handle_request(
    request: DaemonRequest,
    state: DaemonRequestState,
) -> DaemonResponse:
    """Dispatch a validated daemon request through the sealed registry."""
    if request.type not in DAEMON_REQUEST_HANDLERS.registered_keys:
        return DaemonResponse.fail(
            request.request_id,
            f"unsupported request type: {request.type}",
        )
    try:
        return DAEMON_REQUEST_HANDLERS.dispatch(
            request.type,
            request,
            state,
        )
    except DaemonRequestPayloadError as exc:
        response = DaemonResponse.fail_from_exception(
            request.request_id,
            exc,
        )
        report_daemon_request_failure(
            exc,
            event="request_rejected",
            project_root=state.project_root,
            request_id=request.request_id,
            metadata={"request_type": request.type},
        )
        return response


def _handle_ping(
    request: DaemonRequest,
    state: DaemonRequestState,
) -> DaemonResponse:
    _decode_request_payload(EmptyRequestPayload.from_wire, request.payload)
    return DaemonResponse.ok(
        request,
        DaemonIdentityPayload(
            message="pong",
            authority_id=state.authority_id,
        ).to_wire(),
    )


def _handle_health(
    request: DaemonRequest,
    state: DaemonRequestState,
) -> DaemonResponse:
    _decode_request_payload(EmptyRequestPayload.from_wire, request.payload)
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
    chat_request = _decode_request_payload(
        ChatRequestPayload.from_wire,
        request.payload,
    )
    started_at = time.monotonic()
    with runtime_context(
        thread_id=chat_request.thread_id,
        turn_id=chat_request.turn_id,
    ):
        try:
            result = state.conversation_runtime.respond(
                chat_request.message,
                thread_id=chat_request.thread_id,
                turn_id=chat_request.turn_id,
            )
        except RuntimeError as exc:
            report_daemon_request_failure(
                exc,
                event="chat_turn_failed",
                project_root=state.project_root,
                request_id=request.request_id,
            )
            return DaemonResponse.fail_from_exception(
                request.request_id,
                exc,
                include_chain=True,
            )
        state.request_memory_curation(result.thread_id)
    duration_ms = int((time.monotonic() - started_at) * 1000)
    payload = ChatResponsePayload(
        answer=result.answer,
        reply=result.reply,
        thread_id=result.thread_id,
        evidence_references=result.evidence_references,
        epistemic_status=result.epistemic_status,
        confidence=result.confidence,
    )
    with runtime_context(
        thread_id=result.thread_id,
        turn_id=chat_request.turn_id,
    ):
        write_daemon_request_audit(
            "chat_turn_completed",
            project_root=state.project_root,
            request_id=request.request_id,
            duration_ms=duration_ms,
            metadata={
                "evidence_references": len(result.evidence_references),
                "memory_curation_requested": True,
            },
        )
    return DaemonResponse.ok(request, payload.to_wire())


def _handle_shutdown(
    request: DaemonRequest,
    state: DaemonRequestState,
) -> DaemonResponse:
    _decode_request_payload(EmptyRequestPayload.from_wire, request.payload)
    state.shutdown_requested.set()
    write_daemon_request_audit(
        "shutdown_requested",
        project_root=state.project_root,
        request_id=request.request_id,
    )
    return DaemonResponse.ok(
        request,
        MessagePayload("shutdown requested").to_wire(),
    )


def _handle_activity_open(
    request: DaemonRequest,
    state: DaemonRequestState,
) -> DaemonResponse:
    payload = _decode_request_payload(
        ActivityOpenRequestPayload.from_wire,
        request.payload,
    )
    subscription_id = state.activity_broker.open(payload.turn_id)
    return DaemonResponse.ok(
        request,
        ActivityOpenResponsePayload(subscription_id).to_wire(),
    )


def _handle_activity_next(
    request: DaemonRequest,
    state: DaemonRequestState,
) -> DaemonResponse:
    payload = _decode_request_payload(
        ActivityNextRequestPayload.from_wire,
        request.payload,
    )
    try:
        batch = state.activity_broker.next_events(
            payload.subscription_id,
            timeout_seconds=payload.timeout_ms / 1000,
            limit=payload.limit,
        )
    except ActivitySubscriptionNotFound as exc:
        return DaemonResponse.fail_from_exception(request.request_id, exc)
    return DaemonResponse.ok(
        request,
        ActivityEventsResponsePayload(
            batch.events,
            dropped_count=batch.dropped_count,
        ).to_wire(),
    )


def _handle_activity_close(
    request: DaemonRequest,
    state: DaemonRequestState,
) -> DaemonResponse:
    payload = _decode_request_payload(
        ActivityCloseRequestPayload.from_wire,
        request.payload,
    )
    return DaemonResponse.ok(
        request,
        ActivityCloseResponsePayload(
            state.activity_broker.close(payload.subscription_id)
        ).to_wire(),
    )


def _decode_request_payload(
    decoder: Callable[[dict[str, JsonValue]], RequestPayload],
    payload: dict[str, JsonValue],
) -> RequestPayload:
    try:
        return decoder(payload)
    except ProtocolError as exc:
        raise DaemonRequestPayloadError(
            diagnostic_exception_message(exc)
        ) from exc


DAEMON_REQUEST_HANDLERS = build_daemon_request_registry()
