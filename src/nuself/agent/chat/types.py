"""Typed contracts shared by the conversation runtime and its callers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from nuself.conversation import CompletedTurn, ConversationMessage, ConversationState

ConversationNodeName = Literal[
    "prepare_context",
    "respond",
    "state_update",
    "compression",
]
EpistemicStatus = Literal[
    "grounded", "inferred", "uncertain", "unsupported"
]


class ChatStructuredOutput(BaseModel):
    """Structured chat response returned by LangChain response_format."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(
        description=(
            "Plain user-facing answer text. "
            "Do not include internal protocol fields."
        )
    )
    evidence_references: list[str] = Field(
        default_factory=list,
        description="Memory, source, or trace ids used.",
    )
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional confidence from 0.0 to 1.0.",
    )
    epistemic_status: EpistemicStatus = Field(
        default="inferred",
        description=(
            "One of grounded, inferred, uncertain, unsupported."
        ),
    )


@dataclass(frozen=True)
class ChatAgentSettings:
    """Context window settings for the chat agent."""

    recent_messages: int
    summary_trigger_messages: int
    summary_target_chars: int

@dataclass(frozen=True)
class ChatResult:
    """Result returned by one chat turn."""

    answer: str
    conversation_id: str
    evidence_references: tuple[str, ...] = ()
    confidence: float | None = None
    epistemic_status: str = "inferred"
    trace_id: str | None = None
    completed_turn: CompletedTurn | None = None

@dataclass(frozen=True)
class ConversationTurnState:
    """Typed state passed between conversation pipeline stages."""

    conversation_id: str
    persisted_state: ConversationState
    user_message: str
    turn_id: str | None = None
    memory_context: str = ""
    base_messages: tuple[ConversationMessage, ...] = ()
    active_messages: tuple[ConversationMessage, ...] = ()
    final_response: ChatStructuredOutput | None = None
    saved_messages: tuple[ConversationMessage, ...] = ()
    updated_conversation_state: ConversationState | None = None
    node_trace: tuple[ConversationNodeName, ...] = ()
    stage_durations_ms: tuple[tuple[str, int], ...] = ()
    recent_message_count: int = 0
    memory_match_count: int = 0
    profile_match_count: int = 0
    source_match_count: int = 0
    prompt_message_count: int = 0

    @classmethod
    def start(
        cls,
        state: ConversationState,
        message: str,
        conversation_id: str,
        *,
        turn_id: str | None = None,
    ) -> ConversationTurnState:
        return cls(
            conversation_id=conversation_id,
            persisted_state=state,
            user_message=message,
            turn_id=turn_id,
        )


@dataclass(frozen=True)
class ConversationNodeResult:
    """Result from one conversation pipeline stage."""

    state: ConversationTurnState


class ConversationGraphRuntimeError(RuntimeError):
    """Raised when the conversation pipeline cannot complete a turn."""

    def __init__(
        self,
        message: str,
        *,
        node: ConversationNodeName | None = None,
        node_trace: tuple[ConversationNodeName, ...] = (),
    ) -> None:
        super().__init__(message)
        self.node = node
        self.node_trace = node_trace
