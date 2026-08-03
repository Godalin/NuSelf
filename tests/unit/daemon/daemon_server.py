from __future__ import annotations

from concurrent.futures import Future
import threading
from pathlib import Path

import pytest
from langchain_core.messages import BaseMessage

from chat_fixtures import ConversationGraphRuntime
from inbox_fixtures import inbox_service
from nuself.agent.chat.types import (
    ChatStructuredOutput,
    ConversationTurnState,
)
from nuself.conversation import ConversationMessage, ConversationState
from conversation_fixtures import ConversationStore
from nuself.daemon.protocol import DaemonRequest
from nuself.daemon.request_handlers import handle_request
from nuself.daemon.state import DaemonState as _DaemonState
from daemon_fixtures import DaemonStateOwner
from nuself.log.reader import read_log_events
from nuself.memory.observation import MemoryObservation
from nuself.inbox.model import InboxItem
from nuself.runtime.event.publisher import EventPublisher
from nuself.runtime.messages import RuntimeEnvelope
from nuself.daemon.scheduler import (
    DaemonSchedulerCapacityError,
    DaemonTask,
)
from nuself.daemon.tasks import daemon_task

_STATE_OWNER = DaemonStateOwner()


def _new_daemon_state(project_root: Path) -> _DaemonState:
    return _STATE_OWNER.create(project_root)


def DaemonState(project_root: Path) -> _DaemonState:
    """Build the request-serving state used by these adapter tests."""

    return _STATE_OWNER.create(project_root, start=True)


@pytest.fixture(autouse=True)
def _close_states():  # pyright: ignore[reportUnusedFunction]
    yield
    _STATE_OWNER.close()


def test_daemon_resolves_configured_endpoints_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def empty_endpoints(
        project_root: Path | None = None,
        *,
        config: object | None = None,
    ) -> tuple[()]:
        nonlocal calls
        del project_root, config
        calls += 1
        return ()

    monkeypatch.setattr(
        "nuself.agent.endpoint._configured_llm_endpoints",
        empty_endpoints,
    )

    _new_daemon_state(tmp_path)

    assert calls == 1

class StaticResponseService:
    def complete(self, prompt: list[BaseMessage]) -> ChatStructuredOutput:
        return ChatStructuredOutput(
            answer="stubbed: hello",
            evidence_references=["mem_1", "source:note:0"],
            confidence=0.8,
            epistemic_status="grounded",
        )

    def finalize(
        self,
        state: ConversationTurnState,
        draft: ChatStructuredOutput,
    ) -> ChatStructuredOutput:
        return draft


def _successful_conversation_runtime(
    tmp_path: Path,
    *,
    event_publisher: EventPublisher | None = None,
) -> ConversationGraphRuntime:
    return ConversationGraphRuntime(
        tmp_path,
        response_service=StaticResponseService(),
        event_publisher=event_publisher,
    )


class FailingResponseService:
    def complete(
        self,
        prompt: list[BaseMessage],
    ) -> ChatStructuredOutput:
        del prompt
        raise RuntimeError("llm unavailable")

    def finalize(
        self,
        state: ConversationTurnState,
        draft: ChatStructuredOutput,
    ) -> ChatStructuredOutput:
        del state
        return draft


class RepeatedChainFailingResponseService:
    def complete(
        self,
        prompt: list[BaseMessage],
    ) -> ChatStructuredOutput:
        del prompt
        try:
            raise RuntimeError("same")
        except RuntimeError as exc:
            raise RuntimeError("same") from exc

    def finalize(
        self,
        state: ConversationTurnState,
        draft: ChatStructuredOutput,
    ) -> ChatStructuredOutput:
        del state
        return draft


def test_daemon_chat_uses_agent_and_persists_thread(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    state.conversation_runtime = _successful_conversation_runtime(tmp_path)
    request = DaemonRequest(type="chat", payload={"message": "hello"}, request_id="chat1")

    response = handle_request(request, state)

    assert response.status == "ok"
    assert response.payload["answer"] == "stubbed: hello"
    assert response.payload["evidence_references"] == ["mem_1", "source:note:0"]
    assert response.payload["confidence"] == 0.8
    assert response.payload["epistemic_status"] == "grounded"
    assert response.payload["conversation_id"] == "default"
    assert "node_trace" not in response.payload
    assert ConversationStore(tmp_path).list() == ["default"]


def test_daemon_chat_uses_state_event_publisher(
    tmp_path: Path,
) -> None:
    state = DaemonState(tmp_path)
    state.conversation_runtime = _successful_conversation_runtime(
        tmp_path,
        event_publisher=state.event_publisher,
    )
    received: list[RuntimeEnvelope] = []

    def collect_chat_event(event: RuntimeEnvelope) -> None:
        if event.producer == "chat":
            received.append(event)

    state.event_publisher.attach_projection(collect_chat_event)
    subscription_id = state.activity_broker.open("turn-1")

    response = handle_request(
        DaemonRequest(
            type="chat",
            payload={
                "message": "hello",
                "conversation_id": "shared-events",
                "turn_id": "turn-1",
            },
            request_id="chat-events",
        ),
        state,
    )

    assert response.status == "ok"
    assert [event.name for event in received] == [
        "turn.started",
        "turn.completed",
    ]
    audit = [
        event
        for event in read_log_events(
            project_root=tmp_path,
            component="chat",
        )
        if event.event.startswith("turn.")
    ]
    assert [event.event_id for event in audit] == [
        event.message_id for event in received
    ]
    assert all(event.request_id == "chat-events" for event in audit)
    activity = state.activity_broker.next_events(
        subscription_id,
        timeout_seconds=0,
        limit=10,
    )
    activity_lifecycle = [
        event
        for event in activity.events
        if event.event.startswith("turn.")
    ]
    assert activity.dropped_count == 0
    assert [event.event_id for event in activity_lifecycle] == [
        event.message_id for event in received
    ]


def test_daemon_chat_uses_explicit_conversation_id(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    state.conversation_runtime = _successful_conversation_runtime(tmp_path)
    request = DaemonRequest(type="chat", payload={"message": "hello", "conversation_id": "custom"}, request_id="chat2")

    response = handle_request(request, state)

    assert response.status == "ok"
    assert response.payload["conversation_id"] == "custom"
    assert ConversationStore(tmp_path).list() == ["custom"]


def test_daemon_chat_persists_turn_id_for_retry_idempotency(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    state.conversation_runtime = _successful_conversation_runtime(tmp_path)
    request = DaemonRequest(
        type="chat",
        payload={"message": "hello", "conversation_id": "default", "turn_id": "turn-retry"},
        request_id="chat-turn-id",
    )

    response = handle_request(request, state)

    assert response.status == "ok"
    stored = ConversationStore(tmp_path).load("default")
    assert stored.messages[0].turn_id == "turn-retry"
    assert stored.messages[1].turn_id == "turn-retry"


def test_daemon_chat_error_includes_root_cause(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    state.conversation_runtime = ConversationGraphRuntime(
        tmp_path,
        response_service=FailingResponseService(),
    )
    request = DaemonRequest(type="chat", payload={"message": "hello"}, request_id="chat-fail")

    response = handle_request(request, state)

    assert response.status == "error"
    assert response.error is not None
    assert "conversation graph node 'respond' failed" in response.error
    assert "llm unavailable" in response.error


def test_chat_failure_diagnostic_cannot_replace_original_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("audit store unavailable")

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        fail_log,
    )
    state = DaemonState(tmp_path)
    state.conversation_runtime = ConversationGraphRuntime(
        tmp_path,
        response_service=FailingResponseService(),
    )
    request = DaemonRequest(
        type="chat",
        payload={"message": "hello"},
        request_id="chat-failure-audit",
    )

    with pytest.warns(
        RuntimeWarning,
        match=(
            "runtime/observability_sink_failed.*"
            "component=daemon event=chat_turn_failed.*"
            "conversation graph node 'respond' failed"
        ),
    ):
        response = handle_request(request, state)

    assert response.status == "error"
    assert response.error is not None
    assert "conversation graph node 'respond' failed" in response.error
    assert "llm unavailable" in response.error
    assert "audit store unavailable" not in response.error


def test_chat_completion_audit_cannot_invalidate_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("audit store unavailable")

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        fail_log,
    )
    state = DaemonState(tmp_path)
    state.conversation_runtime = _successful_conversation_runtime(tmp_path)
    request = DaemonRequest(
        type="chat",
        payload={"message": "hello"},
        request_id="chat-completion-audit",
    )

    with pytest.warns(
        RuntimeWarning,
        match="runtime/observability_sink_failed",
    ):
        response = handle_request(request, state)

    assert response.status == "ok"
    assert response.payload["answer"] == "stubbed: hello"


def test_daemon_chat_error_deduplicates_exception_messages(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    state.conversation_runtime = ConversationGraphRuntime(
        tmp_path,
        response_service=RepeatedChainFailingResponseService(),
    )
    request = DaemonRequest(type="chat", payload={"message": "hello"}, request_id="chat-repeat-fail")

    response = handle_request(request, state)

    assert response.status == "error"
    assert response.error is not None
    assert response.error.count("same") == 1


def test_daemon_chat_requests_curation_without_running_it_inline(
    tmp_path: Path,
) -> None:
    state = DaemonState(tmp_path)
    requested: list[str] = []
    state._request_memory_curation = requested.append  # type: ignore[method-assign]
    request = DaemonRequest(type="chat", payload={"message": "remember this"}, request_id="chat1")

    response = handle_request(request, state)

    assert response.status == "ok"
    assert "memory_update" not in response.payload
    assert len(requested) == 1
    assert requested[0].startswith("obs_")


def test_daemon_chat_requests_curation_for_non_default_thread(
    tmp_path: Path,
) -> None:
    state = DaemonState(tmp_path)
    requested: list[str] = []
    state._request_memory_curation = requested.append  # type: ignore[method-assign]
    request = DaemonRequest(
        type="chat",
        payload={
            "message": "remember this",
            "conversation_id": "project",
            "turn_id": "turn-curator-failure",
        },
        request_id="chat-curator-failure",
    )

    response = handle_request(request, state)

    assert response.status == "ok"
    assert "memory_update" not in response.payload
    assert len(requested) == 1
    assert requested[0].startswith("obs_")


def test_memory_curator_worker_coalesces_requested_observation_ids(
    tmp_path: Path,
) -> None:
    state = DaemonState(tmp_path)
    calls: list[str] = []

    class RecordingCurator:
        def run_once(self, observation_id: str) -> None:
            calls.append(observation_id)
            state.shutdown_requested.set()

    state.memory_curator = RecordingCurator()  # type: ignore[assignment]
    state._request_memory_curation("obs_project")  # pyright: ignore[reportPrivateUsage]
    state._request_memory_curation("obs_project")  # pyright: ignore[reportPrivateUsage]
    state.scheduler.start()
    assert state.shutdown_requested.wait(timeout=1)
    state.scheduler.shutdown()

    assert calls == ["obs_project"]


def test_memory_curator_periodic_scan_recovers_pending_observations(
    tmp_path: Path,
) -> None:
    state = DaemonState(tmp_path)
    observations = state._memory_observations  # pyright: ignore[reportPrivateUsage]
    for source_ref in ("test:active", "test:archived"):
        observations.observe(
            MemoryObservation.create(
                source_ref=source_ref,
                fragments=("user: remember this",),
            )
        )
    expected_ids = {
        item.id for item in observations.pending()
    }
    calls: list[str] = []

    class RecordingCurator:
        def run_once(self, observation_id: str) -> None:
            calls.append(observation_id)
            if set(calls) == expected_ids:
                state.shutdown_requested.set()

    state.memory_curator = RecordingCurator()  # type: ignore[assignment]
    state.scheduler.start()
    state.scheduler.submit(
        daemon_task(
            "memory.scan",
            "periodic:memory.scan",
            "schedule:memory.scan",
        ),
        delay_seconds=0.01,
        interval_seconds=0.01,
    )
    assert state.shutdown_requested.wait(timeout=1)
    state.scheduler.shutdown()

    assert set(calls) == expected_ids


def test_committed_chat_survives_followup_admission_failure(
    tmp_path: Path,
) -> None:
    state = DaemonState(tmp_path)
    state.conversation_runtime = _successful_conversation_runtime(tmp_path)
    submit = state.scheduler.submit

    def reject_followup(
        task: DaemonTask,
        *,
        delay_seconds: float = 0.0,
        interval_seconds: float | None = None,
    ) -> Future[object]:
        if task.kind in {"memory.curate", "conversation.compress"}:
            raise DaemonSchedulerCapacityError("full")
        return submit(
            task,
            delay_seconds=delay_seconds,
            interval_seconds=interval_seconds,
        )

    state.scheduler.submit = reject_followup  # type: ignore[method-assign]

    result = state.run_chat(
        "remember this",
        conversation_id="default",
        turn_id="turn-followup-deferred",
    )

    assert result.answer == "stubbed: hello"
    assert len(ConversationStore(tmp_path).load("default").messages) == 2
    observations = state._memory_observations  # pyright: ignore[reportPrivateUsage]
    assert len(observations.pending()) == 1


def test_daemon_chat_fails_closed_when_scheduler_is_not_running(
    tmp_path: Path,
) -> None:
    state = _new_daemon_state(tmp_path)
    called = False

    class UnexpectedRuntime:
        def respond(self, *args: object, **kwargs: object) -> None:
            nonlocal called
            del args, kwargs
            called = True

    state.conversation_runtime = UnexpectedRuntime()  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="scheduler is unavailable"):
        state.run_chat("hello", conversation_id="default", turn_id=None)

    assert called is False


def test_periodic_scan_recovers_lost_compression_wakeup(
    tmp_path: Path,
) -> None:
    state = DaemonState(tmp_path)
    conversation_id = "needs-compression"
    ConversationStore(tmp_path).save(
        ConversationState(
            conversation_id=conversation_id,
            messages=[
                ConversationMessage(role="user", content=f"message {index}")
                for index in range(30)
            ],
            next_message_index=30,
        )
    )
    requested: list[str] = []
    state._request_conversation_compression = (  # type: ignore[method-assign]
        lambda value: requested.append(value) or True
    )

    state._scan_conversations(  # pyright: ignore[reportPrivateUsage]
        DaemonTask(
            "conversation.scan",
            "periodic:conversation.scan",
            "schedule:conversation.scan",
        )
    )

    assert requested == [conversation_id]


def test_daemon_ping_returns_authority_identity(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    request = DaemonRequest(type="ping", payload={}, request_id="ping1")

    response = handle_request(request, state)

    assert response.status == "ok"
    assert response.payload == {"authority_id": state.authority_id}


def test_daemon_health_returns_scheduler_snapshot(tmp_path: Path) -> None:
    state = _new_daemon_state(tmp_path)
    response = handle_request(
        DaemonRequest(type="health", payload={}, request_id="health1"),
        state,
    )
    assert response.status == "ok"
    scheduler = response.payload
    assert scheduler["running"] is False
    assert scheduler["accepting"] is True
    assert scheduler["pending"] == 0
    assert scheduler["in_flight"] == 0
    assert scheduler["capacity"] == 4

def test_daemon_shutdown_sets_flag(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    request = DaemonRequest(type="shutdown", payload={}, request_id="shutdown1")

    response = handle_request(request, state)

    assert response.status == "ok"
    assert response.payload == {}
    assert state.shutdown_requested.is_set()


def test_shutdown_audit_failure_cannot_block_accepted_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("audit store unavailable")

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        fail_log,
    )
    state = DaemonState(tmp_path)
    request = DaemonRequest(
        type="shutdown",
        payload={},
        request_id="shutdown-audit",
    )

    with pytest.warns(
        RuntimeWarning,
        match="runtime/observability_sink_failed",
    ):
        response = handle_request(request, state)

    assert response.status == "ok"
    assert response.payload == {}
    assert state.shutdown_requested.is_set()


def test_daemon_chat_rejects_non_string_message(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    request = DaemonRequest(type="chat", payload={"message": 123}, request_id="chat_bad")

    response = handle_request(request, state)

    assert response.status == "error"
    assert response.error is not None
    assert "field 'message' must be a string" in response.error


def test_daemon_handle_backstops_unexpected_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An unexpected (non-ProtocolError) failure in request handling must still
    return a failed response with the exception chain, not hang the client."""
    import io
    from types import SimpleNamespace

    from nuself.daemon import socket_server as server_mod
    from nuself.daemon.protocol import DaemonResponse

    class FakeConnection:
        def __init__(self, raw: bytes) -> None:
            self._raw = raw

        def settimeout(self, timeout: float) -> None:
            assert timeout > 0

        def recv(self, size: int) -> bytes:
            del size
            raw, self._raw = self._raw, b""
            return raw

    raw = DaemonRequest(type="ping", payload={}, request_id="boom1").to_json_line()
    server = object.__new__(server_mod.NuSelfUnixServer)
    server.state = SimpleNamespace(  # type: ignore[assignment]
        project_root=tmp_path
    )
    fake = SimpleNamespace(
        connection=FakeConnection(raw),
        rfile=io.BytesIO(raw),
        wfile=io.BytesIO(),
        server=server,
        _request_authority_root=lambda: tmp_path,
    )

    def boom(request: DaemonRequest, state: object) -> DaemonResponse:
        raise ValueError("kaboom")

    monkeypatch.setattr(server_mod, "handle_request", boom)

    server_mod.RequestHandler.handle(fake)  # type: ignore[arg-type]

    response = DaemonResponse.from_json_line(fake.wfile.getvalue())
    assert response.status == "error"
    assert response.error is not None
    assert "kaboom" in response.error


def test_daemon_background_reflection_scheduler_creates_inbox_item(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    reflected = threading.Event()
    outbox = inbox_service(tmp_path)

    class MockScheduler:
        def reflect(self, now: object = None) -> bool:
            outbox.add(
                InboxItem(
                    id="reflection-test-001",
                    title="test reflection idea",
                    body="test body",
                    status="pending",
                    idempotency_key="reflection-test-key",
                )
            )
            reflected.set()
            return True

    state.reflection_scheduler = MockScheduler()  # type: ignore[assignment]
    state.scheduler.start()
    state.scheduler.submit(
        daemon_task(
            "reflection.check",
            "periodic:reflection.check",
            "schedule:reflection.check",
        ),
        delay_seconds=0.05,
        interval_seconds=0.05,
    )
    try:
        assert reflected.wait(timeout=1)
    finally:
        state.shutdown_requested.set()
        state.scheduler.shutdown()

    entries = outbox.list()
    assert len(entries) >= 1
    assert any(e.title == "test reflection idea" for e in entries)
