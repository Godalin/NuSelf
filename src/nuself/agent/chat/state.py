"""Conversation state persistence and compression collaborator."""

from __future__ import annotations

from dataclasses import replace

from langchain_core.messages import HumanMessage, SystemMessage

from nuself.agent.chat.types import (
    ChatAgentSettings,
    ConversationNodeResult,
    ConversationTurnState,
)
from nuself.agent.chat.thread import ThreadMessage, ThreadState
from nuself.agent.text import TextAgent


class ConversationStateManager:
    def __init__(
        self,
        *,
        text_agent: TextAgent | None,
        settings: ChatAgentSettings,
    ) -> None:
        self._text_agent = text_agent
        self._settings = settings

    def update(
        self, state: ConversationTurnState
    ) -> ConversationNodeResult:
        updated = ThreadState(
            thread_id=state.thread_id,
            summary=state.persisted_state.summary,
            messages=list(state.saved_messages),
            message_start_index=(
                state.persisted_state.message_start_index
            ),
            next_message_index=(
                state.persisted_state.next_message_index
                + len(state.saved_messages)
                - len(state.base_messages)
            ),
        )
        return ConversationNodeResult(
            state=replace(
                state,
                updated_thread_state=updated,
                node_trace=(*state.node_trace, "state_update"),
            )
        )

    def compress(
        self, state: ConversationTurnState
    ) -> ConversationNodeResult:
        updated = state.updated_thread_state
        if updated is None:
            raise RuntimeError(
                "conversation runtime thread state is missing"
            )
        return ConversationNodeResult(
            state=replace(
                state,
                updated_thread_state=self.compress_thread(
                    updated
                ),
                node_trace=(*state.node_trace, "compression"),
            )
        )

    def compress_thread(self, state: ThreadState) -> ThreadState:
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
        return ThreadState(
            thread_id=state.thread_id,
            summary=summary,
            messages=recent,
            message_start_index=(
                state.next_message_index - len(recent)
            ),
            next_message_index=state.next_message_index,
        )

    def _summarize(
        self,
        previous_summary: str,
        messages: list[ThreadMessage],
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
        try:
            if self._text_agent is None:
                raise RuntimeError(
                    "no configured compression text agent"
                )
            summary = self._text_agent.invoke(prompt)
        except (RuntimeError, ValueError):
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
