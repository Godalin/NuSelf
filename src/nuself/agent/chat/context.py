"""Conversation context preparation collaborator."""

from __future__ import annotations

from dataclasses import replace

from nuself.agent.chat.types import (
    ConversationNodeResult,
    ConversationTurnState,
)
from nuself.conversation import ConversationMessage
from nuself.memory.query import MemoryQuery, MemoryQueryService


class ConversationContextPreparer:
    def __init__(
        self, memory_query_service: MemoryQueryService
    ) -> None:
        self._memory_query_service = memory_query_service

    def prepare(
        self, state: ConversationTurnState
    ) -> ConversationNodeResult:
        base_messages = tuple(
            _messages_for_prompt_context(
                state.persisted_state.messages
            )
        )
        active_messages = (
            *base_messages,
            ConversationMessage(
                role="user",
                content=state.user_message,
                turn_id=state.turn_id,
            ),
        )
        packed_memory = self._memory_query_service.pack(
            MemoryQuery(text=state.user_message)
        )
        return ConversationNodeResult(
            state=replace(
                state,
                base_messages=base_messages,
                active_messages=active_messages,
                memory_context=packed_memory.text,
                recent_message_count=len(base_messages),
                memory_match_count=len(packed_memory.matches),
                profile_match_count=len(packed_memory.profile_matches),
                source_match_count=len(packed_memory.source_matches),
                node_trace=(
                    *state.node_trace,
                    "prepare_context",
                ),
            )
        )


def _messages_for_prompt_context(
    messages: list[ConversationMessage],
) -> list[ConversationMessage]:
    return [
        message
        for message in messages
        if not (
            message.role == "assistant"
            and message.content.startswith(
                "LLM API is not configured yet."
            )
        )
    ]
