"""Typed wake-up messages for jobs backed by durable domain records."""

from __future__ import annotations

import queue
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from threading import Condition
from typing import Literal, cast

from nuself.runtime.context import current_runtime_context
from nuself.runtime.messages import RuntimeEnvelope

JobSink = Callable[["JobMessage"], None]
JobAdmissionResult = Literal["admitted", "duplicate", "full"]
_JOB_PAYLOAD_FIELDS = frozenset({"resource_id", "data"})


def _empty_job_data() -> dict[str, object]:
    return {}


@dataclass(frozen=True)
class JobPayload:
    """Routing identity and optional hints carried by a job envelope."""

    resource_id: str
    data: Mapping[str, object] = field(default_factory=_empty_job_data)

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

    @classmethod
    def create(
        cls,
        *,
        name: str,
        producer: str,
        job_id: str,
        resource_id: str,
        payload: Mapping[str, object] | None = None,
    ) -> JobMessage:
        context = replace(current_runtime_context(), job_id=job_id)
        job_payload = JobPayload(
            resource_id=resource_id,
            data={} if payload is None else payload,
        )
        envelope = RuntimeEnvelope(
            kind="job",
            name=name,
            producer=producer,
            context=context,
            payload=job_payload.to_mapping(),
        )
        return cls(envelope=envelope)


class JobAdmissionQueue:
    """Bounded wake-up admission with pending and in-flight coalescing."""

    def __init__(self, capacity: int) -> None:
        if type(capacity) is not int or capacity < 1:
            raise ValueError("job admission capacity must be a positive integer")
        self._capacity = capacity
        self._condition = Condition()
        self._pending: deque[JobMessage] = deque()
        self._active: set[tuple[str, str, str]] = set()

    def admit(self, message: JobMessage) -> JobAdmissionResult:
        """Admit one distinct durable identity without blocking."""

        identity = _job_identity(message)
        with self._condition:
            if identity in self._active:
                return "duplicate"
            if len(self._pending) >= self._capacity:
                return "full"
            self._pending.append(message)
            self._active.add(identity)
            self._condition.notify()
            return "admitted"

    def get(self, *, timeout: float | None = None) -> JobMessage:
        """Acquire one message while retaining its identity as in-flight."""

        if timeout is not None and timeout < 0:
            raise ValueError("job admission timeout must not be negative")
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._condition:
            while not self._pending:
                if deadline is None:
                    self._condition.wait()
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise queue.Empty
                self._condition.wait(remaining)
            return self._pending.popleft()

    def get_nowait(self) -> JobMessage:
        """Acquire one immediately available message."""

        return self.get(timeout=0)

    def complete(self, message: JobMessage) -> None:
        """Release one acquired identity after processing."""

        identity = _job_identity(message)
        with self._condition:
            if identity not in self._active:
                raise ValueError("job admission identity is not active")
            self._active.remove(identity)

    def drain(self) -> tuple[JobMessage, ...]:
        """Remove every pending message while preserving in-flight ownership."""

        with self._condition:
            drained = tuple(self._pending)
            self._pending.clear()
            for message in drained:
                self._active.remove(_job_identity(message))
            return drained

    def empty(self) -> bool:
        """Return whether no pending message is waiting."""

        with self._condition:
            return not self._pending

    @property
    def pending_count(self) -> int:
        with self._condition:
            return len(self._pending)


def _job_identity(message: JobMessage) -> tuple[str, str, str]:
    return (message.name, message.job_id, message.resource_id)
