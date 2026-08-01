"""One-way projections from interaction state into knowledge-domain inputs."""

from __future__ import annotations

from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from nuself.conversation import CompletedTurn
from nuself.memory.observation import MemoryObservation


class MemoryObserver(Protocol):
    def observe(self, observation: MemoryObservation) -> MemoryObservation: ...


def publish_chat_observation(
    observer: MemoryObserver,
    *,
    turn: CompletedTurn,
    source_trace_id: str | None = None,
) -> MemoryObservation:
    """Project one committed turn into memory's producer-neutral API."""

    source_identity = (
        f"{turn.conversation_id}:{turn.start_index}:{turn.end_index}"
    )
    source_ref = f"interaction:{uuid5(NAMESPACE_URL, source_identity).hex}"
    return observer.observe(
        MemoryObservation.create(
            source_ref=source_ref,
            fragments=(
                f"user: {turn.user_content}",
                f"assistant: {turn.assistant_content}",
            ),
            source_trace_id=source_trace_id,
        )
    )
