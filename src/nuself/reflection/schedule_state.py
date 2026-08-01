"""Persisted reflection scheduling state and strict decoding."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from nuself.runtime.messages import encode_json_value
from nuself.storage import StorageCollection

REFLECTION_SCHEDULE_STATE_VERSION = 1


class ReflectionScheduleStateError(ValueError):
    """Raised when persisted scheduling state is not trustworthy."""


class ReflectionScheduleState(BaseModel):
    """Strict cooldown and daily-cap state."""

    model_config = ConfigDict(strict=True, extra="forbid")

    schema_version: Literal[1]
    timestamp: datetime
    daily_count: int = Field(ge=0)
    daily_date: date
    title: str | None = None
    body: str | None = None

    @field_validator("timestamp")
    @classmethod
    def _timestamp_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value

    def to_record(self) -> dict[str, object]:
        return cast(
            dict[str, object],
            self.model_dump(mode="json", exclude_none=True),
        )


def read_reflection_schedule_state(
    collection: StorageCollection,
) -> ReflectionScheduleState | None:
    """Decode the one canonical reflection schedule record."""

    record = collection.get("reflection")
    if record is None:
        return None
    try:
        return ReflectionScheduleState.model_validate_json(
            encode_json_value(
                {
                    key: value
                    for key, value in record.items()
                    if key != "id"
                },
                ensure_ascii=True,
            )
        )
    except ValidationError:
        raise ReflectionScheduleStateError(
            "reflection schedule state is malformed or unsupported"
        ) from None
