"""Durable, producer-neutral inputs for memory curation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, cast
from uuid import NAMESPACE_URL, uuid5

from nuself.clock import utc_now_iso
from nuself.storage import StorageBackend


type ObservationStatus = Literal["pending", "processed"]


@dataclass(frozen=True)
class MemoryObservation:
    """One ordered piece of evidence accepted by the memory domain."""

    id: str
    source_ref: str
    fragments: tuple[str, ...]
    observed_at: str
    status: ObservationStatus = "pending"
    source_trace_id: str | None = None

    @classmethod
    def create(
        cls,
        *,
        source_ref: str,
        fragments: tuple[str, ...],
        source_trace_id: str | None = None,
    ) -> MemoryObservation:
        normalized = tuple(fragment.strip() for fragment in fragments if fragment.strip())
        if not normalized:
            raise ValueError("memory observation requires non-empty fragments")
        if source_ref.strip() == "":
            raise ValueError("memory observation source_ref must not be blank")
        return cls(
            id=f"obs_{uuid5(NAMESPACE_URL, source_ref).hex}",
            source_ref=source_ref,
            fragments=normalized,
            observed_at=utc_now_iso(),
            source_trace_id=source_trace_id,
        )

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> MemoryObservation:
        expected = {
            "id", "source_ref", "fragments", "observed_at", "status",
            "source_trace_id",
        }
        if set(data) != expected:
            raise ValueError("memory observation fields differ from schema")
        observation_id = data["id"]
        source_ref = data["source_ref"]
        raw_fragments = data["fragments"]
        observed_at = data["observed_at"]
        status = data["status"]
        source_trace_id = data["source_trace_id"]
        if not isinstance(observation_id, str) or not observation_id.startswith("obs_"):
            raise ValueError("memory observation id is invalid")
        if not isinstance(source_ref, str) or source_ref == "":
            raise ValueError("memory observation source_ref is invalid")
        if not isinstance(raw_fragments, list) or not raw_fragments:
            raise ValueError("memory observation fragments are invalid")
        fragments = cast(list[object], raw_fragments)
        if any(not isinstance(fragment, str) or fragment == "" for fragment in fragments):
            raise ValueError("memory observation fragment is invalid")
        if not isinstance(observed_at, str) or observed_at == "":
            raise ValueError("memory observation observed_at is invalid")
        if status not in {"pending", "processed"}:
            raise ValueError("memory observation status is invalid")
        if source_trace_id is not None and not isinstance(source_trace_id, str):
            raise ValueError("memory observation source_trace_id is invalid")
        return cls(
            id=observation_id,
            source_ref=source_ref,
            fragments=tuple(cast(list[str], fragments)),
            observed_at=observed_at,
            status=cast(ObservationStatus, status),
            source_trace_id=source_trace_id,
        )

    def to_wire(self) -> dict[str, object]:
        return {
            "id": self.id,
            "source_ref": self.source_ref,
            "fragments": list(self.fragments),
            "observed_at": self.observed_at,
            "status": self.status,
            "source_trace_id": self.source_trace_id,
        }


class MemoryObservationRepository:
    """Memory-owned durable inbox; producers can publish but never read it."""

    def __init__(self, backend: StorageBackend) -> None:
        self._backend = backend
        self._collection = backend.collection("memory_observations")

    def observe(self, observation: MemoryObservation) -> MemoryObservation:
        """Accept one producer-selected evidence batch idempotently."""
        with self._backend.transaction():
            existing = self._collection.get(observation.id)
            if existing is not None:
                decoded = MemoryObservation.from_wire(existing)
                if decoded.source_ref != observation.source_ref or decoded.fragments != observation.fragments:
                    raise ValueError("memory observation identity collision")
                return decoded
            self._collection.put(observation.id, observation.to_wire())
        return observation

    def get(self, observation_id: str) -> MemoryObservation:
        raw = self._collection.get(observation_id)
        if raw is None:
            raise KeyError(observation_id)
        return MemoryObservation.from_wire(raw)

    def pending(self) -> tuple[MemoryObservation, ...]:
        observations = (
            MemoryObservation.from_wire(raw)
            for raw in self._collection.find(status="pending")
        )
        return tuple(sorted(observations, key=lambda item: (item.observed_at, item.id)))

    def list(self) -> tuple[MemoryObservation, ...]:
        return tuple(
            MemoryObservation.from_wire(raw) for raw in self._collection.list()
        )

    def mark_processed(self, observation_id: str) -> None:
        with self._backend.transaction():
            observation = self.get(observation_id)
            self._collection.put(
                observation_id,
                replace(observation, status="processed").to_wire(),
            )
