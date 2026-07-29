"""Typed payloads shared by runtime event producers and projections."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast

RuntimeLogLevel = Literal["debug", "info", "warning", "error"]
_RUNTIME_LOG_PAYLOAD_FIELDS = frozenset(
    {
        "message",
        "level",
        "node",
        "duration_ms",
        "status",
        "error",
        "metadata",
    }
)


@dataclass(frozen=True)
class RuntimeLogEventPayload:
    """Strict log projection carried by one runtime event envelope."""

    message: str | None = None
    level: RuntimeLogLevel = "info"
    node: str | None = None
    duration_ms: int | None = None
    status: str | None = None
    error: str | None = None
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        for field_name in ("message", "node", "status", "error"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, str):
                raise TypeError(
                    f"runtime event log {field_name} must be a string"
                )
        if self.level not in {"debug", "info", "warning", "error"}:
            raise ValueError("runtime event log level is invalid")
        if self.duration_ms is not None and (
            type(self.duration_ms) is not int or self.duration_ms < 0
        ):
            raise TypeError(
                "runtime event log duration_ms must be a non-negative integer"
            )
        if self.metadata is not None and not isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
            self.metadata,
            Mapping,
        ):
            raise TypeError("runtime event log metadata must be a mapping")
    def to_mapping(self) -> dict[str, object]:
        payload: dict[str, object] = {"level": self.level}
        for field_name in (
            "message",
            "node",
            "duration_ms",
            "status",
            "error",
            "metadata",
        ):
            value = getattr(self, field_name)
            if value is not None:
                payload[field_name] = value
        return payload

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, object],
    ) -> RuntimeLogEventPayload:
        unknown = sorted(set(payload) - _RUNTIME_LOG_PAYLOAD_FIELDS)
        if unknown:
            raise ValueError(
                f"runtime event log payload has unknown fields: {unknown!r}"
            )
        level = payload.get("level", "info")
        if not isinstance(level, str):
            raise TypeError("runtime event log level must be a string")
        return cls(
            message=_optional_string(payload, "message"),
            level=cast(RuntimeLogLevel, level),
            node=_optional_string(payload, "node"),
            duration_ms=_optional_integer(payload, "duration_ms"),
            status=_optional_string(payload, "status"),
            error=_optional_string(payload, "error"),
            metadata=_optional_mapping(payload, "metadata"),
        )


def validate_runtime_log_event_payload(
    payload: Mapping[str, object],
) -> None:
    """Validate one core event payload before projection delivery."""

    RuntimeLogEventPayload.from_mapping(payload)


def _optional_string(
    payload: Mapping[str, object],
    field_name: str,
) -> str | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"runtime event log {field_name} must be a string")
    return value


def _optional_integer(
    payload: Mapping[str, object],
    field_name: str,
) -> int | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if type(value) is not int:
        raise TypeError(
            f"runtime event log {field_name} must be an integer"
        )
    return value


def _optional_mapping(
    payload: Mapping[str, object],
    field_name: str,
) -> Mapping[str, object] | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError(
            f"runtime event log {field_name} must be a mapping"
        )
    return cast(Mapping[str, object], value)
