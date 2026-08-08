"""Conversation execution and management service boundary."""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import unquote

from nuself.conversation.model import CompletedTurn, ConversationState
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
        continue_pending_turn: bool = False,
        commit_observer: Callable[[int], None] | None = None,
    ) -> UpdateResult:
        return self._store.update(
            conversation_id,
            update,
            turn_id=turn_id,
            user_message=user_message,
            continue_pending_turn=continue_pending_turn,
            commit_observer=commit_observer,
        )

    def list(self) -> list[str]:
        return self._store.list()

    def list_archived(self) -> list[str]:
        return self._store.list_archived()

    def resolve_turn(self, artifact_ref: str) -> CompletedTurn | None:
        """Resolve a public conversation-turn artifact reference, if retained."""

        turn_prefix = "conversation_turn:"
        range_prefix = "conversation_range:"
        if artifact_ref.startswith(range_prefix):
            encoded = artifact_ref.removeprefix(range_prefix)
            parts = encoded.rsplit(":", 2)
            if len(parts) != 3:
                return None
            conversation_id, start_text, end_text = parts
            try:
                start_index = int(start_text)
                end_index = int(end_text)
            except ValueError:
                return None
            return self._resolve_range(
                unquote(conversation_id),
                start_index=start_index,
                end_index=end_index,
            )
        if not artifact_ref.startswith(turn_prefix):
            return None
        turn_id = artifact_ref.removeprefix(turn_prefix)
        if not turn_id:
            return None
        conversation_ids = dict.fromkeys((*self.list(), *self.list_archived()))
        for conversation_id in conversation_ids:
            state = self.load(conversation_id)
            indexed = [
                (state.message_start_index + index, message)
                for index, message in enumerate(state.messages)
                if message.turn_id == turn_id
            ]
            user = next(
                ((index, message) for index, message in indexed if message.role == "user"),
                None,
            )
            assistant = next(
                (
                    (index, message)
                    for index, message in indexed
                    if message.role == "assistant"
                ),
                None,
            )
            if user is not None and assistant is not None:
                return CompletedTurn(
                    conversation_id=conversation_id,
                    start_index=user[0],
                    end_index=assistant[0] + 1,
                    user_content=user[1].content,
                    assistant_content=assistant[1].content,
                    turn_id=turn_id,
                )
        return None

    def _resolve_range(
        self,
        conversation_id: str,
        *,
        start_index: int,
        end_index: int,
    ) -> CompletedTurn | None:
        if start_index < 0 or end_index != start_index + 2:
            return None
        try:
            state = self.load(conversation_id)
        except ValueError:
            return None
        local_start = start_index - state.message_start_index
        local_end = end_index - state.message_start_index
        if local_start < 0 or local_end > len(state.messages):
            return None
        selected = state.messages[local_start:local_end]
        if len(selected) != 2 or [item.role for item in selected] != [
            "user",
            "assistant",
        ]:
            return None
        return CompletedTurn(
            conversation_id=conversation_id,
            start_index=start_index,
            end_index=end_index,
            user_content=selected[0].content,
            assistant_content=selected[1].content,
            turn_id=selected[0].turn_id,
        )

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
