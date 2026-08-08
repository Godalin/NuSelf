"""Application orchestration after one committed Chat turn."""

from __future__ import annotations

from pathlib import Path

from nuself.agent.chat.types import ChatResult
from nuself.application.projection import MemoryObserver, publish_chat_observation
from nuself.memory.audit import MEMORY_AUDIT


class ChatCompletionService:
    """Project committed Chat evidence without replacing its result."""

    def __init__(
        self,
        observer: MemoryObserver,
        *,
        project_root: Path,
    ) -> None:
        self._observer = observer
        self._project_root = project_root

    def complete(self, result: ChatResult) -> str | None:
        """Return a durable observation ID, or ``None`` after degradation."""
        turn = result.require_completed_turn()
        try:
            observation = publish_chat_observation(
                self._observer,
                turn=turn,
                source_trace_id=result.trace_id,
            )
        except Exception as exc:
            MEMORY_AUDIT.failure(
                exc,
                event="post_chat_observation_failed",
                project_root=self._project_root,
            )
            return None
        return observation.id


__all__ = ["ChatCompletionService"]
