"""One-way projections from interaction state into knowledge-domain inputs."""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from nuself.agent.chat import ChatResult
from nuself.application.composition import ApplicationGraph
from nuself.memory.observation import MemoryObservation


def publish_chat_observation(
    application: ApplicationGraph,
    *,
    result: ChatResult,
    user_message: str,
    turn_id: str | None = None,
) -> MemoryObservation:
    """Publish the last committed turn without exposing conversation to memory."""

    state = application.conversations.load(result.conversation_id)
    if len(state.messages) >= 2:
        persisted_user, persisted_assistant = state.messages[-2:]
        if persisted_user.role != "user" or persisted_assistant.role != "assistant":
            raise ValueError("completed chat result does not end in a complete turn")
        start_index = state.next_message_index - 2
        source_identity = (
            f"{result.conversation_id}:{start_index}:{state.next_message_index}"
        )
        fragments = (
            f"user: {persisted_user.content}",
            f"assistant: {persisted_assistant.content}",
        )
    else:
        source_identity = (
            f"{result.conversation_id}:{turn_id or ''}:{user_message}:{result.reply}"
        )
        fragments = (
            f"user: {user_message}",
            f"assistant: {result.reply}",
        )
    source_ref = f"interaction:{uuid5(NAMESPACE_URL, source_identity).hex}"
    return application.memory.observations.observe(
        MemoryObservation.create(
            source_ref=source_ref,
            fragments=fragments,
            source_trace_id=result.trace_id,
        )
    )
