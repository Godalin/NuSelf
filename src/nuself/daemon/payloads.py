"""Typed payload codecs for the daemon JSONL protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast, overload

from nuself.daemon.protocol import JsonValue, ProtocolError
from nuself.runtime.log_event import LogEvent
from nuself.runtime.diagnostics import diagnostic_exception_message


@dataclass(frozen=True)
class EmptyPayload:
    """Validated empty daemon request or response payload."""

    def to_wire(self) -> dict[str, JsonValue]:
        return {}

    @classmethod
    def from_wire(
        cls,
        payload: dict[str, JsonValue],
    ) -> EmptyPayload:
        _expect_fields(payload)
        return cls()


@dataclass(frozen=True)
class DaemonIdentityPayload:
    """Readiness response bound to one state authority."""

    authority_id: str

    def to_wire(self) -> dict[str, JsonValue]:
        return {"authority_id": self.authority_id}

    @classmethod
    def from_wire(
        cls,
        payload: dict[str, JsonValue],
    ) -> DaemonIdentityPayload:
        _expect_fields(
            payload,
            required=frozenset({"authority_id"}),
        )
        return cls(
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
    conversation_id: str = "default"
    turn_id: str | None = None

    def to_wire(self) -> dict[str, JsonValue]:
        payload: dict[str, JsonValue] = {
            "message": self.message,
            "conversation_id": self.conversation_id,
        }
        if self.turn_id is not None:
            payload["turn_id"] = self.turn_id
        return payload

    @classmethod
    def from_wire(cls, payload: dict[str, JsonValue]) -> ChatRequestPayload:
        _expect_fields(
            payload,
            required=frozenset({"message"}),
            optional=frozenset({"conversation_id", "turn_id"}),
        )
        return cls(
            message=_required_string(
                payload,
                "message",
                context="chat request",
                allow_blank=True,
            ),
            conversation_id=_optional_non_blank_string(
                payload,
                "conversation_id",
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
class SchedulerHealthPayload:
    """Serializable unified scheduler-health snapshot."""

    running: bool
    accepting: bool
    pending: int
    in_flight: int
    capacity: int
    last_error: str | None

    def to_wire(self) -> dict[str, JsonValue]:
        return {
            "running": self.running,
            "accepting": self.accepting,
            "pending": self.pending,
            "in_flight": self.in_flight,
            "capacity": self.capacity,
            "last_error": self.last_error,
        }

    @classmethod
    def from_wire(
        cls,
        payload: dict[str, JsonValue],
    ) -> SchedulerHealthPayload:
        _expect_fields(
            payload,
            required=frozenset(
                {
                    "running",
                    "accepting",
                    "pending",
                    "in_flight",
                    "capacity",
                    "last_error",
                }
            ),
        )
        counts = {
            name: _required_integer(
                payload, name, context="scheduler health response"
            )
            for name in ("pending", "in_flight", "capacity")
        }
        if any(value < 0 for value in counts.values()) or counts["capacity"] < 1:
            raise ProtocolError("scheduler health counts are invalid")
        return cls(
            running=_required_bool(
                payload,
                "running",
                context="scheduler health response",
            ),
            accepting=_required_bool(
                payload,
                "accepting",
                context="scheduler health response",
            ),
            pending=counts["pending"],
            in_flight=counts["in_flight"],
            capacity=counts["capacity"],
            last_error=_required_nullable_string(
                payload,
                "last_error",
                context="scheduler health response",
            ),
        )


@dataclass(frozen=True)
class HealthResponsePayload:
    """Daemon unified-scheduler health response."""

    scheduler: SchedulerHealthPayload

    def to_wire(self) -> dict[str, JsonValue]:
        return {"scheduler": self.scheduler.to_wire()}

    @classmethod
    def from_wire(
        cls,
        payload: dict[str, JsonValue],
    ) -> HealthResponsePayload:
        _expect_fields(
            payload,
            required=frozenset({"scheduler"}),
        )
        scheduler = payload.get("scheduler")
        if not isinstance(scheduler, dict):
            raise ProtocolError("health response scheduler must be an object")
        return cls(SchedulerHealthPayload.from_wire(scheduler))


@dataclass(frozen=True)
class ChatResponsePayload:
    """Stable daemon chat response projection."""

    answer: str
    conversation_id: str
    evidence_references: tuple[str, ...]
    epistemic_status: str | None
    confidence: float | None = None

    def to_wire(self) -> dict[str, JsonValue]:
        payload: dict[str, JsonValue] = {
            "answer": self.answer,
            "conversation_id": self.conversation_id,
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
                    "conversation_id",
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
            conversation_id=_required_string(
                payload,
                "conversation_id",
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
