"""Conversation state persistence and compression collaborator."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from langchain_core.messages import HumanMessage, SystemMessage

from nuself.agent.chat.types import (
    ChatAgentSettings,
    ConversationNodeResult,
    ConversationTurnState,
)
from nuself.conversation import ConversationMessage, ConversationState
from nuself.agent.text import TextAgent


class ConversationStateManager:
    def __init__(
        self,
        *,
        text_agent: TextAgent | None,
        settings: ChatAgentSettings,
        report_compression_fallback: Callable[[Exception], None],
    ) -> None:
        self._text_agent = text_agent
        self._settings = settings
        self._report_compression_fallback = report_compression_fallback

    def update(
        self, state: ConversationTurnState
    ) -> ConversationNodeResult:
        updated = ConversationState(
            conversation_id=state.conversation_id,
            summary=state.persisted_state.summary,
            messages=list(state.saved_messages),
            message_start_index=(
                state.persisted_state.message_start_index
            ),
            next_message_index=(
                state.persisted_state.message_start_index
                + len(state.saved_messages)
            ),
            archived=state.persisted_state.archived,
            pending_turns=state.persisted_state.pending_turns,
        )
        return ConversationNodeResult(
            state=replace(
                state,
                updated_conversation_state=updated,
                node_trace=(*state.node_trace, "state_update"),
            )
        )

    def compress_conversation(
        self, state: ConversationState
    ) -> ConversationState:
        if (
            len(state.messages)
            <= self._settings.summary_trigger_messages
        ):
            return state
        recent = state.messages[
            -self._settings.recent_messages :
        ]
        older = state.messages[
            : -self._settings.recent_messages
        ]
        summary = self._summarize(state.summary, older)
        return ConversationState(
            conversation_id=state.conversation_id,
            summary=summary,
            messages=recent,
            message_start_index=(
                state.next_message_index - len(recent)
            ),
            next_message_index=state.next_message_index,
            archived=state.archived,
            pending_turns=state.pending_turns,
        )

    def _summarize(
        self,
        previous_summary: str,
        messages: list[ConversationMessage],
    ) -> str:
        transcript = "\n".join(
            f"{message.role}: {message.content}"
            for message in messages
        )
        prompt = [
            SystemMessage(
                content=(
                    "Compress a private NuSelf conversation into "
                    "durable context. Preserve user preferences, "
                    "decisions, unresolved questions, and useful "
                    "facts. Do not add new facts."
                ),
            ),
            HumanMessage(
                content=(
                    "Previous summary:\n"
                    f"{previous_summary or '(none)'}\n\n"
                    f"New transcript:\n{transcript}"
                ),
            ),
        ]
        if self._text_agent is None:
            summary = _local_summary(
                previous_summary,
                transcript,
                self._settings.summary_target_chars,
            )
        else:
            try:
                summary = self._text_agent.invoke(prompt)
                if summary.strip() == "":
                    raise ValueError(
                        "compression model returned an empty summary"
                    )
            except Exception as exc:
                self._report_compression_fallback(exc)
                summary = _local_summary(
                    previous_summary,
                    transcript,
                    self._settings.summary_target_chars,
                )
        return summary[: self._settings.summary_target_chars]


def _local_summary(
    previous_summary: str,
    transcript: str,
    target_chars: int,
) -> str:
    combined = "\n\n".join(
        part
        for part in (previous_summary, transcript)
        if part != ""
    )
    if len(combined) <= target_chars:
        return combined
    return combined[-target_chars:]
