"""Conversation persistence and serialized mutation."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager, ExitStack, contextmanager
from dataclasses import replace
import time
from typing import Generator

from nuself.config.settings import RuntimePaths
from nuself.conversation.model import (
    ConversationState,
    ConversationTurnConflictError,
    ConversationTurnIncompleteError,
    PendingTurn,
)
from nuself.private_fs import blocking_private_file_lock
from nuself.storage.contract import StorageBackend

class ConversationStore:
    """SQLite-backed conversation store under the selected authority."""

    def __init__(
        self,
        paths: RuntimePaths,
        *,
        backend: StorageBackend,
    ) -> None:
        self._locks_dir = paths.runtime_dir / "conversation-locks"
        self._backend = backend
        self._collection = self._backend.collection("conversations")

    def load(self, conversation_id: str) -> ConversationState:
        self._validate_id(conversation_id)
        raw = self._collection.get(conversation_id)
        if raw is None:
            return ConversationState.empty(conversation_id)
        return ConversationState.from_wire(raw)

    def save(self, state: ConversationState) -> None:
        self._validate_id(state.conversation_id)
        with self._locked(state.conversation_id), self._backend.transaction():
            self._save_unlocked(state)

    def update[UpdateResult](
        self,
        conversation_id: str,
        update: Callable[[ConversationState], tuple[ConversationState, UpdateResult]],
        *,
        turn_id: str | None = None,
        user_message: str | None = None,
        commit_observer: Callable[[int], None] | None = None,
    ) -> UpdateResult:
        """Serialize one turn without holding SQLite across model execution."""

        self._validate_id(conversation_id)
        if (turn_id is None) != (user_message is None):
            raise ValueError(
                "turn_id and user_message must be supplied together"
            )
        with self._locked(conversation_id):
            original = self._collection.get(conversation_id)
            state = (
                ConversationState.empty(conversation_id)
                if original is None
                else ConversationState.from_wire(original)
            )
            if turn_id is not None and not any(
                item.turn_id == turn_id and item.role == "assistant"
                for item in state.messages
            ):
                assert user_message is not None
                state = _begin_turn_attempt(
                    state,
                    turn_id,
                    user_message,
                )
                with self._backend.transaction():
                    self._save_unlocked(state)
                original = self._collection.get(conversation_id)
            updated, result = update(state)
            if updated.conversation_id != conversation_id:
                raise ValueError("conversation update cannot change conversation identity")
            commit_started_at = time.monotonic()
            with self._backend.transaction():
                if self._collection.get(conversation_id) != original:
                    raise ValueError(
                        "conversation changed concurrently; retry the turn"
                    )
                self._save_unlocked(
                    _finish_turn_attempt(updated, turn_id)
                )
            if commit_observer is not None:
                commit_observer(
                    int((time.monotonic() - commit_started_at) * 1000)
                )
            return result

    def _save_unlocked(self, state: ConversationState) -> None:
        self._collection.put(state.conversation_id, state.to_wire())

    def _locked(
        self,
        conversation_id: str,
    ) -> AbstractContextManager[None]:
        self._validate_id(conversation_id)
        return blocking_private_file_lock(
            self._locks_dir / f"{conversation_id}.lock"
        )

    @contextmanager
    def _locked_many(
        self,
        *conversation_ids: str,
    ) -> Generator[None, None, None]:
        with ExitStack() as stack:
            for conversation_id in sorted(set(conversation_ids)):
                stack.enter_context(self._locked(conversation_id))
            yield

    @staticmethod
    def _validate_id(conversation_id: str) -> None:
        if (
            conversation_id == ""
            or "/" in conversation_id
            or "\\" in conversation_id
            or conversation_id in {".", ".."}
        ):
            raise ValueError(f"invalid conversation id: {conversation_id}")

    def list(self) -> list[str]:
        """List persisted conversation IDs, excluding archived conversations."""
        return sorted(
            state.conversation_id
            for state in self._states()
            if not state.archived
        )

    def list_archived(self) -> list[str]:
        """List archived conversation IDs."""
        return sorted(
            state.conversation_id
            for state in self._states()
            if state.archived
        )

    def _states(self) -> tuple[ConversationState, ...]:
        return tuple(
            ConversationState.from_wire(item)
            for item in self._collection.list()
        )

    def rename(self, old_conversation_id: str, new_conversation_id: str) -> None:
        """Rename one latest locked conversation snapshot."""
        if old_conversation_id == new_conversation_id:
            return
        self._validate_id(old_conversation_id)
        self._validate_id(new_conversation_id)
        with self._locked_many(old_conversation_id, new_conversation_id), self._backend.transaction():
            raw = self._collection.get(old_conversation_id)
            if raw is None:
                raise ValueError(f"conversation not found: {old_conversation_id}")
            if self._collection.get(new_conversation_id) is not None:
                raise ValueError(
                    f"conversation already exists: {new_conversation_id}"
                )
            state = ConversationState.from_wire(raw)
            renamed = replace(state, conversation_id=new_conversation_id)
            self._save_unlocked(renamed)
            self._collection.delete(old_conversation_id)

    def branch(
        self,
        source_conversation_id: str,
        new_conversation_id: str,
        message_index: int | None = None,
    ) -> ConversationState:
        """Branch a new conversation from a source up to a message index.

        If message_index is None, branches from the current end.
        """
        self._validate_id(source_conversation_id)
        self._validate_id(new_conversation_id)
        with self._locked_many(source_conversation_id, new_conversation_id), self._backend.transaction():
            source_raw = self._collection.get(source_conversation_id)
            if source_raw is None:
                raise ValueError(
                    f"source conversation not found: {source_conversation_id}"
                )
            if self._collection.get(new_conversation_id) is not None:
                raise ValueError(
                    f"conversation already exists: {new_conversation_id}"
                )
            source = ConversationState.from_wire(source_raw)
            branch_index = (
                len(source.messages)
                if message_index is None
                else message_index
            )
            if (
                branch_index < 0
                or branch_index > len(source.messages)
            ):
                raise ValueError(
                    f"branch index {branch_index} out of range "
                    f"(0..{len(source.messages)})"
                )
            branched = ConversationState(
                conversation_id=new_conversation_id,
                summary=source.summary,
                messages=source.messages[:branch_index],
                message_start_index=source.message_start_index,
                next_message_index=(
                    source.message_start_index + branch_index
                ),
                pending_turns=(),
            )
            self._save_unlocked(branched)
            return branched

    def archive(self, conversation_id: str) -> None:
        """Mark a conversation as archived."""
        self._validate_id(conversation_id)
        with self._locked(conversation_id), self._backend.transaction():
            raw = self._collection.get(conversation_id)
            if raw is None:
                raise ValueError(f"conversation not found: {conversation_id}")
            state = ConversationState.from_wire(raw)
            if state.archived:
                raise ValueError(
                    f"archived conversation already exists: {conversation_id}"
                )
            self._save_unlocked(replace(state, archived=True))

    def unarchive(self, conversation_id: str) -> None:
        """Restore an archived conversation."""
        self._validate_id(conversation_id)
        with self._locked(conversation_id), self._backend.transaction():
            raw = self._collection.get(conversation_id)
            if raw is None:
                raise ValueError(
                    f"archived conversation not found: {conversation_id}"
                )
            state = ConversationState.from_wire(raw)
            if not state.archived:
                raise ValueError(f"conversation already exists: {conversation_id}")
            self._save_unlocked(replace(state, archived=False))

    def delete(self, conversation_id: str) -> None:
        """Permanently delete a conversation."""
        self._validate_id(conversation_id)
        with self._locked(conversation_id), self._backend.transaction():
            if self._collection.get(conversation_id) is None:
                raise ValueError(f"conversation not found: {conversation_id}")
            self._collection.delete(conversation_id)


def _begin_turn_attempt(
    state: ConversationState,
    turn_id: str,
    message: str,
) -> ConversationState:
    attempted = PendingTurn.from_message(turn_id, message)
    for pending in state.pending_turns:
        if pending.turn_id != turn_id:
            continue
        if pending.input_digest != attempted.input_digest:
            raise ConversationTurnConflictError(
                f"turn ID {turn_id!r} is already bound to different input"
            )
        raise ConversationTurnIncompleteError(
            f"turn ID {turn_id!r} has an unfinished prior execution"
        )
    return replace(
        state,
        pending_turns=(*state.pending_turns, attempted),
    )


def _finish_turn_attempt(
    state: ConversationState,
    turn_id: str | None,
) -> ConversationState:
    if turn_id is None:
        return state
    return replace(
        state,
        pending_turns=tuple(
            pending
            for pending in state.pending_turns
            if pending.turn_id != turn_id
        ),
    )
