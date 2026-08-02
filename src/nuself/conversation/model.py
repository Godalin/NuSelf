"""Conversation domain models and stable turn errors."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Literal, cast

type ConversationRole = Literal["user", "assistant"]


class ConversationTurnConflictError(RuntimeError):
    """A stable turn ID was reused with different user input."""


class ConversationTurnIncompleteError(RuntimeError):
    """A prior execution of one stable turn did not commit a reply."""


@dataclass(frozen=True)
class PendingTurn:
    """Payload-safe evidence that one stable turn began execution."""

    turn_id: str
    input_digest: str

    @classmethod
    def from_message(cls, turn_id: str, message: str) -> PendingTurn:
        return cls(
            turn_id=turn_id,
            input_digest=hashlib.sha256(message.encode("utf-8")).hexdigest(),
        )

    def to_wire(self) -> dict[str, str]:
        return {
            "turn_id": self.turn_id,
            "input_digest": self.input_digest,
        }

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> PendingTurn:
        if set(data) != {"turn_id", "input_digest"}:
            raise ValueError("pending turn fields are invalid")
        turn_id = data["turn_id"]
        input_digest = data["input_digest"]
        if not isinstance(turn_id, str) or not turn_id:
            raise ValueError("pending turn ID must be a non-empty string")
        if (
            not isinstance(input_digest, str)
            or len(input_digest) != 64
            or any(char not in "0123456789abcdef" for char in input_digest)
        ):
            raise ValueError("pending turn input digest is invalid")
        return cls(turn_id=turn_id, input_digest=input_digest)


@dataclass(frozen=True)
class ConversationMessage:
    """A persisted user or assistant message in a NuSelf conversation."""

    role: ConversationRole
    content: str
    turn_id: str | None = None

    def to_wire(self) -> dict[str, str]:
        wire = {"role": self.role, "content": self.content}
        if self.turn_id is not None:
            wire["turn_id"] = self.turn_id
        return wire

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> ConversationMessage:
        unexpected = set(data) - {"role", "content", "turn_id"}
        if unexpected:
            raise ValueError("conversation message contains unsupported fields")
        role = data.get("role")
        content = data.get("content")
        turn_id = data.get("turn_id")
        if role not in {"user", "assistant"}:
            raise ValueError(
                "conversation message role must be user or assistant"
            )
        if not isinstance(content, str):
            raise ValueError("conversation message content must be a string")
        if turn_id is not None and not isinstance(turn_id, str):
            raise ValueError(
                "conversation message turn_id must be a string when present"
            )
        return cls(
            role=cast(ConversationRole, role),
            content=content,
            turn_id=turn_id,
        )


@dataclass(frozen=True)
class ConversationState:
    """Persisted state for one conversation."""

    conversation_id: str
    summary: str = ""
    messages: list[ConversationMessage] = field(
        default_factory=list[ConversationMessage]
    )
    message_start_index: int = 0
    next_message_index: int = 0
    archived: bool = False
    pending_turns: tuple[PendingTurn, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.next_message_index == self.message_start_index and self.messages:
            object.__setattr__(
                self,
                "next_message_index",
                self.message_start_index + len(self.messages),
            )
        self._validate_indexes()
        pending_ids = [item.turn_id for item in self.pending_turns]
        if len(pending_ids) != len(set(pending_ids)):
            raise ValueError("pending turn IDs must be unique")

    def to_wire(self) -> dict[str, object]:
        self._validate_indexes()
        wire: dict[str, object] = {
            "conversation_id": self.conversation_id,
            "summary": self.summary,
            "messages": [message.to_wire() for message in self.messages],
            "message_start_index": self.message_start_index,
            "next_message_index": self.next_message_index,
            "archived": self.archived,
        }
        if self.pending_turns:
            wire["pending_turns"] = [
                pending.to_wire() for pending in self.pending_turns
            ]
        return wire

    def _validate_indexes(self) -> None:
        if (
            type(self.message_start_index) is not int
            or self.message_start_index < 0
        ):
            raise ValueError(
                "message_start_index must be a non-negative integer"
            )
        if (
            type(self.next_message_index) is not int
            or self.next_message_index < 0
        ):
            raise ValueError(
                "next_message_index must be a non-negative integer"
            )
        if self.next_message_index != self.message_start_index + len(self.messages):
            raise ValueError(
                "next_message_index must equal message_start_index plus "
                "the message count"
            )

    @classmethod
    def empty(cls, conversation_id: str) -> ConversationState:
        return cls(conversation_id=conversation_id)

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> ConversationState:
        conversation_id = data.get("conversation_id")
        summary = data.get("summary")
        messages = data.get("messages")
        message_start_index = data.get("message_start_index", 0)
        next_message_index = data.get("next_message_index")
        archived = data.get("archived", False)
        pending_turns = data.get("pending_turns", [])
        if not isinstance(conversation_id, str):
            raise ValueError("conversation_id must be a string")
        if not isinstance(summary, str):
            raise ValueError("summary must be a string")
        if not isinstance(messages, list):
            raise ValueError("messages must be a list")
        if type(message_start_index) is not int or message_start_index < 0:
            raise ValueError(
                "message_start_index must be a non-negative integer"
            )
        message_items = cast(list[object], messages)
        if any(not isinstance(item, dict) for item in message_items):
            raise ValueError("every conversation message must be an object")
        parsed_messages = [
            ConversationMessage.from_wire(cast(dict[str, object], item))
            for item in message_items
        ]
        if next_message_index is None:
            next_message_index = message_start_index + len(parsed_messages)
        if type(next_message_index) is not int or next_message_index < 0:
            raise ValueError("next_message_index must be a non-negative integer")
        if not isinstance(archived, bool):
            raise ValueError("archived must be a boolean")
        if not isinstance(pending_turns, list):
            raise ValueError("pending_turns must be an object list")
        pending_items = cast(list[object], pending_turns)
        if any(not isinstance(item, dict) for item in pending_items):
            raise ValueError("pending_turns must be an object list")
        decoded_pending = tuple(
            PendingTurn.from_wire(cast(dict[str, object], item))
            for item in pending_items
        )
        pending_ids = [item.turn_id for item in decoded_pending]
        if len(pending_ids) != len(set(pending_ids)):
            raise ValueError("pending turn IDs must be unique")
        expected_next_index = message_start_index + len(parsed_messages)
        if next_message_index != expected_next_index:
            raise ValueError(
                "next_message_index must equal message_start_index plus "
                "the message count"
            )
        return cls(
            conversation_id=conversation_id,
            summary=summary,
            messages=parsed_messages,
            message_start_index=message_start_index,
            next_message_index=next_message_index,
            archived=archived,
            pending_turns=decoded_pending,
        )


@dataclass(frozen=True)
class CompletedTurn:
    """Immutable committed-turn evidence exported by conversation."""

    conversation_id: str
    start_index: int
    end_index: int
    user_content: str
    assistant_content: str
    turn_id: str | None = None
