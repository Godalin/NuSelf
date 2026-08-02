"""Validated administration API for user-visible domain records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from nuself.conversation import ConversationState, ConversationStore
from nuself.memory.model import MemoryEntry
from nuself.memory.repository import MemoryEntryRepository
from nuself.storage import COLLECTION_NAMES, StorageBackend

Record = dict[str, object]
Decoder = Callable[[Record], object]


@dataclass(frozen=True)
class DataResource:
    name: str
    collection: str
    editable: bool = False
    internal: bool = False


_RESOURCES = (
    DataResource("memory", "memory_entries", editable=True),
    DataResource("candidates", "memory_candidates"),
    DataResource("conversations", "conversations", editable=True),
    DataResource("profile", "profile_items"),
    DataResource("sources", "source_documents"),
    DataResource("source-chunks", "source_chunks"),
    DataResource("persona", "persona_prompts"),
    DataResource("reason-threads", "reason_threads"),
    DataResource("reason-steps", "reason_steps"),
    DataResource("traces", "trace_nodes"),
    DataResource("trace-edges", "trace_edges"),
    DataResource("notifications", "notification_outbox"),
    DataResource("reflections", "reflection_entries"),
    DataResource("memory_observations", "memory_observations", internal=True),
    DataResource("memory_curator_plans", "memory_curator_plans", internal=True),
    DataResource("scheduler_state", "scheduler_state", internal=True),
)


class DataAdminService:
    """One explicit boundary for generic inspection and limited repair."""

    def __init__(
        self,
        backend: StorageBackend,
        *,
        conversations: ConversationStore,
        memories: MemoryEntryRepository,
    ) -> None:
        self._backend = backend
        self._conversations = conversations
        self._memories = memories
        if {item.collection for item in _RESOURCES} != set(COLLECTION_NAMES):
            raise RuntimeError("data admin resources differ from storage schema")

    def resources(self, *, include_internal: bool = False) -> tuple[DataResource, ...]:
        return tuple(
            item for item in _RESOURCES if include_internal or not item.internal
        )

    def resolve(self, name: str, *, internal: bool = False) -> DataResource:
        resource = next(
            (
                item
                for item in _RESOURCES
                if name == item.name or name == item.collection
            ),
            None,
        )
        if resource is None:
            raise ValueError(f"unknown data resource: {name}")
        if resource.internal and not internal:
            raise ValueError(f"internal resource requires --internal: {name}")
        return resource

    def list(self, resource: DataResource) -> tuple[Record, ...]:
        return self._backend.collection(resource.collection).list()

    def get(self, resource: DataResource, record_id: str) -> Record | None:
        return self._backend.collection(resource.collection).get(record_id)

    def validate(self, resource: DataResource, record: Record) -> None:
        self._decoder(resource)(record)

    def update(
        self,
        resource: DataResource,
        record_id: str,
        record: Record,
    ) -> None:
        identity = record.get("id", record.get("conversation_id"))
        if identity != record_id:
            raise ValueError("data update cannot change stable identity")
        decoded = self._decoder(resource)(record)
        if resource.collection == "memory_entries":
            assert isinstance(decoded, MemoryEntry)
            self._memories.save(decoded)
            return
        assert isinstance(decoded, ConversationState)
        self._conversations.save(decoded)

    def delete(self, resource: DataResource, record_id: str) -> None:
        if not resource.editable:
            raise ValueError(f"data resource is read-only: {resource.name}")
        if resource.collection == "memory_entries":
            self._memories.delete(record_id)
            return
        self._conversations.delete(record_id)

    @staticmethod
    def _decoder(resource: DataResource) -> Decoder:
        if not resource.editable:
            raise ValueError(
                f"data resource has no generic validation contract: {resource.name}"
            )
        if resource.collection == "memory_entries":
            return MemoryEntry.from_wire
        return ConversationState.from_wire
