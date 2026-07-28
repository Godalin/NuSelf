"""Typed payload codecs for the daemon JSONL protocol."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import cast, overload

from nuself.daemon.protocol import JsonValue, ProtocolError
from nuself.daemon.types import WorkerHealth
from nuself.logs import LogEvent


@dataclass(frozen=True)
class EmptyRequestPayload:
    """Validated empty payload for control requests."""

    @classmethod
    def from_wire(
        cls,
        payload: dict[str, JsonValue],
    ) -> EmptyRequestPayload:
        _expect_fields(payload)
        return cls()


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
        _expect_fields(
            payload,
            required=frozenset({"message"}),
            optional=frozenset({"thread_id", "turn_id"}),
        )
        return cls(
            message=_required_string(
                payload,
                "message",
                context="chat request",
                allow_blank=True,
            ),
            thread_id=_optional_non_blank_string(
                payload,
                "thread_id",
                default="default",
                context="chat request",
            ),
            turn_id=_optional_non_blank_string(
                payload,
                "turn_id",
                default=None,
                context="chat request",
            ),
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


@dataclass(frozen=True)
class ActivityOpenRequestPayload:
    turn_id: str

    @classmethod
    def from_wire(
        cls,
        payload: dict[str, JsonValue],
    ) -> ActivityOpenRequestPayload:
        _expect_fields(
            payload,
            required=frozenset({"turn_id"}),
        )
        return cls(
            turn_id=_required_string(
                payload,
                "turn_id",
                context="activity",
            )
        )


@dataclass(frozen=True)
class ActivityNextRequestPayload:
    subscription_id: str
    timeout_ms: int = 200
    limit: int = 50

    @classmethod
    def from_wire(
        cls,
        payload: dict[str, JsonValue],
    ) -> ActivityNextRequestPayload:
        _expect_fields(
            payload,
            required=frozenset({"subscription_id"}),
            optional=frozenset({"timeout_ms", "limit"}),
        )
        timeout_ms = _optional_integer(payload, "timeout_ms", default=200)
        limit = _optional_integer(payload, "limit", default=50)
        if not 0 <= timeout_ms <= 5_000:
            raise ProtocolError("activity timeout_ms must be between 0 and 5000")
        if not 1 <= limit <= 256:
            raise ProtocolError("activity limit must be between 1 and 256")
        return cls(
            subscription_id=_required_string(
                payload,
                "subscription_id",
                context="activity",
            ),
            timeout_ms=timeout_ms,
            limit=limit,
        )


@dataclass(frozen=True)
class ActivityCloseRequestPayload:
    subscription_id: str

    @classmethod
    def from_wire(
        cls,
        payload: dict[str, JsonValue],
    ) -> ActivityCloseRequestPayload:
        _expect_fields(
            payload,
            required=frozenset({"subscription_id"}),
        )
        return cls(
            subscription_id=_required_string(
                payload,
                "subscription_id",
                context="activity",
            )
        )


@dataclass(frozen=True)
class ActivityOpenResponsePayload:
    subscription_id: str

    def to_wire(self) -> dict[str, JsonValue]:
        return {"subscription_id": self.subscription_id}


@dataclass(frozen=True)
class ActivityEventsResponsePayload:
    events: tuple[LogEvent, ...]

    def to_wire(self) -> dict[str, JsonValue]:
        return {"events": [_json_value(event.to_record()) for event in self.events]}


@dataclass(frozen=True)
class ActivityCloseResponsePayload:
    closed: bool

    def to_wire(self) -> dict[str, JsonValue]:
        return {"closed": self.closed}


def _required_string(
    payload: dict[str, JsonValue],
    field_name: str,
    *,
    context: str,
    allow_blank: bool = False,
) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str):
        raise ProtocolError(
            f"{context} field '{field_name}' must be a string"
        )
    if not allow_blank and not value.strip():
        raise ProtocolError(
            f"{context} field '{field_name}' must be a non-blank string"
        )
    return value


@overload
def _optional_non_blank_string(
    payload: dict[str, JsonValue],
    field_name: str,
    *,
    default: str,
    context: str,
) -> str: ...


@overload
def _optional_non_blank_string(
    payload: dict[str, JsonValue],
    field_name: str,
    *,
    default: None,
    context: str,
) -> str | None: ...


def _optional_non_blank_string(
    payload: dict[str, JsonValue],
    field_name: str,
    *,
    default: str | None,
    context: str,
) -> str | None:
    if field_name not in payload:
        return default
    return _required_string(
        payload,
        field_name,
        context=context,
    )


def _optional_integer(
    payload: dict[str, JsonValue],
    field_name: str,
    *,
    default: int,
) -> int:
    value = payload.get(field_name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolError(f"activity field '{field_name}' must be an integer")
    return value


def _expect_fields(
    payload: dict[str, JsonValue],
    *,
    required: frozenset[str] = frozenset(),
    optional: frozenset[str] = frozenset(),
) -> None:
    unknown = payload.keys() - required - optional
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ProtocolError(f"unknown payload field(s): {names}")


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str | bool | int | float):
        return value
    if isinstance(value, list | tuple):
        sequence = cast(Iterable[object], value)
        return [_json_value(item) for item in sequence]
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        return {str(key): _json_value(item) for key, item in mapping.items()}
    raise TypeError(f"activity event contains non-JSON value: {type(value).__name__}")
