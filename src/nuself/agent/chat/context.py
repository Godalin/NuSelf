"""Conversation context preparation collaborator."""

from __future__ import annotations

from dataclasses import replace

from nuself.agent.chat.types import (
    ConversationNodeResult,
    ConversationTurnState,
)
from nuself.conversation import ConversationMessage


class ConversationContextPreparer:
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
        return ConversationNodeResult(
            state=replace(
                state,
                base_messages=base_messages,
                active_messages=active_messages,
                recent_message_count=len(base_messages),
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
