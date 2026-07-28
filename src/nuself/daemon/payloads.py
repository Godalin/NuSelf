"""Typed payload codecs for the daemon JSONL protocol."""

from __future__ import annotations

from dataclasses import dataclass

from nuself.daemon.protocol import JsonValue, ProtocolError
from nuself.daemon.types import WorkerHealth


@dataclass(frozen=True)
class MessagePayload:
    """One human-readable daemon response message."""

    message: str

    def to_wire(self) -> dict[str, JsonValue]:
        return {"message": self.message}


@dataclass(frozen=True)
class ChatRequestPayload:
    """Validated inputs for one daemon chat request."""

    message: str
    thread_id: str = "default"
    turn_id: str | None = None

    @classmethod
    def from_wire(cls, payload: dict[str, JsonValue]) -> ChatRequestPayload:
        message = payload.get("message")
        if not isinstance(message, str):
            raise ProtocolError("chat request requires string payload field 'message'")
        thread_id_raw = payload.get("thread_id")
        turn_id_raw = payload.get("turn_id")
        return cls(
            message=message,
            thread_id=(thread_id_raw if isinstance(thread_id_raw, str) else "default"),
            turn_id=turn_id_raw if isinstance(turn_id_raw, str) else None,
        )


@dataclass(frozen=True)
class WorkerHealthPayload:
    """Serializable worker-health snapshot."""

    name: str
    alive: bool
    last_success_at: str | None
    last_error: str | None
    consecutive_failures: int

    @classmethod
    def from_health(cls, health: WorkerHealth) -> WorkerHealthPayload:
        return cls(
            name=health.name,
            alive=health.alive,
            last_success_at=health.last_success_at,
            last_error=health.last_error,
            consecutive_failures=health.consecutive_failures,
        )

    def to_wire(self) -> dict[str, JsonValue]:
        return {
            "name": self.name,
            "alive": self.alive,
            "last_success_at": self.last_success_at,
            "last_error": self.last_error,
            "consecutive_failures": self.consecutive_failures,
        }


@dataclass(frozen=True)
class HealthResponsePayload:
    """Daemon background-worker health response."""

    workers: tuple[WorkerHealthPayload, ...]

    def to_wire(self) -> dict[str, JsonValue]:
        return {"workers": [worker.to_wire() for worker in self.workers]}


@dataclass(frozen=True)
class ChatResponsePayload:
    """Stable daemon chat response projection."""

    answer: str
    reply: str
    thread_id: str
    evidence_references: tuple[str, ...]
    epistemic_status: str | None
    confidence: float | None = None
    memory_update: str | None = None

    def to_wire(self) -> dict[str, JsonValue]:
        payload: dict[str, JsonValue] = {
            "answer": self.answer,
            "reply": self.reply,
            "thread_id": self.thread_id,
            "evidence_references": list(self.evidence_references),
            "epistemic_status": self.epistemic_status,
        }
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        if self.memory_update is not None:
            payload["memory_update"] = self.memory_update
        return payload
