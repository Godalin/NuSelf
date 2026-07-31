"""Typed contracts shared by the conversation runtime and its callers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from nuself.agent.chat.thread import ThreadMessage, ThreadState
from nuself.config import ConfigSystem

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

    @classmethod
    def from_project(
        cls, project_root: Path | None = None
    ) -> ChatAgentSettings:
        config = ConfigSystem.load(project_root=project_root)
        return cls(
            recent_messages=config.chat.context.recent_messages,
            summary_trigger_messages=(
                config.chat.context.summary_trigger_messages
            ),
            summary_target_chars=config.chat.context.summary_target_chars,
        )


@dataclass(frozen=True)
class ChatResult:
    """Result returned by one chat turn."""

    answer: str
    thread_id: str
    evidence_references: tuple[str, ...] = ()
    confidence: float | None = None
    epistemic_status: str = "inferred"
    trace_id: str | None = None

    @property
    def reply(self) -> str:
        return self.answer

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "answer": self.answer,
            "reply": self.answer,
            "thread_id": self.thread_id,
            "evidence_references": list(self.evidence_references),
            "epistemic_status": self.epistemic_status,
        }
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        if self.trace_id is not None:
            payload["trace_id"] = self.trace_id
        return payload


@dataclass(frozen=True)
class ConversationTurnState:
    """Typed state passed between conversation pipeline stages."""

    thread_id: str
    persisted_state: ThreadState
    user_message: str
    turn_id: str | None = None
    memory_context: str = ""
    base_messages: tuple[ThreadMessage, ...] = ()
    active_messages: tuple[ThreadMessage, ...] = ()
    final_response: ChatStructuredOutput | None = None
    saved_messages: tuple[ThreadMessage, ...] = ()
    updated_thread_state: ThreadState | None = None
    node_trace: tuple[ConversationNodeName, ...] = ()

    @classmethod
    def start(
        cls,
        state: ThreadState,
        message: str,
        thread_id: str,
        *,
        turn_id: str | None = None,
    ) -> ConversationTurnState:
        return cls(
            thread_id=thread_id,
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
