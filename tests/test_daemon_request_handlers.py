from pathlib import Path
from typing import cast

import pytest

from nuself.daemon import request_handlers
from nuself.daemon.protocol import (
    REQUEST_TYPES,
    DaemonRequest,
    DaemonResponse,
)
from nuself.daemon.request_handlers import (
    DAEMON_REQUEST_HANDLERS,
    DaemonRequestState,
    build_daemon_request_registry,
)
from nuself.logs import LogEvent, write_log_event
from nuself.runtime.context import RuntimeContext, current_runtime_context


class RecordingActivityBroker:
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    def publish(self, event: LogEvent) -> None:
        self.events.append(event)


class MiddlewareState:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.activity_broker = RecordingActivityBroker()


def test_daemon_request_registry_is_complete_and_sealed() -> None:
    assert DAEMON_REQUEST_HANDLERS.sealed
    assert set(DAEMON_REQUEST_HANDLERS.registered_keys) == set(
        REQUEST_TYPES
    )


def test_daemon_request_registry_builder_isolated() -> None:
    rebuilt = build_daemon_request_registry()

    assert rebuilt is not DAEMON_REQUEST_HANDLERS
    assert rebuilt.sealed


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
            project_root=state.project_root,
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
