"""Immutable structured-log projection model and record codec."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import InitVar, dataclass, field
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from nuself.runtime.audit.types import LOG_COMPONENTS, LogComponent, LogLevel
from nuself.runtime.identities import require_persisted_event_name
from nuself.runtime.messages import (
    RUNTIME_SCHEMA_VERSION,
    freeze_json_value,
    thaw_json_value,
)

_LEGACY_LOG_INSTANT = datetime.min.replace(tzinfo=UTC)


@dataclass(frozen=True)
class LogEvent:
    """One immutable NuSelf log projection."""

    time: str
    level: LogLevel
    component: LogComponent
    event: str
    message: str
    event_id: str | None = field(default_factory=lambda: uuid4().hex)
    schema_version: int | None = RUNTIME_SCHEMA_VERSION
    conversation_id: str | None = None
    reason_id: str | None = None
    request_id: str | None = None
    turn_id: str | None = None
    job_id: str | None = None
    trace_id: str | None = None
    source: str | None = None
    node: str | None = None
    duration_ms: int | None = None
    status: str | None = None
    error: str | None = None
    metadata: Mapping[str, object] | None = None
    _allow_empty_time: InitVar[bool] = False
    _instant: datetime | None = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self, _allow_empty_time: bool) -> None:
        if not isinstance(self.time, str):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("log time must be a string")
        if self.level not in {"debug", "info", "warning", "error"}:
            raise ValueError("log level is invalid")
        if self.component not in LOG_COMPONENTS:
            raise ValueError("log component is invalid")
        for field_name in ("event", "message"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"log {field_name} must be a string")
        if (self.event_id is None) != (self.schema_version is None):
            raise ValueError(
                "log event_id and schema_version must both be present or absent"
            )
        if self.event_id is not None and (
            not isinstance(self.event_id, str)  # pyright: ignore[reportUnnecessaryIsInstance]
            or not self.event_id.strip()
        ):
            raise ValueError("log event_id must not be blank")
        if self.schema_version is not None and (
            type(self.schema_version) is not int
            or self.schema_version != RUNTIME_SCHEMA_VERSION
        ):
            raise ValueError("log schema_version is unsupported")
        object.__setattr__(
            self,
            "_instant",
            _parse_log_timestamp(
                self.time,
                allow_empty=(
                    _allow_empty_time
                    and self.event == "legacy"
                    and self.event_id is None
                    and self.schema_version is None
                ),
            ),
        )
        for field_name in (
            "conversation_id",
            "reason_id",
            "request_id",
            "turn_id",
            "job_id",
            "trace_id",
            "source",
            "node",
            "status",
            "error",
        ):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, str):
                raise TypeError(f"log {field_name} must be a string")
        if self.duration_ms is not None and (
            type(self.duration_ms) is not int or self.duration_ms < 0
        ):
            raise TypeError("log duration_ms must be a non-negative integer")
        if self.schema_version is not None:
            _require_log_identity(self.component, self.event)
        if self.metadata is None:
            return
        if not isinstance(self.metadata, Mapping):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("log event metadata must be a mapping")
        object.__setattr__(
            self,
            "metadata",
            cast(Mapping[str, object], freeze_json_value(self.metadata)),
        )

    def to_record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "time": self.time,
            "level": self.level,
            "component": self.component,
            "event": self.event,
            "message": self.message,
        }
        for key, value in (
            ("event_id", self.event_id),
            ("schema_version", self.schema_version),
            ("conversation_id", self.conversation_id),
            ("reason_id", self.reason_id),
            ("request_id", self.request_id),
            ("turn_id", self.turn_id),
            ("job_id", self.job_id),
            ("trace_id", self.trace_id),
            ("source", self.source),
            ("node", self.node),
            ("duration_ms", self.duration_ms),
            ("status", self.status),
            ("error", self.error),
            ("metadata", self.metadata),
        ):
            if value is not None:
                record[key] = thaw_json_value(value)
        return record

    def chronological_key(self) -> tuple[int, datetime]:
        """Return an instant-aware stable sorting key."""

        if self._instant is None:
            return (0, _LEGACY_LOG_INSTANT)
        return (1, self._instant)

    @classmethod
    def from_record(cls, record: dict[str, object]) -> LogEvent:
        component = record.get("component")
        level = record.get("level")
        event = record.get("event")
        message = record.get("message")
        timestamp = record.get("time")
        if component not in LOG_COMPONENTS:
            raise ValueError("log component is invalid")
        if level not in {"debug", "info", "warning", "error"}:
            raise ValueError("log level is invalid")
        if (
            not isinstance(event, str)
            or not isinstance(message, str)
            or not isinstance(timestamp, str)
        ):
            raise ValueError("log event fields are invalid")
        return cls(
            time=timestamp,
            level=cast(LogLevel, level),
            component=component,
            event=event,
            message=message,
            event_id=_record_optional_str(record, "event_id"),
            schema_version=_record_optional_int(record, "schema_version"),
            conversation_id=_record_optional_str(record, "conversation_id"),
            reason_id=_record_optional_str(record, "reason_id"),
            request_id=_record_optional_str(record, "request_id"),
            turn_id=_record_optional_str(record, "turn_id"),
            job_id=_record_optional_str(record, "job_id"),
            trace_id=_record_optional_str(record, "trace_id"),
            source=_record_optional_str(record, "source"),
            node=_record_optional_str(record, "node"),
            duration_ms=_record_optional_int(record, "duration_ms"),
            status=_record_optional_str(record, "status"),
            error=_record_optional_str(record, "error"),
            metadata=_record_optional_mapping(record, "metadata"),
        )


def _require_log_identity(component: object, event: object) -> None:
    if component not in LOG_COMPONENTS:
        raise ValueError("log component is invalid")
    try:
        require_persisted_event_name(event)
    except ValueError as exc:
        raise ValueError("log event name is invalid") from exc


def _parse_log_timestamp(value: str, *, allow_empty: bool) -> datetime | None:
    if value == "":
        if allow_empty:
            return None
        raise ValueError("structured log time must not be empty")
    try:
        instant = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("log time must be an ISO-8601 timestamp") from exc
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("log time must include a timezone")
    return instant


def _record_optional_str(
    record: Mapping[str, object], field_name: str
) -> str | None:
    value = record.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"log {field_name} must be a string")
    return value


def _record_optional_int(
    record: Mapping[str, object], field_name: str
) -> int | None:
    value = record.get(field_name)
    if value is None:
        return None
    if type(value) is not int:
        raise TypeError(f"log {field_name} must be an integer")
    return value


def _record_optional_mapping(
    record: Mapping[str, object], field_name: str
) -> Mapping[str, object] | None:
    value = record.get(field_name)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError(f"log {field_name} must be a mapping")
    return cast(Mapping[str, object], value)
