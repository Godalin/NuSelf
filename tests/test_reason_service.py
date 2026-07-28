"""Tests for reason service."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
import sqlite3
from typing import Any, Never

import pytest
from langchain_core.messages import BaseMessage
from pydantic import ValidationError

from nuself.logs import read_log_events
from nuself.reason.domain import ReasoningStep
from nuself.reason.errors import (
    ReasonAdvanceError,
    ReasonPromptError,
    ReasonTransitionError,
)
from nuself.reason.repository import ReasonRepository
from nuself.reason.service import ReasonService
from nuself.trace.service import TraceQueryService


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


def test_start_thread_resolves_project_root_for_prompt_generator(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "AGENTS.md").write_text("# test project\n", encoding="utf-8")
    seen_project_roots: list[Path] = []

    def prompt_generator(*args: object, **kwargs: object) -> str:
        project_root = kwargs.get("project_root")
        if isinstance(project_root, Path):
            seen_project_roots.append(project_root)
        return "Generated prompt."

    service = ReasonService(prompt_generator=prompt_generator)

    service.start_thread("Prompt root")

    assert seen_project_roots == [tmp_path]


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
    service = _reason_service(repository=ReasonRepository(tmp_path))
    thread = service.start_thread("What should I do?")
    assert thread.topic == "What should I do?"
    assert thread.status == "active"


def test_start_thread_writes_logs_under_project_root(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)

    service.start_thread("Where should reason logs live?")

    events = read_log_events(project_root=tmp_path, component="reasoning")
    assert events
    assert events[-1].event == "thread_started"
    assert (tmp_path / "private" / "logs" / "reasoning.log").is_file()


def test_start_thread_initializes_private_workspace(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)

    thread = service.start_thread("Where should scratch state live?")

    workspace = service.workspace_paths(thread.id)
    db_path = tmp_path / "private" / "nuself.sqlite"
    assert workspace.root == tmp_path / "private" / "workspaces" / "reason" / thread.id
    assert workspace.database == db_path
    assert workspace.artifacts.is_dir()
    assert workspace.notes.is_dir()
    # nuself.sqlite is created lazily by SqliteStore on first workspace access
    ws = service.workspace(thread.id)
    ws.put("meta", {"key": "value"})
    assert db_path.is_file()
    conn = sqlite3.connect(str(db_path))
    try:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        assert "workspace_entries" in tables
    finally:
        conn.close()


def test_start_and_list(tmp_path: Path) -> None:
    service = _reason_service(repository=ReasonRepository(tmp_path))
    service.start_thread("Question 1")
    service.start_thread("Question 2")
    threads = service.list_threads()
    assert len(threads) == 2


def test_start_with_evidence(tmp_path: Path) -> None:
    service = _reason_service(repository=ReasonRepository(tmp_path))
    thread = service.start_thread("Test", evidence_refs=("ref-1", "ref-2"))
    assert thread.evidence_refs == ("ref-1", "ref-2")


def test_start_thread_records_trace(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path)

    thread = service.start_thread("What should be traced?", evidence_refs=("memory:abc",))

    traces = TraceQueryService(tmp_path).list_traces(kind="reason_thread")
    assert len(traces) == 1
    assert traces[0].outputs == (f"reason:{thread.id}",)
    assert traces[0].evidence_refs == ()


def test_start_thread_records_trace_when_repository_is_injected(tmp_path: Path) -> None:
    service = _reason_service(project_root=tmp_path, repository=ReasonRepository(tmp_path))

    thread = service.start_thread("Injected repository should still trace")

    traces = TraceQueryService(tmp_path).list_traces(kind="reason_thread")
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
        "nuself.reason.service.write_log_event",
        fail_log,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    service = _reason_service(project_root=tmp_path)

    with pytest.warns(RuntimeWarning) as captured:
        thread = service.start_thread("Persist despite projections")

    assert service.show_thread(thread.id) == thread
    messages = [str(warning.message) for warning in captured]
    assert any(
        "reasoning/trace_recording_failed: trace store unavailable"
        in message
        for message in messages
    )
    assert any(
        "reasoning/reason_audit_write_failed: audit store unavailable"
        in message
        for message in messages
    )


def test_show_thread_by_id(tmp_path: Path) -> None:
    service = _reason_service(repository=ReasonRepository(tmp_path))
    created = service.start_thread("Show me")
    shown = service.show_thread(created.id)
    assert shown.id == created.id


def test_pause_and_resume_thread(tmp_path: Path) -> None:
    service = _reason_service(repository=ReasonRepository(tmp_path))
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
        "nuself.reason.service.write_log_event",
        fail_log,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )

    with pytest.warns(
        RuntimeWarning,
        match="reasoning/reason_audit_write_failed",
    ):
        paused = service.pause_thread(thread.id)

    assert paused.status == "paused"
    assert service.show_thread(thread.id).status == "paused"


def test_resolve_thread(tmp_path: Path) -> None:
    service = _reason_service(repository=ReasonRepository(tmp_path))
    t = service.start_thread("Test")
    resolved = service.resolve_thread(t.id)
    assert resolved.status == "resolved"


def test_archive_thread(tmp_path: Path) -> None:
    service = _reason_service(repository=ReasonRepository(tmp_path))
    t = service.start_thread("Test")
    archived = service.archive_thread(t.id)
    assert archived.status == "archived"


def test_invalid_transition_raises(tmp_path: Path) -> None:
    service = _reason_service(repository=ReasonRepository(tmp_path))
    t = service.start_thread("Test")
    service.resolve_thread(t.id)
    with pytest.raises(ReasonTransitionError):
        service.pause_thread(t.id)


def test_advance_thread(tmp_path: Path) -> None:
    service = _reason_service(repository=ReasonRepository(tmp_path))
    t = service.start_thread("Test advance")
    step = _test_step(t.id)
    advanced = service.advance_thread(t.id, step=step)
    assert advanced.last_advanced_at is not None
    steps = service.list_steps(t.id)
    assert len(steps) == 1
    assert steps[0] == step


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
    traces = TraceQueryService(tmp_path).list_traces(kind="reason_step")
    assert len(traces) == 1
    assert traces[0].outputs == (
        f"reason:{advanced.id}",
        f"reason_step:{steps[0].id}",
    )
    assert traces[0].metadata["step_kind"] == "progress"


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
        "nuself.reason.service.write_log_event",
        fail_log,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )

    with pytest.warns(RuntimeWarning) as captured:
        advanced = service.advance_thread(thread.id, step=step)

    assert advanced.last_advanced_at is not None
    assert service.show_thread(thread.id) == advanced
    assert service.list_steps(thread.id) == [step]
    messages = [str(warning.message) for warning in captured]
    assert any(
        "reasoning/trace_recording_failed: trace store unavailable"
        in message
        for message in messages
    )
    assert any(
        "reasoning/reason_audit_write_failed: audit store unavailable"
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
        "nuself.reason.service.write_log_event",
        fail_log,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )

    with pytest.warns(
        RuntimeWarning,
        match="reasoning/reason_audit_write_failed",
    ):
        deleted_id = service.delete_thread(thread.id)

    assert deleted_id == thread.id
    assert service.list_threads(status="all") == []


def test_delete_failure_does_not_emit_success_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = ReasonRepository(tmp_path)
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
    service = _reason_service(repository=ReasonRepository(tmp_path))
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

    service = _reason_service(repository=ReasonRepository(tmp_path), advancer=EmptyAdvancer())
    thread = service.start_thread("No fake steps")

    with pytest.raises(
        ReasonAdvanceError,
        match="did not produce a structured step",
    ):
        service.advance_thread(thread.id)


def test_advance_paused_thread_raises(tmp_path: Path) -> None:
    service = _reason_service(repository=ReasonRepository(tmp_path))
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
