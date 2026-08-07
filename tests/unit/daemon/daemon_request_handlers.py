from pathlib import Path
from typing import cast

import pytest

from nuself.agent.chat.types import ChatResult
from nuself.daemon import request_handlers
from nuself.daemon.protocol import (
    REQUEST_TYPES,
    DaemonRequest,
    DaemonResponse,
    ProtocolError,
    RequestType,
)
from nuself.daemon.request_handlers import (
    DAEMON_REQUEST_HANDLERS,
    DaemonRequestPayloadError,
    DaemonRequestState,
    build_daemon_request_registry,
    handle_request,
)
from nuself.log.store import write_log_event
from nuself.log.record import LogEvent
from nuself.runtime.context import RuntimeContext, current_runtime_context
from nuself.runtime.handlers import (
    HandlerRegistry,
    HandlerRegistryCoverageError,
    UnknownHandlerError,
)
from nuself.runtime.feature.approval import (
    ApprovalEffectRequest,
)
from nuself.runtime.feature.protocol import (
    ToolEffectRequired,
    ToolEffectResolution,
)
from nuself.daemon.payloads import (
    ChatToolEffectPayload,
    decode_chat_payload,
)


class RecordingActivityBroker:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    def publish(self, event: LogEvent) -> None:
        self.events.append(event)


class MiddlewareState:
    def __init__(self, authority_root: Path) -> None:
        self.authority_root = authority_root
        self.activity_broker = RecordingActivityBroker()


def test_chat_handler_returns_typed_tool_effect(tmp_path: Path) -> None:
    effect_request = ApprovalEffectRequest(
        component="memory",
        operation="memory_create",
        action="create",
        resource="memory",
        risk="reversible",
        summary="Create exact memory",
    )

    class ApprovalState(MiddlewareState):
        def run_chat(
            self,
            message: str,
            *,
            conversation_id: str,
            turn_id: str | None,
            effect_resolution: ToolEffectResolution | None,
        ) -> ChatResult:
            del message, conversation_id, turn_id, effect_resolution
            raise ToolEffectRequired(effect_request)

    response = handle_request(
        DaemonRequest(
            type="chat",
            payload={
                "message": "remember this",
                "conversation_id": "default",
                "turn_id": "turn-1",
            },
        ),
        cast(DaemonRequestState, ApprovalState(tmp_path)),
    )

    assert response.status == "ok"
    payload = decode_chat_payload(response.payload)
    assert isinstance(payload, ChatToolEffectPayload)
    assert payload.request == effect_request


def test_daemon_request_registry_uses_shared_catalog_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        request_handlers,
        "REQUEST_TYPES",
        tuple(
            request_type
            for request_type in REQUEST_TYPES
            if request_type != "ping"
        ),
    )

    with pytest.raises(HandlerRegistryCoverageError) as captured:
        build_daemon_request_registry()

    assert captured.value.missing == frozenset()
    assert captured.value.extra == frozenset({"ping"})


def test_registered_handler_unknown_error_is_not_reclassified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = UnknownHandlerError("nested registry lookup failed")
    registry = HandlerRegistry[
        RequestType,
        [DaemonRequest, DaemonRequestState],
        DaemonResponse,
    ]()

    def fail(
        request: DaemonRequest,
        state: DaemonRequestState,
    ) -> DaemonResponse:
        del request, state
        raise failure

    registry.register("ping", fail)
    registry.seal()
    monkeypatch.setattr(
        request_handlers,
        "DAEMON_REQUEST_HANDLERS",
        registry,
    )

    with pytest.raises(UnknownHandlerError) as captured:
        handle_request(
            DaemonRequest(
                type="ping",
                payload={},
                request_id="nested-lookup",
            ),
            cast(DaemonRequestState, MiddlewareState(tmp_path)),
        )

    assert captured.value is failure


def test_registered_handler_protocol_error_is_not_reclassified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = ProtocolError("nested protocol failed")
    registry = HandlerRegistry[
        RequestType,
        [DaemonRequest, DaemonRequestState],
        DaemonResponse,
    ]()

    def fail(
        request: DaemonRequest,
        state: DaemonRequestState,
    ) -> DaemonResponse:
        del request, state
        raise failure

    registry.register("ping", fail)
    registry.seal()
    monkeypatch.setattr(
        request_handlers,
        "DAEMON_REQUEST_HANDLERS",
        registry,
    )

    with pytest.raises(ProtocolError) as captured:
        handle_request(
            DaemonRequest(
                type="ping",
                payload={},
                request_id="nested-protocol",
            ),
            cast(DaemonRequestState, MiddlewareState(tmp_path)),
        )

    assert captured.value is failure


def test_daemon_middleware_applies_context_and_activity_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_contexts: list[RuntimeContext] = []

    def capture_ping(
        request: DaemonRequest,
        state: DaemonRequestState,
    ) -> DaemonResponse:
        observed_contexts.append(current_runtime_context())
        write_log_event(
            "daemon",
            "middleware_test",
            "middleware test",
            project_root=state.authority_root,
        )
        return DaemonResponse.ok(request)

    monkeypatch.setattr(request_handlers, "_handle_ping", capture_ping)
    registry = build_daemon_request_registry()
    state = MiddlewareState(tmp_path)
    request = DaemonRequest(
        type="ping",
        payload={},
        request_id="middleware-request",
    )

    response = registry.dispatch(
        "ping",
        request,
        cast(DaemonRequestState, state),
    )

    assert response.status == "ok"
    assert len(observed_contexts) == 1
    assert observed_contexts[0].request_id == "middleware-request"
    assert observed_contexts[0].source == "daemon"
    assert len(state.activity_broker.events) == 1
    assert state.activity_broker.events[0].request_id == "middleware-request"
    assert current_runtime_context().request_id is None


@pytest.mark.parametrize(
    "request_type",
    ["ping", "health", "shutdown"],
)
def test_control_handlers_reject_non_empty_payload_at_dispatch_boundary(
    tmp_path: Path,
    request_type: str,
) -> None:
    state = MiddlewareState(tmp_path)
    request = DaemonRequest(
        type=cast(RequestType, request_type),
        payload={"unexpected": True},
        request_id=f"{request_type}-invalid",
    )

    response = handle_request(
        request,
        cast(DaemonRequestState, state),
    )

    assert response.status == "error"
    assert response.error == "unknown payload field(s): unexpected"


def test_direct_payload_codec_failure_has_typed_source_wrapper(
    tmp_path: Path,
) -> None:
    request = DaemonRequest(
        type="ping",
        payload={"unexpected": True},
        request_id="typed-payload-error",
    )

    with pytest.raises(DaemonRequestPayloadError) as captured:
        DAEMON_REQUEST_HANDLERS.dispatch(
            "ping",
            request,
            cast(DaemonRequestState, MiddlewareState(tmp_path)),
        )

    assert str(captured.value) == "unknown payload field(s): unexpected"
    assert isinstance(captured.value.__cause__, ProtocolError)
    assert not isinstance(
        captured.value.__cause__,
        DaemonRequestPayloadError,
    )


def test_payload_rejection_survives_logging_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = MiddlewareState(tmp_path)

    def fail_log(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise OSError("log unavailable")

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        fail_log,
    )

    with pytest.warns(
        RuntimeWarning,
        match="runtime/observability_sink_failed",
    ):
        response = handle_request(
            DaemonRequest(
                type="ping",
                payload={"unexpected": True},
                request_id="rejection-log-failure",
            ),
            cast(DaemonRequestState, state),
        )

    assert response.status == "error"
    assert response.error == "unknown payload field(s): unexpected"
