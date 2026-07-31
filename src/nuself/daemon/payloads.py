"""Typed payload codecs for the daemon JSONL protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast, overload

from nuself.daemon.protocol import JsonValue, ProtocolError
from nuself.daemon.types import WorkerHealth
from nuself.logs import LogEvent
from nuself.runtime.diagnostics import diagnostic_exception_message


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

    @classmethod
    def from_wire(
        cls,
        payload: dict[str, JsonValue],
    ) -> MessagePayload:
        _expect_fields(
            payload,
            required=frozenset({"message"}),
        )
        return cls(
            message=_required_string(
                payload,
                "message",
                context="message response",
                allow_blank=True,
            )
        )


@dataclass(frozen=True)
class DaemonIdentityPayload:
    """Readiness response bound to one state authority."""

    message: str
    authority_id: str

    def to_wire(self) -> dict[str, JsonValue]:
        return {
            "message": self.message,
            "authority_id": self.authority_id,
        }

    @classmethod
    def from_wire(
        cls,
        payload: dict[str, JsonValue],
    ) -> DaemonIdentityPayload:
        _expect_fields(
            payload,
            required=frozenset({"message", "authority_id"}),
        )
        return cls(
            message=_required_string(
                payload,
                "message",
                context="daemon identity response",
                allow_blank=False,
            ),
            authority_id=_required_string(
                payload,
                "authority_id",
                context="daemon identity response",
                allow_blank=False,
            ),
        )


@dataclass(frozen=True)
class ChatRequestPayload:
    """Validated inputs for one daemon chat request."""

    message: str
    thread_id: str = "default"
    turn_id: str | None = None

    def to_wire(self) -> dict[str, JsonValue]:
        payload: dict[str, JsonValue] = {
            "message": self.message,
            "thread_id": self.thread_id,
        }
        if self.turn_id is not None:
            payload["turn_id"] = self.turn_id
        return payload

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

    @classmethod
    def from_wire(
        cls,
        payload: dict[str, JsonValue],
    ) -> WorkerHealthPayload:
        _expect_fields(
            payload,
            required=frozenset(
                {
                    "name",
                    "alive",
                    "last_success_at",
                    "last_error",
                    "consecutive_failures",
                }
            ),
        )
        consecutive_failures = _required_integer(
            payload,
            "consecutive_failures",
            context="worker health response",
        )
        if consecutive_failures < 0:
            raise ProtocolError(
                "worker health response field "
                "'consecutive_failures' must be non-negative"
            )
        return cls(
            name=_required_string(
                payload,
                "name",
                context="worker health response",
            ),
            alive=_required_bool(
                payload,
                "alive",
                context="worker health response",
            ),
            last_success_at=_required_nullable_string(
                payload,
                "last_success_at",
                context="worker health response",
            ),
            last_error=_required_nullable_string(
                payload,
                "last_error",
                context="worker health response",
            ),
            consecutive_failures=consecutive_failures,
        )


@dataclass(frozen=True)
class HealthResponsePayload:
    """Daemon background-worker health response."""

    workers: tuple[WorkerHealthPayload, ...]

    def to_wire(self) -> dict[str, JsonValue]:
        return {"workers": [worker.to_wire() for worker in self.workers]}

    @classmethod
    def from_wire(
        cls,
        payload: dict[str, JsonValue],
    ) -> HealthResponsePayload:
        _expect_fields(
            payload,
            required=frozenset({"workers"}),
        )
        workers = payload.get("workers")
        if not isinstance(workers, list):
            raise ProtocolError(
                "health response field 'workers' must be a list"
            )
        decoded: list[WorkerHealthPayload] = []
        for index, worker in enumerate(workers):
            if not isinstance(worker, dict):
                raise ProtocolError(
                    f"health response worker[{index}] must be an object"
                )
            try:
                decoded.append(WorkerHealthPayload.from_wire(worker))
            except ProtocolError as exc:
                raise ProtocolError(
                    f"health response worker[{index}] is invalid: "
                    f"{diagnostic_exception_message(exc)}"
                ) from exc
        return cls(tuple(decoded))


@dataclass(frozen=True)
class ChatResponsePayload:
    """Stable daemon chat response projection."""

    answer: str
    reply: str
    thread_id: str
    evidence_references: tuple[str, ...]
    epistemic_status: str | None
    confidence: float | None = None

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
        return payload

    @classmethod
    def from_wire(
        cls,
        payload: dict[str, JsonValue],
    ) -> ChatResponsePayload:
        _expect_fields(
            payload,
            required=frozenset(
                {
                    "answer",
                    "reply",
                    "thread_id",
                    "evidence_references",
                    "epistemic_status",
                }
            ),
            optional=frozenset({"confidence"}),
        )
        evidence = payload.get("evidence_references")
        if not isinstance(evidence, list) or not all(
            isinstance(item, str) for item in evidence
        ):
            raise ProtocolError(
                "chat response field 'evidence_references' "
                "must be a string list"
            )
        evidence_references = cast(list[str], evidence)
        epistemic_status = _required_nullable_string(
            payload,
            "epistemic_status",
            context="chat response",
        )
        if epistemic_status not in {
            None,
            "grounded",
            "inferred",
            "uncertain",
            "unsupported",
        }:
            raise ProtocolError(
                "chat response field 'epistemic_status' is invalid"
            )
        confidence = _optional_number(
            payload,
            "confidence",
            context="chat response",
        )
        if confidence is not None and not 0 <= confidence <= 1:
            raise ProtocolError(
                "chat response field 'confidence' must be between 0 and 1"
            )
        return cls(
            answer=_required_string(
                payload,
                "answer",
                context="chat response",
                allow_blank=True,
            ),
            reply=_required_string(
                payload,
                "reply",
                context="chat response",
                allow_blank=True,
            ),
            thread_id=_required_string(
                payload,
                "thread_id",
                context="chat response",
            ),
            evidence_references=tuple(evidence_references),
            epistemic_status=epistemic_status,
            confidence=confidence,
        )


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

    @classmethod
    def from_wire(
        cls,
        payload: dict[str, JsonValue],
    ) -> ActivityOpenResponsePayload:
        _expect_fields(
            payload,
            required=frozenset({"subscription_id"}),
        )
        return cls(
            _required_string(
                payload,
                "subscription_id",
                context="activity open response",
            )
        )


@dataclass(frozen=True)
class ActivityEventsResponsePayload:
    events: tuple[LogEvent, ...]
    dropped_count: int = 0

    def __post_init__(self) -> None:
        if type(self.dropped_count) is not int or self.dropped_count < 0:
            raise ValueError(
                "activity dropped_count must be a non-negative integer"
            )

    def to_wire(self) -> dict[str, JsonValue]:
        return {
            "events": [
                cast(JsonValue, event.to_record())
                for event in self.events
            ],
            "dropped_count": self.dropped_count,
        }

    @classmethod
    def from_wire(
        cls,
        payload: dict[str, JsonValue],
    ) -> ActivityEventsResponsePayload:
        _expect_fields(
            payload,
            required=frozenset({"events", "dropped_count"}),
        )
        events = payload.get("events")
        if not isinstance(events, list):
            raise ProtocolError(
                "activity response field 'events' must be a list"
            )
        dropped_count = payload.get("dropped_count")
        if type(dropped_count) is not int or dropped_count < 0:
            raise ProtocolError(
                "activity response field 'dropped_count' must be "
                "a non-negative integer"
            )
        decoded: list[LogEvent] = []
        for index, event in enumerate(events):
            if not isinstance(event, dict):
                raise ProtocolError(
                    f"activity response event[{index}] must be an object"
                )
            try:
                decoded.append(
                    LogEvent.from_record(
                        cast(dict[str, object], event)
                    )
                )
            except ValueError as exc:
                raise ProtocolError(
                    f"activity response event[{index}] is invalid: "
                    f"{diagnostic_exception_message(exc)}"
                ) from exc
        return cls(tuple(decoded), dropped_count=dropped_count)


@dataclass(frozen=True)
class ActivityCloseResponsePayload:
    closed: bool

    def to_wire(self) -> dict[str, JsonValue]:
        return {"closed": self.closed}

    @classmethod
    def from_wire(
        cls,
        payload: dict[str, JsonValue],
    ) -> ActivityCloseResponsePayload:
        _expect_fields(
            payload,
            required=frozenset({"closed"}),
        )
        return cls(
            _required_bool(
                payload,
                "closed",
                context="activity close response",
            )
        )


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


def _required_integer(
    payload: dict[str, JsonValue],
    field_name: str,
    *,
    context: str,
) -> int:
    value = payload.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolError(
            f"{context} field '{field_name}' must be an integer"
        )
    return value


def _required_bool(
    payload: dict[str, JsonValue],
    field_name: str,
    *,
    context: str,
) -> bool:
    value = payload.get(field_name)
    if not isinstance(value, bool):
        raise ProtocolError(
            f"{context} field '{field_name}' must be a boolean"
        )
    return value


def _required_nullable_string(
    payload: dict[str, JsonValue],
    field_name: str,
    *,
    context: str,
) -> str | None:
    value = payload.get(field_name)
    if value is not None and not isinstance(value, str):
        raise ProtocolError(
            f"{context} field '{field_name}' must be a string or null"
        )
    return value


def _optional_number(
    payload: dict[str, JsonValue],
    field_name: str,
    *,
    context: str,
) -> float | None:
    if field_name not in payload:
        return None
    value = payload[field_name]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ProtocolError(
            f"{context} field '{field_name}' must be a number"
        )
    return float(value)


def _expect_fields(
    payload: dict[str, JsonValue],
    *,
    required: frozenset[str] = frozenset(),
    optional: frozenset[str] = frozenset(),
) -> None:
    missing = required - payload.keys()
    if missing:
        names = ", ".join(sorted(missing))
        raise ProtocolError(f"missing payload field(s): {names}")
    unknown = payload.keys() - required - optional
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ProtocolError(f"unknown payload field(s): {names}")
