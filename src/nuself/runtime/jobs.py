"""Typed wake-up messages for jobs backed by durable domain records."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace

from nuself.runtime.context import current_runtime_context
from nuself.runtime.messages import RuntimeEnvelope

JobSink = Callable[["JobMessage"], None]


@dataclass(frozen=True)
class JobMessage:
    """Immutable wake-up message; durable job state remains domain-owned."""

    envelope: RuntimeEnvelope
    job_id: str
    resource_id: str

    def __post_init__(self) -> None:
        if self.envelope.kind != "job":
            raise ValueError("job message requires a job envelope")
        if not self.job_id or not self.resource_id:
            raise ValueError("job_id and resource_id are required")
        if self.envelope.context.job_id != self.job_id:
            raise ValueError("job envelope context does not match job_id")

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
        envelope = RuntimeEnvelope(
            kind="job",
            name=name,
            producer=producer,
            context=context,
            payload=payload or {},
        )
        return cls(
            envelope=envelope,
            job_id=job_id,
            resource_id=resource_id,
        )
