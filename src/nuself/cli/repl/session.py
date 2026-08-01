"""State owned by one interactive CLI connection."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from nuself.cli.composition import compose_cli_conversation_store
from nuself.runtime.log_event import LogEvent
from nuself.cli.repl.transcript import (
    is_shareable_transcript_log,
    conversation_messages_from_index,
)


@dataclass(frozen=True)
class InteractiveRetryOffer:
    message: str
    conversation_id: str
    turn_id: str
    request_may_have_completed: bool


def empty_conversation_start_indexes() -> dict[str, int]:
    return {}


def empty_captured_conversation_messages() -> dict[str, list[tuple[int, str, str]]]:
    return {}


def empty_captured_log_events() -> dict[str, list[LogEvent]]:
    return {}


def empty_captured_log_events_by_message() -> dict[str, dict[int, list[LogEvent]]]:
    return {}


@dataclass
class InteractiveSession:
    """State that belongs to one interactive CLI connection."""

    connected_at: datetime
    conversation_start_indexes: dict[str, int] = field(default_factory=empty_conversation_start_indexes)
    captured_messages: dict[str, list[tuple[int, str, str]]] = field(default_factory=empty_captured_conversation_messages)
    captured_next_indexes: dict[str, int] = field(default_factory=empty_conversation_start_indexes)
    captured_log_events: dict[str, list[LogEvent]] = field(default_factory=empty_captured_log_events)
    captured_log_events_by_message: dict[str, dict[int, list[LogEvent]]] = field(
        default_factory=empty_captured_log_events_by_message
    )
    exported_next_indexes: dict[str, int] = field(default_factory=empty_conversation_start_indexes)
    retry_offer: InteractiveRetryOffer | None = None
    retry_requested: bool = False

    def prepare_turn(
        self,
        *,
        message: str,
        conversation_id: str,
        new_turn_id: str,
    ) -> str:
        offer = self.retry_offer
        if (
            self.retry_requested
            and offer is not None
            and offer.message == message
            and offer.conversation_id == conversation_id
        ):
            self.retry_requested = False
            return offer.turn_id
        self.retry_requested = False
        self.retry_offer = None
        return new_turn_id

    def offer_retry(
        self,
        *,
        message: str,
        conversation_id: str,
        turn_id: str,
        request_may_have_completed: bool,
    ) -> None:
        self.retry_offer = InteractiveRetryOffer(
            message=message,
            conversation_id=conversation_id,
            turn_id=turn_id,
            request_may_have_completed=request_may_have_completed,
        )

    def clear_retry(self) -> None:
        self.retry_offer = None
        self.retry_requested = False

    def start_index_for(self, project_root: Path | None, conversation_id: str) -> int:
        if conversation_id not in self.conversation_start_indexes:
            next_index = compose_cli_conversation_store(
                project_root
            ).load(conversation_id).next_message_index
            self.conversation_start_indexes[conversation_id] = next_index
            self.captured_next_indexes[conversation_id] = next_index
        return self.conversation_start_indexes[conversation_id]

    def capture_new_messages(self, project_root: Path | None, conversation_id: str) -> None:
        start_index = self.start_index_for(project_root, conversation_id)
        capture_start = self.captured_next_indexes.get(conversation_id, start_index)
        conversation = compose_cli_conversation_store(project_root).load(conversation_id)
        new_messages = conversation_messages_from_index(conversation, capture_start)
        if not new_messages:
            return
        self.captured_messages.setdefault(conversation_id, []).extend(new_messages)
        self.captured_next_indexes[conversation_id] = new_messages[-1][0] + 1

    def transcript_messages(self, project_root: Path | None, conversation_id: str) -> list[tuple[int, str, str]]:
        self.capture_new_messages(project_root, conversation_id)
        return list(self.captured_messages.get(conversation_id, []))

    def capture_log_events(self, conversation_id: str, events: list[LogEvent], *, message_index: int | None = None) -> None:
        if not events:
            return
        if message_index is not None:
            events_by_message = self.captured_log_events_by_message.setdefault(conversation_id, {})
            events_by_message.setdefault(message_index, []).extend(events)
            return
        self.captured_log_events.setdefault(conversation_id, []).extend(events)

    def transcript_log_events(self, conversation_id: str, *, include_all: bool) -> list[LogEvent]:
        events = list(self.captured_log_events.get(conversation_id, []))
        if include_all:
            return events
        return [event for event in events if is_shareable_transcript_log(event)]

    def transcript_log_events_by_message(self, conversation_id: str, *, include_all: bool) -> dict[int, list[LogEvent]]:
        result: dict[int, list[LogEvent]] = {}
        for message_index, events in self.captured_log_events_by_message.get(conversation_id, {}).items():
            filtered_events = events if include_all else [event for event in events if is_shareable_transcript_log(event)]
            if filtered_events:
                result[message_index] = list(filtered_events)
        return result

    def has_unexported_messages(self, project_root: Path | None, conversation_id: str) -> bool:
        self.capture_new_messages(project_root, conversation_id)
        next_index = self.captured_next_indexes.get(conversation_id, self.start_index_for(project_root, conversation_id))
        exported_index = self.exported_next_indexes.get(conversation_id, self.start_index_for(project_root, conversation_id))
        return next_index > exported_index

    def mark_transcript_exported(self, project_root: Path | None, conversation_id: str) -> None:
        self.capture_new_messages(project_root, conversation_id)
        self.exported_next_indexes[conversation_id] = self.captured_next_indexes.get(
            conversation_id, self.start_index_for(project_root, conversation_id)
        )

    def conversation_ids_with_unexported_messages(self, project_root: Path | None) -> list[str]:
        conversation_ids = set(self.conversation_start_indexes)
        conversation_ids.update(self.captured_messages)
        result: list[str] = []
        for conversation_id in sorted(conversation_ids):
            if self.has_unexported_messages(project_root, conversation_id):
                result.append(conversation_id)
        return result
