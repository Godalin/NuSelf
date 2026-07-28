from pathlib import Path
from typing import Any

import pytest

import nuself.runtime.observability as observability
from nuself.agent.chat.persona import ConversationPersonaOrchestrator
from nuself.cli.commands.memory.common import record_memory_trace
from nuself.cli.commands.persona import _record_lifecycle  # pyright: ignore[reportPrivateUsage]
from nuself.decorators.audit import audit_log
from nuself.logs import read_log_events
from nuself.persona import PersonaInput, PersonaTurnState
from nuself.persona.prompt_repo import PersonaPrompt
from nuself.persona.tools import _record_prompt_trace  # pyright: ignore[reportPrivateUsage]


class _Memory:
    id = "m1"
    title = "Memory"
    body = "Body"
    type = "concept"
    confidence = 0.8


def test_memory_trace_failure_is_observed_without_failing_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("trace store unavailable")

    monkeypatch.setattr(
        "nuself.cli.commands.memory.common.TraceRecorder.record_memory_update",
        fail,
    )

    record_memory_trace(tmp_path, _Memory(), "add")

    event = read_log_events(project_root=tmp_path, component="memory")[-1]
    assert event.event == "trace_recording_failed"
    assert event.error == "trace store unavailable"
    assert event.metadata == {"memory_id": "m1", "action": "add"}


def test_persona_trace_failure_is_observed_without_failing_tool(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("trace store unavailable")

    monkeypatch.setattr(
        "nuself.trace.service.TraceRecorder.record_persona_prompt_created",
        fail,
    )
    prompt = PersonaPrompt(
        id="persona_1",
        name="Reviewer",
        prompt="Review carefully.",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )

    _record_prompt_trace(prompt, project_root=tmp_path)

    event = read_log_events(project_root=tmp_path, component="persona")[-1]
    assert event.event == "trace_recording_failed"
    assert event.error == "trace store unavailable"
    assert event.metadata == {
        "persona_prompt_id": "persona_1",
        "action": "create",
    }


def test_cli_persona_trace_failure_is_observed_after_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("trace store unavailable")

    monkeypatch.setattr(
        "nuself.trace.service.TraceRecorder.record_persona_prompt_created",
        fail,
    )
    prompt = PersonaPrompt(
        id="persona_cli",
        name="Reviewer",
        prompt="Review carefully.",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )

    _record_lifecycle(
        tmp_path,
        action="prompt_created",
        persona=prompt,
    )

    event = read_log_events(project_root=tmp_path, component="persona")[-1]
    assert event.event == "trace_recording_failed"
    assert event.error == "trace store unavailable"
    assert event.metadata == {
        "persona_prompt_id": "persona_cli",
        "action": "prompt_created",
    }


def test_cli_persona_unknown_trace_action_propagates(
    tmp_path: Path,
) -> None:
    prompt = PersonaPrompt(
        id="persona_cli",
        name="Reviewer",
        prompt="Review carefully.",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )

    with pytest.raises(AttributeError):
        _record_lifecycle(
            tmp_path,
            action="unknown",
            persona=prompt,
        )


def test_audit_failure_is_observed_without_failing_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    structured_failures: list[tuple[str, str | None]] = []

    def fail_audit_or_capture_failure(
        component: str,
        event: str,
        message: str,
        **kwargs: object,
    ) -> None:
        if event != "audit_log_failed":
            raise OSError("audit store unavailable")
        structured_failures.append((event, kwargs.get("error")))  # type: ignore[arg-type]

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_audit_or_capture_failure,
    )

    @audit_log("chat")
    def tool() -> str:
        return "ok"

    assert tool() == "ok"
    assert structured_failures == [
        ("audit_log_failed", "audit store unavailable"),
    ]


def test_persona_failure_log_cannot_mask_discussion_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FailingDiscussion:
        def discuss(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("discussion unavailable")

    write_log_event = observability.write_log_event

    def fail_audit(*args: Any, **kwargs: Any) -> object:
        event = args[1]
        if event == "persona_discussion_failure":
            raise OSError("audit store unavailable")
        return write_log_event(*args, **kwargs)

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_audit,
    )
    orchestrator = ConversationPersonaOrchestrator.__new__(
        ConversationPersonaOrchestrator
    )
    orchestrator._project_root = tmp_path  # pyright: ignore[reportPrivateUsage]
    orchestrator._discussion_service = FailingDiscussion()  # pyright: ignore[reportPrivateUsage, reportAttributeAccessIssue]
    turn_state = PersonaTurnState(
        input=PersonaInput(user_message="compare"),
        selected_personas=(),
    )

    with pytest.warns(
        RuntimeWarning,
        match="persona/persona_discussion_failure",
    ):
        result = orchestrator._run_discussion(  # pyright: ignore[reportPrivateUsage]
            topic="compare",
            thread_id="thread-1",
            trigger="requested",
            turn_state=turn_state,
            should_escalate=True,
        )

    assert result == "\nDiscussion failed: discussion unavailable"
    assert read_log_events(
        project_root=tmp_path,
        component="persona",
    ) == []


@pytest.mark.parametrize(
    "error",
    [
        AssertionError("broken discussion invariant"),
        AttributeError("missing discussion dependency"),
        KeyError("missing discussion registry entry"),
        TypeError("invalid internal discussion call"),
    ],
    ids=["assertion", "attribute", "lookup", "type"],
)
def test_persona_discussion_implementation_errors_propagate(
    tmp_path: Path,
    error: Exception,
) -> None:
    class FailingDiscussion:
        def discuss(self, *args: object, **kwargs: object) -> None:
            del args, kwargs
            raise error

    orchestrator = ConversationPersonaOrchestrator.__new__(
        ConversationPersonaOrchestrator
    )
    orchestrator._project_root = tmp_path  # pyright: ignore[reportPrivateUsage]
    orchestrator._discussion_service = FailingDiscussion()  # pyright: ignore[reportPrivateUsage, reportAttributeAccessIssue]
    turn_state = PersonaTurnState(
        input=PersonaInput(user_message="compare"),
        selected_personas=(),
    )

    with pytest.raises(type(error)) as caught:
        orchestrator._run_discussion(  # pyright: ignore[reportPrivateUsage]
            topic="compare",
            thread_id="thread-1",
            trigger="requested",
            turn_state=turn_state,
            should_escalate=True,
        )

    assert caught.value is error
    assert read_log_events(
        project_root=tmp_path,
        component="persona",
    ) == []
