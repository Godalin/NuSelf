from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, cast

import pytest
from langchain_core.messages import BaseMessage

from nuself.agent.capabilities import AgentCapabilitySnapshot
from nuself.agent.chat import (
    ChatStructuredOutput,
    ConversationGraphRuntime,
    ConversationTurnState,
    ThreadStore,
)
from nuself.daemon.protocol import DaemonRequest
from nuself.daemon.request_handlers import handle_request
from nuself.daemon.state import DaemonState
from nuself.daemon.workers import (
    DaemonWorkerJoinTimeoutError,
    DaemonWorkerSupervisor,
)
from nuself.logs import read_log_events, runtime_event_log_sink
from nuself.memory.curator import MemoryCuratorResult
from nuself.notification import NotificationOutbox, OutboxEntry
from nuself.runtime.context import (
    RuntimeContext,
    current_runtime_context,
    runtime_context,
)
from nuself.runtime.events import EventPublisher
from nuself.runtime.messages import RuntimeEnvelope


def _worker_supervisor(
    tmp_path: Path,
    shutdown_requested: threading.Event | None = None,
) -> DaemonWorkerSupervisor:
    publisher = EventPublisher()
    publisher.attach_projection(runtime_event_log_sink(tmp_path))
    return DaemonWorkerSupervisor(
        tmp_path,
        (
            shutdown_requested
            if shutdown_requested is not None
            else threading.Event()
        ),
        publisher,
    )


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


def test_daemon_state_owns_worker_event_and_audit_composition(
    tmp_path: Path,
) -> None:
    state = DaemonState(tmp_path)
    received: list[RuntimeEnvelope] = []
    state.event_publisher.attach_projection(received.append)
    state.shutdown_requested.set()

    state.start_background_memory_curator()
    state.stop_background_memory_curator()

    assert [event.name for event in received] == [
        "worker.started",
        "worker.stopped",
    ]
    audit = [
        event
        for event in read_log_events(
            project_root=tmp_path,
            component="daemon",
        )
        if event.event.startswith("worker.")
    ]
    assert [event.event_id for event in audit] == [
        event.message_id for event in received
    ]


def test_daemon_chat_uses_agent_and_persists_thread(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    state.conversation_runtime = _successful_conversation_runtime(tmp_path)
    request = DaemonRequest(type="chat", payload={"message": "hello"}, request_id="chat1")

    response = handle_request(request, state)

    assert response.status == "ok"
    assert isinstance(response.payload["reply"], str)
    assert response.payload["reply"] == "stubbed: hello"
    assert response.payload["answer"] == response.payload["reply"]
    assert response.payload["evidence_references"] == ["mem_1", "source:note:0"]
    assert response.payload["confidence"] == 0.8
    assert response.payload["epistemic_status"] == "grounded"
    assert response.payload["thread_id"] == "default"
    assert "node_trace" not in response.payload
    assert ThreadStore(tmp_path).list() == ["default"]


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
                "thread_id": "shared-events",
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


def test_daemon_chat_uses_explicit_thread_id(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    state.conversation_runtime = _successful_conversation_runtime(tmp_path)
    request = DaemonRequest(type="chat", payload={"message": "hello", "thread_id": "custom"}, request_id="chat2")

    response = handle_request(request, state)

    assert response.status == "ok"
    assert response.payload["thread_id"] == "custom"
    assert ThreadStore(tmp_path).list() == ["custom"]


def test_daemon_chat_persists_turn_id_for_retry_idempotency(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    state.conversation_runtime = _successful_conversation_runtime(tmp_path)
    request = DaemonRequest(
        type="chat",
        payload={"message": "hello", "thread_id": "default", "turn_id": "turn-retry"},
        request_id="chat-turn-id",
    )

    response = handle_request(request, state)

    assert response.status == "ok"
    stored = ThreadStore(tmp_path).load("default")
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


class FakeChangedCurator:
    def run_once(self, **kwargs: object) -> MemoryCuratorResult:
        return MemoryCuratorResult(
            processed_messages=2,
            created=1,
            updated=0,
            ignored=0,
            log_path=Path("memory.log"),
        )


class RecoverableFailingCurator:
    def run_once(self, **kwargs: object) -> MemoryCuratorResult:
        try:
            raise RuntimeError("curator backend unavailable")
        except RuntimeError as exc:
            raise RuntimeError("post-chat curation failed") from exc


class UnexpectedFailingCurator:
    def run_once(self, **kwargs: object) -> MemoryCuratorResult:
        raise ValueError("curator invariant broken")


def test_daemon_chat_runs_memory_curator_after_reply(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    state.memory_curator = FakeChangedCurator()  # type: ignore[assignment]
    request = DaemonRequest(type="chat", payload={"message": "remember this"}, request_id="chat1")

    response = handle_request(request, state)

    assert response.status == "ok"
    assert response.payload["memory_update"] == "processed=2 created=1 updated=0 ignored=0"


def test_daemon_chat_observes_recoverable_curator_failure(
    tmp_path: Path,
) -> None:
    state = DaemonState(tmp_path)
    state.memory_curator = RecoverableFailingCurator()  # type: ignore[assignment]
    request = DaemonRequest(
        type="chat",
        payload={
            "message": "remember this",
            "thread_id": "project",
            "turn_id": "turn-curator-failure",
        },
        request_id="chat-curator-failure",
    )

    response = handle_request(request, state)

    assert response.status == "ok"
    assert "memory_update" not in response.payload
    event = read_log_events(project_root=tmp_path, component="memory")[-1]
    assert event.event == "post_chat_curation_failed"
    assert event.status == "degraded"
    assert event.error == (
        "post-chat curation failed <- curator backend unavailable"
    )
    assert event.request_id == "chat-curator-failure"
    assert event.thread_id == "project"
    assert event.turn_id == "turn-curator-failure"
    assert event.source == "daemon"


def test_daemon_chat_does_not_degrade_unexpected_curator_failure(
    tmp_path: Path,
) -> None:
    state = DaemonState(tmp_path)
    state.memory_curator = UnexpectedFailingCurator()  # type: ignore[assignment]
    request = DaemonRequest(
        type="chat",
        payload={"message": "remember this"},
        request_id="chat-curator-invariant",
    )

    with pytest.raises(ValueError, match="curator invariant broken"):
        handle_request(request, state)


def test_daemon_ping_returns_pong(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    request = DaemonRequest(type="ping", payload={}, request_id="ping1")

    response = handle_request(request, state)

    assert response.status == "ok"
    assert response.payload["message"] == "pong"
    assert response.payload["authority_id"] == state.authority_id


def test_daemon_health_returns_worker_snapshots(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    response = handle_request(
        DaemonRequest(type="health", payload={}, request_id="health1"),
        state,
    )
    assert response.status == "ok"
    workers = response.payload["workers"]
    assert isinstance(workers, list)
    names: set[str] = set()
    for item in workers:
        if isinstance(item, dict):
            name = item.get("name")
            if isinstance(name, str):
                names.add(name)
    assert names == {
        "memory_curator",
        "reflection_scheduler",
        "reason_scheduler",
        "export_worker",
        "notification_delivery",
    }


def test_reason_scheduler_uses_public_agent_capability_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = DaemonState(tmp_path)
    snapshot_calls = 0

    class CapabilityRuntime:
        def capability_snapshot(self) -> AgentCapabilitySnapshot:
            nonlocal snapshot_calls
            snapshot_calls += 1
            return AgentCapabilitySnapshot(
                endpoints=(),
                readonly_tools=(),
            )

    captured: dict[str, object] = {}

    def build_scheduler(
        project_root: Path,
        **kwargs: object,
    ) -> object:
        captured["project_root"] = project_root
        captured.update(kwargs)
        return object()

    def start_worker(name: str) -> None:
        captured["started"] = name

    state.conversation_runtime = cast(Any, CapabilityRuntime())
    monkeypatch.setattr(
        "nuself.daemon.state.ReasonScheduler",
        build_scheduler,
    )
    monkeypatch.setattr(
        cast(Any, state)._worker_supervisor,
        "start",
        start_worker,
    )

    state.start_background_reason_scheduler()

    assert snapshot_calls == 1
    assert captured["project_root"] == tmp_path
    assert captured["readonly_tools"] == ()
    assert captured["langchain_models"] == ()
    assert captured["started"] == "reason_scheduler"


def test_memory_curator_worker_survives_unexpected_error(
    tmp_path: Path,
) -> None:
    state = DaemonState(tmp_path)
    state.memory_curator_interval_seconds = 0.01

    class BrokenCurator:
        def run_once(self) -> None:
            raise ValueError("bad curator data")

    state.memory_curator = BrokenCurator()  # type: ignore[assignment]
    state.start_background_memory_curator()
    deadline = time.monotonic() + 1.0
    health = state.worker_health()[0]
    while health.consecutive_failures == 0 and time.monotonic() < deadline:
        time.sleep(0.01)
        health = state.worker_health()[0]

    assert health.alive is True
    assert health.consecutive_failures >= 1
    assert health.last_error == "bad curator data"
    state.shutdown_requested.set()
    state.stop_background_memory_curator()


def test_worker_supervisor_records_escaping_target_and_context(
    tmp_path: Path,
) -> None:
    shutdown_requested = threading.Event()
    supervisor = _worker_supervisor(tmp_path, shutdown_requested)
    observed: list[RuntimeContext] = []

    def fail_target() -> None:
        observed.append(current_runtime_context())
        raise ValueError("target escaped")

    supervisor.register(
        "memory_curator",
        thread_name="test-supervised-worker",
        target=fail_target,
    )
    supervisor.seal()

    supervisor.start("memory_curator")
    supervisor.join("memory_curator", timeout=1)

    assert observed[0].source == "daemon.worker.memory_curator"
    health = next(
        item for item in supervisor.health() if item.name == "memory_curator"
    )
    assert health.alive is False
    assert health.consecutive_failures == 1
    assert health.last_error == "target escaped"
    lifecycle = [
        event
        for event in read_log_events(
            project_root=tmp_path,
            component="daemon",
        )
        if event.event.startswith("worker.")
    ]
    assert [event.event for event in lifecycle] == [
        "worker.started",
        "worker.failed",
        "worker.stopped",
    ]
    failed = lifecycle[1]
    assert failed.source == "daemon.worker.memory_curator"
    assert failed.metadata == {
        "worker": "memory_curator",
        "operation_event": "worker_exited_unexpectedly",
        "error_type": "ValueError",
    }
    assert failed.error == "target escaped"


def test_worker_error_log_failure_does_not_stop_scheduled_loop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nuself import logs
    from nuself.runtime import observability

    state = DaemonState(tmp_path)
    state.memory_curator_interval_seconds = 0.01
    calls = 0

    class FailOnceCurator:
        def run_once(self) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ValueError("first iteration failed")
            state.shutdown_requested.set()

    state.memory_curator = FailOnceCurator()  # type: ignore[assignment]

    def fail_error_log(
        *args: object,
        **kwargs: object,
    ) -> object:
        raise OSError("worker log unavailable")

    monkeypatch.setattr(
        logs,
        "write_runtime_event",
        fail_error_log,
    )
    monkeypatch.setattr(
        observability,
        "write_log_event",
        fail_error_log,
    )

    with pytest.warns(
        RuntimeWarning,
        match="internal_event_delivery_failed.*worker log unavailable",
    ):
        state.start_background_memory_curator()
        state.stop_background_memory_curator()

    assert calls == 2
    health = next(
        item for item in state.worker_health() if item.name == "memory_curator"
    )
    assert health.alive is False
    assert health.consecutive_failures == 0
    assert health.last_success_at is not None


def test_worker_iterations_have_isolated_job_contexts(
    tmp_path: Path,
) -> None:
    supervisor = _worker_supervisor(tmp_path)
    supervisor.register(
        "memory_curator",
        thread_name="test-memory-curator",
        target=lambda: None,
    )
    supervisor.seal()
    observed: list[RuntimeContext] = []

    def first_operation() -> None:
        observed.append(current_runtime_context())
        with runtime_context(thread_id="tick-thread"):
            observed.append(current_runtime_context())

    def second_operation() -> None:
        observed.append(current_runtime_context())

    with runtime_context(
        request_id="ambient-request",
        thread_id="ambient-thread",
        trace_id="ambient-trace",
        source="test",
    ):
        assert supervisor.run_iteration(
            "memory_curator",
            first_operation,
            error_event="memory_curator_error",
            error_message="memory curator iteration failed",
        )
        assert supervisor.run_iteration(
            "memory_curator",
            second_operation,
            error_event="memory_curator_error",
            error_message="memory curator iteration failed",
        )
        assert current_runtime_context() == RuntimeContext(
            request_id="ambient-request",
            thread_id="ambient-thread",
            trace_id="ambient-trace",
            source="test",
        )

    first, nested, second = observed
    assert first.source == "daemon.worker.memory_curator"
    assert first.job_id is not None
    assert first.request_id is None
    assert first.thread_id is None
    assert first.trace_id is None
    assert nested.job_id == first.job_id
    assert nested.thread_id == "tick-thread"
    assert second.source == "daemon.worker.memory_curator"
    assert second.job_id is not None
    assert second.job_id != first.job_id
    assert second.thread_id is None


def test_worker_failure_log_uses_iteration_job_context(
    tmp_path: Path,
) -> None:
    supervisor = _worker_supervisor(tmp_path)
    supervisor.register(
        "reflection_scheduler",
        thread_name="test-reflection-scheduler",
        target=lambda: None,
    )
    supervisor.seal()
    observed: list[RuntimeContext] = []

    def fail() -> None:
        observed.append(current_runtime_context())
        raise ValueError("tick failed")

    assert not supervisor.run_iteration(
        "reflection_scheduler",
        fail,
        error_event="reflection_scheduler_error",
        error_message="reflection scheduler iteration failed",
    )

    event = next(
        item
        for item in read_log_events(
            project_root=tmp_path,
            component="daemon",
        )
        if item.event == "worker.failed"
    )
    assert observed[0].job_id is not None
    assert event.job_id == observed[0].job_id
    assert event.source == "daemon.worker.reflection_scheduler"
    assert event.metadata == {
        "worker": "reflection_scheduler",
        "operation_event": "reflection_scheduler_error",
        "error_type": "ValueError",
    }
    assert current_runtime_context() == RuntimeContext()


def test_export_worker_initialization_fails_before_thread_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nuself.daemon import reason_export

    state = DaemonState(tmp_path)

    def fail_store(*args: object, **kwargs: object) -> object:
        raise OSError("workspace unavailable")

    monkeypatch.setattr(
        reason_export,
        "PrivateWorkspaceStore",
        fail_store,
    )

    with pytest.raises(OSError, match="workspace unavailable"):
        state.start_background_export_worker()

    health = next(
        item
        for item in state.worker_health()
        if item.name == "export_worker"
    )
    assert health.alive is False
    assert health.last_success_at is None
    assert health.last_error is None


def test_daemon_worker_join_timeout_is_logged_and_remains_live(
    tmp_path: Path,
) -> None:
    shutdown_requested = threading.Event()
    supervisor = _worker_supervisor(tmp_path, shutdown_requested)
    release = threading.Event()

    def wait_for_release() -> None:
        release.wait()

    supervisor.register(
        "memory_curator",
        thread_name="test-memory-curator",
        target=wait_for_release,
    )
    supervisor.seal()
    supervisor.start("memory_curator")
    with pytest.raises(
        DaemonWorkerJoinTimeoutError,
        match="memory_curator did not stop",
    ):
        supervisor.join(
            "memory_curator",
            timeout=0,
        )

    health = next(
        item for item in supervisor.health() if item.name == "memory_curator"
    )
    assert health.alive is True
    [event] = [
        item
        for item in read_log_events(
            project_root=tmp_path,
            component="daemon",
        )
        if item.event == "thread_timeout"
    ]
    assert event.event == "thread_timeout"
    assert event.status == "timed_out"
    assert event.metadata == {
        "worker": "memory_curator",
        "timeout_seconds": 0,
    }

    release.set()
    supervisor.join(
        "memory_curator",
        timeout=1,
    )
    health = next(
        item for item in supervisor.health() if item.name == "memory_curator"
    )
    assert health.alive is False


def test_daemon_echo_returns_payload(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    request = DaemonRequest(type="echo", payload={"test": "data"}, request_id="echo1")

    response = handle_request(request, state)

    assert response.status == "ok"
    assert response.payload["test"] == "data"


def test_daemon_shutdown_sets_flag(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    request = DaemonRequest(type="shutdown", payload={}, request_id="shutdown1")

    response = handle_request(request, state)

    assert response.status == "ok"
    assert response.payload["message"] == "shutdown requested"
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
    assert response.payload["message"] == "shutdown requested"
    assert state.shutdown_requested.is_set()


def test_daemon_unsupported_type_returns_error(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    request = DaemonRequest(type="unknown", payload={}, request_id="unknown1")  # type: ignore[arg-type]

    response = handle_request(request, state)

    assert response.status == "error"
    assert response.error is not None
    assert "unsupported request type" in response.error


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
    fake = SimpleNamespace(
        connection=FakeConnection(raw),
        rfile=io.BytesIO(raw),
        wfile=io.BytesIO(),
        _daemon_state=lambda: SimpleNamespace(project_root=tmp_path),
        _request_project_root=lambda: tmp_path,
    )

    def boom(request: DaemonRequest, state: object) -> DaemonResponse:
        raise ValueError("kaboom")

    monkeypatch.setattr(server_mod, "handle_request", boom)

    server_mod.RequestHandler.handle(fake)  # type: ignore[arg-type]

    response = DaemonResponse.from_json_line(fake.wfile.getvalue())
    assert response.status == "error"
    assert response.error is not None
    assert "kaboom" in response.error


def test_daemon_background_reflection_scheduler_creates_outbox_entry(tmp_path: Path) -> None:
    """End-to-end: daemon starts reflection scheduler thread, which reflects and creates an outbox entry."""
    state = DaemonState(tmp_path)
    state.reflection_check_interval_seconds = 0.05
    reflected = threading.Event()

    class MockScheduler:
        def should_reflect(self, now: object = None) -> bool:
            return True

        def reflect(self, now: object = None) -> bool:
            outbox = NotificationOutbox(tmp_path)
            outbox.add(
                OutboxEntry(
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
    state.start_background_reflection_scheduler()
    try:
        assert reflected.wait(timeout=1)
    finally:
        state.shutdown_requested.set()
        state.stop_background_reflection_scheduler()

    outbox = NotificationOutbox(tmp_path)
    entries = outbox.list()
    assert len(entries) >= 1
    assert any(e.title == "test reflection idea" for e in entries)
