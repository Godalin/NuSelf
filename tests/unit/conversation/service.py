"""Conversation service artifact-resolution tests."""

from __future__ import annotations

from pathlib import Path

from nuself.config.settings import runtime_paths
from nuself.conversation import (
    ConversationMessage,
    ConversationService,
    ConversationState,
    ConversationStore,
)
from tests.backend import owned_backend


def test_resolve_turn_returns_the_persisted_message_pair(tmp_path: Path) -> None:
    paths = runtime_paths(tmp_path)
    store = ConversationStore(paths, backend=owned_backend(tmp_path))
    store.save(
        ConversationState(
            conversation_id="discussion",
            messages=[
                ConversationMessage("user", "Remember this", "turn-1"),
                ConversationMessage("assistant", "I will", "turn-1"),
            ],
            message_start_index=4,
            next_message_index=6,
        )
    )

    turn = ConversationService(store).resolve_turn(
        "conversation_turn:turn-1"
    )

    assert turn is not None
    assert turn.artifact_ref == "conversation_turn:turn-1"
    assert turn.conversation_id == "discussion"
    assert turn.start_index == 4
    assert turn.end_index == 6
    assert turn.user_content == "Remember this"
    assert turn.assistant_content == "I will"


def test_resolve_turn_rejects_unknown_or_foreign_refs(tmp_path: Path) -> None:
    paths = runtime_paths(tmp_path)
    service = ConversationService(
        ConversationStore(paths, backend=owned_backend(tmp_path))
    )

    assert service.resolve_turn("memory:mem-1") is None
    assert service.resolve_turn("conversation_turn:missing") is None
    assert service.resolve_turn("conversation_range:invalid%2Fid:0:2") is None


def test_resolve_turn_supports_an_encoded_message_range(tmp_path: Path) -> None:
    paths = runtime_paths(tmp_path)
    store = ConversationStore(paths, backend=owned_backend(tmp_path))
    store.save(
        ConversationState(
            conversation_id="nested:discussion",
            messages=[
                ConversationMessage("user", "Range question"),
                ConversationMessage("assistant", "Range answer"),
            ],
            message_start_index=8,
            next_message_index=10,
        )
    )
    service = ConversationService(store)

    turn = service.resolve_turn("conversation_range:nested%3Adiscussion:8:10")

    assert turn is not None
    assert turn.user_content == "Range question"
    assert turn.assistant_content == "Range answer"
    assert turn.artifact_ref == "conversation_range:nested%3Adiscussion:8:10"
