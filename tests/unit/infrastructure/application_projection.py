"""Cross-domain application projection contracts."""

from __future__ import annotations

from pathlib import Path

from nuself.application.projection import (
    publish_chat_observation,
    publish_reason_observation,
)
from nuself.conversation import CompletedTurn
from nuself.log.reader import read_log_events
from nuself.memory.observation import MemoryObservation
from nuself.reason.model import ReasoningStep, ReasoningThread


def _turn() -> CompletedTurn:
    return CompletedTurn(
        conversation_id="default",
        start_index=0,
        end_index=2,
        user_content="hello",
        assistant_content="reply",
        turn_id="turn-1",
    )


def test_chat_projection_returns_durable_observation(
    tmp_path: Path,
) -> None:
    class Observer:
        def observe(
            self,
            observation: MemoryObservation,
        ) -> MemoryObservation:
            return observation

    result = publish_chat_observation(
        Observer(),
        turn=_turn(),
        source_trace_id="trace-1",
        project_root=tmp_path,
    )

    assert result is not None
    assert result.id.startswith("obs_")


def test_chat_projection_failure_does_not_replace_reply(
    tmp_path: Path,
) -> None:
    class FailingObserver:
        def observe(
            self,
            observation: MemoryObservation,
        ) -> MemoryObservation:
            del observation
            raise OSError("observation unavailable")

    result = publish_chat_observation(
        FailingObserver(),
        turn=_turn(),
        project_root=tmp_path,
    )

    assert result is None
    event = read_log_events(
        project_root=tmp_path,
        component="memory",
    )[-1]
    assert event.event == "post_chat_observation_failed"
    assert event.status == "degraded"
    assert event.error == "observation unavailable"


def test_reason_projection_retains_step_and_trace_references() -> None:
    captured: list[MemoryObservation] = []

    class Observer:
        def observe(self, observation: MemoryObservation) -> MemoryObservation:
            captured.append(observation)
            return observation

    result = publish_reason_observation(
        Observer(),
        thread=ReasoningThread(id="reason-1", topic="A durable question"),
        step=ReasoningStep(
            id="step-1",
            thread_id="reason-1",
            summary="A durable conclusion",
            new_findings_data=({"label": "Finding one"},),
        ),
        source_trace_id="trace-1",
    )

    assert result is not None
    assert result is captured[0]
    assert result.source_ref == "reason_step:step-1"
    assert result.source_trace_id == "trace-1"
    assert "reason finding: Finding one" in result.fragments
