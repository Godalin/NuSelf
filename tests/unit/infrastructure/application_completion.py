"""Post-chat application completion contracts."""

from __future__ import annotations

from pathlib import Path

from nuself.agent.chat.types import ChatResult
from nuself.application.completion import ChatCompletionService
from nuself.conversation import CompletedTurn
from nuself.log.reader import read_log_events
from nuself.memory.observation import MemoryObservation


def _result() -> ChatResult:
    return ChatResult(
        answer="reply",
        conversation_id="default",
        trace_id="trace-1",
        completed_turn=CompletedTurn(
            conversation_id="default",
            start_index=0,
            end_index=2,
            user_content="hello",
            assistant_content="reply",
            turn_id="turn-1",
        ),
    )


def test_completion_returns_durable_observation_identity(
    tmp_path: Path,
) -> None:
    class Observer:
        def observe(
            self,
            observation: MemoryObservation,
        ) -> MemoryObservation:
            return observation

    result = ChatCompletionService(
        Observer(),
        project_root=tmp_path,
    ).complete(_result())

    assert result is not None
    assert result.startswith("obs_")


def test_completion_projection_failure_does_not_replace_reply(
    tmp_path: Path,
) -> None:
    class FailingObserver:
        def observe(
            self,
            observation: MemoryObservation,
        ) -> MemoryObservation:
            del observation
            raise OSError("observation unavailable")

    result = ChatCompletionService(
        FailingObserver(),
        project_root=tmp_path,
    ).complete(_result())

    assert result is None
    event = read_log_events(
        project_root=tmp_path,
        component="memory",
    )[-1]
    assert event.event == "post_chat_observation_failed"
    assert event.status == "degraded"
    assert event.error == "observation unavailable"
