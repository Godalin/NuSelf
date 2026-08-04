from __future__ import annotations

from pathlib import Path

from conversation_fixtures import ConversationStore
from nuself.conversation import (
    ConversationHistoryService,
    ConversationMessage,
    ConversationService,
    ConversationState,
)


def test_history_api_returns_bounded_immutable_views(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path)
    store.save(
        ConversationState(
            conversation_id="first",
            messages=[
                ConversationMessage("user", "old"),
                ConversationMessage("assistant", "answer"),
            ],
        )
    )
    store.save(
        ConversationState(
            conversation_id="second",
            messages=[
                ConversationMessage("user", "new"),
                ConversationMessage("assistant", "latest"),
            ],
        )
    )

    excerpts = ConversationHistoryService(ConversationService(store)).recent(
        limit=1,
        messages_per_conversation=1,
    )

    assert len(excerpts) == 1
    assert excerpts[0].id == "second"
    assert [(message.role, message.content) for message in excerpts[0].messages] == [
        ("assistant", "latest")
    ]
