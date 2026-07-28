from pathlib import Path

import pytest

from nuself.cli.commands.memory.common import record_memory_trace
from nuself.decorators.audit import audit_log
from nuself.logs import read_log_events
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


def test_audit_failure_is_observed_without_failing_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    structured_failures: list[tuple[str, str | None]] = []

    def fail_audit(*args: object, **kwargs: object) -> None:
        raise OSError("audit store unavailable")

    def capture_failure(
        component: str,
        event: str,
        message: str,
        **kwargs: object,
    ) -> None:
        structured_failures.append((event, kwargs.get("error")))  # type: ignore[arg-type]

    monkeypatch.setattr("nuself.decorators.audit.write_log_event", fail_audit)
    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        capture_failure,
    )

    @audit_log("chat")
    def tool() -> str:
        return "ok"

    assert tool() == "ok"
    assert structured_failures == [
        ("audit_log_failed", "audit store unavailable"),
    ]
