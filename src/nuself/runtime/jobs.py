"""Typed wake-up messages for jobs backed by durable domain records."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import cast

from nuself.runtime.messages import RuntimeEnvelope
JobSink = Callable[["JobMessage"], None]
_JOB_PAYLOAD_FIELDS = frozenset({"resource_id", "data"})


@dataclass(frozen=True)
class JobPayload:
    """Routing identity and optional hints carried by a job envelope."""

    resource_id: str
    data: Mapping[str, object] = field(
        default_factory=dict[str, object]
    )

    def __post_init__(self) -> None:
        if not isinstance(self.resource_id, str) or not self.resource_id.strip():  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError("job payload resource_id must not be blank")
        if not isinstance(self.data, Mapping):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("job payload data must be a mapping")

    def to_mapping(self) -> dict[str, object]:
        return {
            "resource_id": self.resource_id,
            "data": self.data,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> JobPayload:
        fields = set(payload)
        missing = sorted(_JOB_PAYLOAD_FIELDS - fields)
        unknown = sorted(fields - _JOB_PAYLOAD_FIELDS)
        if missing or unknown:
            raise ValueError(
                "job payload fields are invalid "
                f"(missing={missing!r}, unknown={unknown!r})"
            )
        resource_id = payload["resource_id"]
        if not isinstance(resource_id, str):
            raise TypeError("job payload resource_id must be a string")
        data = payload["data"]
        if not isinstance(data, Mapping):
            raise TypeError("job payload data must be a mapping")
        return cls(
            resource_id=resource_id,
            data=cast(Mapping[str, object], data),
        )


@dataclass(frozen=True)
class JobMessage:
    """Immutable wake-up message; durable job state remains domain-owned."""

    envelope: RuntimeEnvelope
    _payload: JobPayload = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.envelope.kind != "job":
            raise ValueError("job message requires a job envelope")
        if self.envelope.context.job_id is None:
            raise ValueError("job envelope context requires job_id")
        object.__setattr__(
            self,
            "_payload",
            JobPayload.from_mapping(self.envelope.payload),
        )

    @property
    def job_id(self) -> str:
        value = self.envelope.context.job_id
        if value is None:
            raise RuntimeError("validated job envelope lost job_id")
        return value

    @property
    def name(self) -> str:
        return self.envelope.name

    @property
    def producer(self) -> str:
        return self.envelope.producer

    @property
    def resource_id(self) -> str:
        return self._payload.resource_id

    @property
    def payload(self) -> Mapping[str, object]:
        return self._payload.data
