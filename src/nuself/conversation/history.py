"""Bounded read-only Conversation history API."""

from __future__ import annotations

from dataclasses import dataclass

from nuself.conversation.model import ConversationRole
from nuself.conversation.store import ConversationStore


@dataclass(frozen=True)
class ConversationHistoryMessage:
    """Immutable public message view returned by the conversation API."""

    role: ConversationRole
    content: str


@dataclass(frozen=True)
class ConversationHistoryExcerpt:
    """Bounded public history view with no persistence details."""

    id: str
    messages: tuple[ConversationHistoryMessage, ...]


class ConversationHistoryService:
    """Read-only API for domains that explicitly need chat evidence."""

    def __init__(self, store: ConversationStore) -> None:
        self._store = store

    def recent(
        self,
        *,
        limit: int = 5,
        messages_per_conversation: int = 10,
    ) -> tuple[ConversationHistoryExcerpt, ...]:
        if limit < 1 or messages_per_conversation < 1:
            raise ValueError("conversation history limits must be positive")
        excerpts: list[ConversationHistoryExcerpt] = []
        for conversation_id in reversed(self._store.list()[-limit:]):
            state = self._store.load(conversation_id)
            excerpts.append(
                ConversationHistoryExcerpt(
                    id=conversation_id,
                    messages=tuple(
                        ConversationHistoryMessage(message.role, message.content)
                        for message in state.messages[-messages_per_conversation:]
                    ),
                )
            )
        return tuple(excerpts)
