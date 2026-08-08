"""Tests for reason service."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Never

import pytest
from langchain_core.messages import BaseMessage
from pydantic import ValidationError

from nuself.trace.composition import compose_trace_services
from nuself.config.settings import runtime_paths
from nuself.log.reader import read_log_events
from nuself.reason.model import ReasoningStep, ReasoningThread
from nuself.reason.errors import (
    ReasonAdvanceError,
    ReasonOperationConflict,
    ReasonPromptError,
    ReasonTransitionError,
)
from nuself.reason.repository import ReasonRepository
from reason_fixtures import ReasonService
from tests.backend import owned_backend
from inbox_fixtures import inbox_service


def _reason_service(**kwargs: Any) -> ReasonService:
    return ReasonService(prompt_generator=_test_prompt_generator, **kwargs)


def _test_prompt_generator(*args: object, **kwargs: object) -> str:
    return "Test-generated reasoning prompt."


def test_start_thread_rejects_empty_prompt_with_domain_error(
    tmp_path: Path,
) -> None:
    service = ReasonService(
        tmp_path,
        prompt_generator=lambda *args, **kwargs: "",
    )

    with pytest.raises(
        ReasonPromptError,
        match="prompt generation returned empty output",
    ):
        service.start_thread("Empty prompt")


def test_prompt_generation_requires_project_root_with_domain_error() -> None:
    from nuself.reason.prompt import generate_reasoning_prompt

    with pytest.raises(
        ReasonPromptError,
        match="project root is not configured",
    ):
        generate_reasoning_prompt("Missing project")


def test_prompt_generation_uses_shared_no_model_error(
    tmp_path: Path,
) -> None:
    from nuself.reason.prompt import generate_reasoning_prompt

    with pytest.raises(
        ReasonPromptError,
        match="no configured LangChain model",
    ) as caught:
        generate_reasoning_prompt(
            "Missing model",
            project_root=tmp_path,
        )

    assert isinstance(caught.value.__cause__, RuntimeError)
    assert str(caught.value.__cause__) == (
        "no configured LangChain model"
    )


def test_prompt_generation_wraps_declared_llm_runtime_failure(
    tmp_path: Path,
) -> None:
    from nuself.reason.prompt import (
        ReasonPromptOutput,
        generate_reasoning_prompt,
    )

    provider_error = RuntimeError("provider unavailable")

    class FailingAgent:
        def invoke(
            self,
            messages: object,
        ) -> ReasonPromptOutput:
            del messages
            raise provider_error

    with pytest.raises(ReasonPromptError) as caught:
        generate_reasoning_prompt(
            "Provider failure",
            project_root=tmp_path,
            agent=FailingAgent(),
        )

    assert caught.value.__cause__ is provider_error


def test_prompt_generation_preserves_unexpected_llm_implementation_error(
    tmp_path: Path,
) -> None:
    from nuself.reason.prompt import generate_reasoning_prompt

    unexpected = TypeError("LLM adapter implementation failed")

    class BrokenAgent:
        def invoke(self, messages: object) -> Never:
            del messages
            raise unexpected

    with pytest.raises(TypeError) as caught:
        generate_reasoning_prompt(
            "Broken adapter",
            project_root=tmp_path,
            agent=BrokenAgent(),
        )

    assert caught.value is unexpected


def test_start_thread_preserves_unexpected_prompt_generator_error(
    tmp_path: Path,
) -> None:
    unexpected = RuntimeError("prompt implementation failed")

    def fail_prompt(*args: object, **kwargs: object) -> str:
        raise unexpected

    service = ReasonService(tmp_path, prompt_generator=fail_prompt)

    with pytest.raises(RuntimeError) as caught:
        service.start_thread("Unexpected failure")

    assert caught.value is unexpected


def test_start_thread_passes_only_reason_inputs_to_prompt_generator(
    tmp_path: Path,
) -> None:
    seen_kwargs: dict[str, object] = {}

    def prompt_generator(*args: object, **kwargs: object) -> str:
        del args
        seen_kwargs.update(kwargs)
        return "Generated prompt."

    service = ReasonService(tmp_path, prompt_generator=prompt_generator)

    service.start_thread("Prompt root")

    assert seen_kwargs == {"mandates": (), "active_items": ()}


def test_generated_prompt_request_defines_bounded_round_pacing(
    tmp_path: Path,
) -> None:
    from nuself.reason.prompt import (
        ReasonPromptOutput,
        generate_reasoning_prompt,
    )

    captured_prompt: dict[str, str] = {}

    class FakeAgent:
        def invoke(
            self,
            messages: Sequence[BaseMessage],
        ) -> ReasonPromptOutput:
            captured_prompt["value"] = messages[1].text
            return ReasonPromptOutput(prompt="Generated prompt.")

    result = generate_reasoning_prompt(
        "Round-based debate",
        project_root=tmp_path,
        agent=FakeAgent(),
    )

    assert result == "Generated prompt."
    assert "one step must mean at" in captured_prompt["value"]
    assert "most one complete round" in captured_prompt["value"]
    assert "must not skip ahead through multiple rounds" in captured_prompt["value"]
    assert "every later persona utterance" in captured_prompt["value"]
    assert "calling persona_think for that persona" in captured_prompt["value"]
    assert "must not simulate local persona speech directly" in captured_prompt["value"]
    assert "terminal_status=continue" in captured_prompt["value"]
    assert "suggest_resolved" in captured_prompt["value"]
    assert "suggest_paused" in captured_prompt["value"]


@pytest.mark.parametrize(
    "payload",
    [
        {"prompt": ""},
        {"prompt": "   "},
        {"prompt": 3},
        {"prompt": "valid", "extra": True},
    ],
)
def test_reason_prompt_output_is_exact(
    payload: dict[str, object],
) -> None:
    from nuself.reason.prompt import ReasonPromptOutput

    with pytest.raises(ValidationError):
        ReasonPromptOutput.model_validate(payload)


def test_start_thread(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)
    thread = service.start_thread("What should I do?")
    assert thread.topic == "What should I do?"
    assert thread.status == "active"


def test_start_thread_once_replays_original_thread(tmp_path: Path) -> None:
    prompt_calls = 0

    def prompt(*args: object, **kwargs: object) -> str:
        nonlocal prompt_calls
        del args, kwargs
        prompt_calls += 1
        return "Stable prompt."

    service = ReasonService(tmp_path, prompt_generator=prompt)

    first = service.start_thread_once(
        "proposal-1",
        "What should I do?",
        working_summary="Keep this stable.",
    )
    replay = service.start_thread_once(
        "proposal-1",
        "What should I do?",
        working_summary="Keep this stable.",
    )

    assert replay == first
    assert prompt_calls == 1
    assert service.list_threads() == [first]
    traces = compose_trace_services(
        runtime_paths(tmp_path),
        owned_backend(tmp_path),
    ).query.list_traces(kind="reason_thread")
    assert len(traces) == 1


def test_start_thread_once_rejects_conflicting_reuse(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)
    service.start_thread_once("proposal-1", "First topic")

    with pytest.raises(ReasonOperationConflict, match="proposal-1"):
        service.start_thread_once("proposal-1", "Different topic")

    assert [thread.topic for thread in service.list_threads()] == [
        "First topic"
    ]


def test_start_thread_once_rolls_back_thread_when_receipt_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nuself.storage.sqlite import SqliteCollection

    original_put = SqliteCollection.put

    def fail_operation_put(
        collection: SqliteCollection,
        key: str,
        value: dict[str, object],
    ) -> None:
        if collection._collection_name == "reason_operations":  # pyright: ignore[reportPrivateUsage]
            raise OSError("operation receipt unavailable")
        original_put(collection, key, value)

    monkeypatch.setattr(SqliteCollection, "put", fail_operation_put)
    service = _reason_service(project_root=tmp_path)

    with pytest.raises(OSError, match="operation receipt unavailable"):
        service.start_thread_once("proposal-1", "Atomic topic")

    assert service.list_threads() == []


def test_start_thread_writes_logs_under_project_root(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)

    thread = service.start_thread("Where should reason logs live?")

    events = read_log_events(project_root=tmp_path, component="reasoning")
    assert events
    assert events[-1].event == "thread_started"
    assert events[-1].message == "Reason thread started"
    assert events[-1].metadata == {"thread_id": thread.id}
    assert thread.topic not in str(events[-1].to_record())
    assert (tmp_path / "logs" / "reasoning.log").is_file()


def test_start_and_list(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)
    service.start_thread("Question 1")
    service.start_thread("Question 2")
    threads = service.list_threads()
    assert len(threads) == 2


def test_start_with_evidence(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)
    thread = service.start_thread("Test", evidence_refs=("ref-1", "ref-2"))
    assert thread.evidence_refs == ("ref-1", "ref-2")


def test_start_thread_records_trace(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)

    thread = service.start_thread("What should be traced?", evidence_refs=("memory:abc",))

    traces = compose_trace_services(
        runtime_paths(tmp_path),
        owned_backend(tmp_path),
    ).query.list_traces(kind="reason_thread")
    assert len(traces) == 1
    assert traces[0].outputs == (f"reason:{thread.id}",)
    assert traces[0].evidence_refs == ()


def test_start_thread_records_trace_when_repository_is_injected(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path, repository=ReasonRepository(runtime_paths(tmp_path), backend=owned_backend(tmp_path)))

    thread = service.start_thread("Injected repository should still trace")

    traces = compose_trace_services(
        runtime_paths(tmp_path),
        owned_backend(tmp_path),
    ).query.list_traces(kind="reason_thread")
    assert len(traces) == 1
    assert traces[0].outputs == (f"reason:{thread.id}",)


def test_start_projections_cannot_replace_persisted_thread(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_trace(*args: object, **kwargs: object) -> None:
        raise OSError("trace store unavailable")

    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("audit store unavailable")

    monkeypatch.setattr(
        "nuself.trace.service.TraceRecorder.record_reason_thread_created",
        fail_trace,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        fail_log,
    )
    service = _reason_service(project_root=tmp_path)

    with pytest.warns(RuntimeWarning) as captured:
        thread = service.start_thread("Persist despite projections")

    assert service.show_thread(thread.id) == thread
    messages = [str(warning.message) for warning in captured]
    assert any(
        "component=reasoning event=trace_recording_failed "
        "observed_error=trace store unavailable"
        in message
        for message in messages
    )
    assert any(
        "component=reasoning event=observability_projection_failed "
        "observed_error=audit store unavailable"
        in message
        for message in messages
    )


def test_show_thread_by_id(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)
    created = service.start_thread("Show me")
    shown = service.show_thread(created.id)
    assert shown.id == created.id


def test_pause_and_resume_thread(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)
    t = service.start_thread("Test")
    paused = service.pause_thread(t.id)
    assert paused.status == "paused"
    resumed = service.resume_thread(t.id)
    assert resumed.status == "active"


def test_transition_audit_failure_cannot_replace_persisted_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _reason_service(project_root=tmp_path)
    thread = service.start_thread("Transition survives audit")

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

    with pytest.warns(
        RuntimeWarning,
        match="runtime/observability_sink_failed",
    ):
        paused = service.pause_thread(thread.id)

    assert paused.status == "paused"
    assert service.show_thread(thread.id).status == "paused"


def test_resolve_thread(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)
    t = service.start_thread("Test")
    resolved = service.resolve_thread(t.id)
    assert resolved.status == "resolved"


def test_archive_thread(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)
    t = service.start_thread("Test")
    archived = service.archive_thread(t.id)
    assert archived.status == "archived"


def test_invalid_transition_raises(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)
    t = service.start_thread("Test")
    service.resolve_thread(t.id)
    with pytest.raises(ReasonTransitionError):
        service.pause_thread(t.id)


def test_advance_thread(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)
    t = service.start_thread("Test advance")
    step = _test_step(t.id)
    advanced = service.advance_thread(t.id, step=step)
    assert advanced.last_advanced_at is not None
    steps = service.list_steps(t.id)
    assert len(steps) == 1
    assert steps[0] == step

    items = inbox_service(tmp_path).list()
    assert [(item.kind, item.source_id) for item in items] == [
        ("reason_step", step.id)
    ]


def test_no_change_step_does_not_enter_inbox(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)
    thread = service.start_thread("No change")
    service.advance_thread(
        thread.id,
        step=ReasoningStep(
            thread_id=thread.id,
            kind="no_change",
            summary="No meaningful change.",
            delta="No new evidence.",
            output="Continue later.",
        ),
    )

    assert inbox_service(tmp_path).list() == []


def test_advance_thread_applies_resolved_terminal_status(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)
    thread = service.start_thread("Resolve after advance")
    step = ReasoningStep(
        thread_id=thread.id,
        summary="Finished",
        delta="Reached terminal condition",
        output="The thread is complete.",
        terminal_status="suggest_resolved",
        terminal_reason="Terminal condition reached.",
    )

    advanced = service.advance_thread(thread.id, step=step)

    assert advanced.status == "resolved"
    assert service.show_thread(thread.id).status == "resolved"
    events = read_log_events(project_root=tmp_path, component="reasoning")
    applied = [event for event in events if event.event == "terminal_recommendation_applied"]
    assert applied
    assert applied[-1].metadata is not None
    assert applied[-1].metadata["terminal_status"] == "suggest_resolved"
    assert applied[-1].metadata["to_status"] == "resolved"
    assert "terminal_reason" not in applied[-1].metadata
    assert step.terminal_reason not in str(applied[-1].to_record())


def test_advance_thread_applies_paused_terminal_status(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)
    thread = service.start_thread("Pause after advance")
    step = ReasoningStep(
        thread_id=thread.id,
        summary="Need input",
        delta="Blocked on user choice",
        output="Which path should continue?",
        terminal_status="suggest_paused",
        terminal_reason="Needs user input.",
    )

    advanced = service.advance_thread(thread.id, step=step)

    assert advanced.status == "paused"
    assert service.show_thread(thread.id).status == "paused"


def test_advance_thread_continues_by_default_even_if_output_mentions_done(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)
    thread = service.start_thread("Do not parse prose")
    step = ReasoningStep(
        thread_id=thread.id,
        summary="Looks complete",
        delta="Text mentions completion",
        output="This looks done, resolved, and should stop.",
    )

    advanced = service.advance_thread(thread.id, step=step)

    assert advanced.status == "active"


def test_advance_thread_records_trace(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)
    thread = service.start_thread("Trace advances")
    step = _test_step(thread.id)

    advanced = service.advance_thread(thread.id, step=step)

    steps = service.list_steps(thread.id)
    traces = compose_trace_services(
        runtime_paths(tmp_path),
        owned_backend(tmp_path),
    ).query.list_traces(kind="reason_step")
    assert len(traces) == 1
    assert traces[0].outputs == (
        f"reason:{advanced.id}",
        f"reason_step:{steps[0].id}",
    )
    assert traces[0].metadata["step_kind"] == "progress"


def test_advance_projects_committed_step_with_recorded_trace(
    tmp_path: Path,
) -> None:
    observed: list[tuple[str, str, str | None]] = []

    def observe_step(
        thread: ReasoningThread,
        step: ReasoningStep,
        trace_id: str | None,
    ) -> None:
        observed.append((thread.id, step.id, trace_id))

    service = _reason_service(
        project_root=tmp_path,
        step_observer=observe_step,
    )
    thread = service.start_thread("Project this step")
    step = _test_step(thread.id)

    service.advance_thread(thread.id, step=step)

    [reason_trace] = compose_trace_services(
        runtime_paths(tmp_path),
        owned_backend(tmp_path),
    ).query.list_traces(kind="reason_step")
    assert observed == [(thread.id, step.id, reason_trace.id)]


def test_advance_projections_cannot_replace_committed_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _reason_service(project_root=tmp_path)
    thread = service.start_thread("Advance survives projections")
    step = _test_step(thread.id)

    def fail_trace(*args: object, **kwargs: object) -> None:
        raise OSError("trace store unavailable")

    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("audit store unavailable")

    monkeypatch.setattr(
        "nuself.trace.service.TraceRecorder.record_reason_step",
        fail_trace,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        fail_log,
    )

    with pytest.warns(RuntimeWarning) as captured:
        advanced = service.advance_thread(thread.id, step=step)

    assert advanced.last_advanced_at is not None
    assert service.show_thread(thread.id) == advanced
    assert service.list_steps(thread.id) == [step]
    messages = [str(warning.message) for warning in captured]
    assert any(
        "component=reasoning event=trace_recording_failed "
        "observed_error=trace store unavailable"
        in message
        for message in messages
    )
    assert any(
        "component=reasoning event=observability_projection_failed "
        "observed_error=audit store unavailable"
        in message
        for message in messages
    )


def test_delete_success_audit_failure_cannot_replace_deletion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _reason_service(project_root=tmp_path)
    thread = service.start_thread("Delete survives audit")

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

    with pytest.warns(
        RuntimeWarning,
        match="runtime/observability_sink_failed",
    ):
        deleted_id = service.delete_thread(thread.id)

    assert deleted_id == thread.id
    assert service.list_threads(status="all") == []


def test_delete_failure_does_not_emit_success_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = ReasonRepository(runtime_paths(tmp_path), backend=owned_backend(tmp_path))
    service = _reason_service(
        project_root=tmp_path,
        repository=repository,
    )
    thread = service.start_thread("Failed delete is not success")

    def fail_delete(thread_id: str) -> None:
        raise OSError("repository delete failed")

    monkeypatch.setattr(repository, "delete_thread", fail_delete)

    with pytest.raises(OSError, match="repository delete failed"):
        service.delete_thread(thread.id)

    events = read_log_events(
        project_root=tmp_path,
        component="reasoning",
    )
    assert not any(
        event.event == "thread_deleted"
        for event in events
    )


def test_reason_step_rejects_non_object_tool_logs() -> None:
    wire = ReasoningStep(
        id="step-test",
        thread_id="reason-test",
        kind="progress",
        summary="Advanced",
        delta="Moved",
        created_at="2026-05-27T00:00:00+00:00",
    ).to_wire()
    wire["tool_logs"] = ["not an object"]

    try:
        ReasoningStep.from_wire(wire)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "tool_logs" in str(exc)


def test_advance_without_advancer_or_step_raises(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)
    thread = service.start_thread("No fallback advance")

    with pytest.raises(
        ReasonAdvanceError,
        match="no reason advancer configured",
    ):
        service.advance_thread(thread.id)


def test_advance_when_advancer_returns_none_raises(tmp_path: Path) -> None:
    class EmptyAdvancer:
        def advance(self, thread: object) -> None:
            return None

    service = _reason_service(project_root=tmp_path)
    thread = service.start_thread("No fake steps")

    with pytest.raises(
        ReasonAdvanceError,
        match="did not produce a structured step",
    ):
        service.advance_thread(thread.id, advancer=EmptyAdvancer())


def test_advance_paused_thread_raises(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)
    t = service.start_thread("Test")
    service.pause_thread(t.id)
    with pytest.raises(ReasonAdvanceError):
        service.advance_thread(t.id)


def _test_step(thread_id: str) -> ReasoningStep:
    return ReasoningStep(
        thread_id=thread_id,
        kind="progress",
        summary="Advanced",
        delta="Moved forward",
        output="Observable output",
    )
