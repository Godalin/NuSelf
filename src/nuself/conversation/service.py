"""Conversation execution and management service boundary."""

from __future__ import annotations

from collections.abc import Callable

from nuself.conversation.model import ConversationState
from nuself.conversation.store import ConversationStore


class ConversationService:
    """Coordinate persistent conversation use cases over one store."""

    def __init__(self, store: ConversationStore) -> None:
        self._store = store

    def load(self, conversation_id: str) -> ConversationState:
        return self._store.load(conversation_id)

    def save(self, state: ConversationState) -> None:
        self._store.save(state)

    def update[UpdateResult](
        self,
        conversation_id: str,
        update: Callable[
            [ConversationState],
            tuple[ConversationState, UpdateResult],
        ],
        *,
        turn_id: str | None = None,
        user_message: str | None = None,
        resume_pending_turn: bool = False,
        commit_observer: Callable[[int], None] | None = None,
    ) -> UpdateResult:
        return self._store.update(
            conversation_id,
            update,
            turn_id=turn_id,
            user_message=user_message,
            resume_pending_turn=resume_pending_turn,
            commit_observer=commit_observer,
        )

    def list(self) -> list[str]:
        return self._store.list()

    def list_archived(self) -> list[str]:
        return self._store.list_archived()

    def rename(self, old_conversation_id: str, new_conversation_id: str) -> None:
        self._store.rename(old_conversation_id, new_conversation_id)

    def branch(
        self,
        source_conversation_id: str,
        new_conversation_id: str,
        message_index: int | None = None,
    ) -> ConversationState:
        return self._store.branch(
            source_conversation_id,
            new_conversation_id,
            message_index,
        )

    def archive(self, conversation_id: str) -> None:
        self._store.archive(conversation_id)

    def unarchive(self, conversation_id: str) -> None:
        self._store.unarchive(conversation_id)

    def delete(self, conversation_id: str) -> None:
        self._store.delete(conversation_id)
