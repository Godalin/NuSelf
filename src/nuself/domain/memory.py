"""Memory domain models and typed-memory descriptors."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol, TypeAlias, cast
from uuid import uuid4

MemoryEntryType: TypeAlias = Literal[
    "source_note",
    "profile_fact",
    "belief",
    "preference",
    "goal",
    "concept",
    "style_trait",
    "episode",
    "open_question",
    "instruction",
    "persona_instruction",
]

ReviewState: TypeAlias = Literal["draft", "reviewed", "rejected", "quarantined", "archived"]
PrivacyLevel: TypeAlias = Literal["private", "shareable"]
MemoryCandidateAction: TypeAlias = Literal["create", "update", "merge", "delete"]
MemoryCandidateReviewState: TypeAlias = Literal["pending", "accepted", "rejected"]
MemoryEvidenceSourceType: TypeAlias = Literal["thread", "manual", "source", "optimizer"]


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_memory_entry_id() -> str:
    return f"mem_{uuid4().hex}"


def new_memory_candidate_id() -> str:
    return f"cand_{uuid4().hex}"


def empty_str_list() -> list[str]:
    return []


def empty_object_dict() -> dict[str, object]:
    return {}


def empty_evidence_list() -> list["MemoryEvidence"]:
    return []


def empty_relations_dict() -> dict[str, list[str]]:
    return {}


def merge_relations(
    base: dict[str, list[str]], other: dict[str, list[str]]
) -> dict[str, list[str]]:
    """Merge two relations dicts, deduplicating target ids per relation."""
    merged = {k: list(v) for k, v in base.items()}
    for key, values in other.items():
        seen = set(merged.get(key, []))
        for value in values:
            if value not in seen:
                seen.add(value)
                merged.setdefault(key, []).append(value)
    return merged


def _migrate_legacy_relations(data: dict[str, object]) -> dict[str, list[str]]:
    """Backward-compat: read old supersedes/related_memory_ids into relations dict."""
    relations = _optional_relations_dict(data, "relations")
    if relations:
        return relations
    supersedes = _optional_str_list(data, "supersedes")
    related = _optional_str_list(data, "related_memory_ids")
    if supersedes:
        relations["supersedes"] = supersedes
    if related:
        relations["related_to"] = related
    return relations


@dataclass(frozen=True)
class MemoryEvidence:
    """Structured source evidence attached to a memory object."""

    source_type: MemoryEvidenceSourceType
    source_ref: str
    summary: str = ""
    observed_at: str | None = None
    quote: str = ""
    created_at: str = field(default_factory=now_iso)

    def to_wire(self) -> dict[str, object]:
        return {
            "source_type": self.source_type,
            "source_ref": self.source_ref,
            "summary": self.summary,
            "observed_at": self.observed_at,
            "quote": self.quote,
            "created_at": self.created_at,
        }

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> "MemoryEvidence":
        return cls(
            source_type=_expect_evidence_source_type(data, "source_type"),
            source_ref=_expect_str(data, "source_ref"),
            summary=_optional_str(data, "summary") or "",
            observed_at=_optional_str(data, "observed_at"),
            quote=_optional_str(data, "quote") or "",
            created_at=_expect_str(data, "created_at"),
        )


@dataclass(frozen=True)
class MemoryEntry:
    """Reviewed or draft memory that is visible to the user."""

    type: MemoryEntryType
    title: str
    body: str
    tags: list[str] = field(default_factory=empty_str_list)
    source_refs: list[str] = field(default_factory=empty_str_list)
    confidence: float = 1.0
    importance: float = 0.5
    privacy: PrivacyLevel = "private"
    review_state: ReviewState = "draft"
    id: str = field(default_factory=new_memory_entry_id)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    revisit_at: str | None = None
    observed_at: str | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    temporal_note: str = ""
    relations: dict[str, list[str]] = field(default_factory=empty_relations_dict)
    evidence: list[MemoryEvidence] = field(default_factory=empty_evidence_list)
    payload: dict[str, object] = field(default_factory=empty_object_dict)

    def with_updates(
        self,
        *,
        title: str | None = None,
        body: str | None = None,
        tags: list[str] | None = None,
        confidence: float | None = None,
        importance: float | None = None,
        review_state: ReviewState | None = None,
        observed_at: str | None = None,
        valid_from: str | None = None,
        valid_until: str | None = None,
        temporal_note: str | None = None,
    ) -> "MemoryEntry":
        return MemoryEntry(
            type=self.type,
            title=title if title is not None else self.title,
            body=body if body is not None else self.body,
            tags=tags if tags is not None else self.tags,
            source_refs=self.source_refs,
            confidence=confidence if confidence is not None else self.confidence,
            importance=importance if importance is not None else self.importance,
            privacy=self.privacy,
            review_state=review_state if review_state is not None else self.review_state,
            id=self.id,
            created_at=self.created_at,
            updated_at=now_iso(),
            revisit_at=self.revisit_at,
            observed_at=observed_at if observed_at is not None else self.observed_at,
            valid_from=valid_from if valid_from is not None else self.valid_from,
            valid_until=valid_until if valid_until is not None else self.valid_until,
            temporal_note=temporal_note if temporal_note is not None else self.temporal_note,
            relations=self.relations,
            evidence=self.evidence,
            payload=self.payload,
        )

    def to_wire(self) -> dict[str, object]:
        wire: dict[str, object] = {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "body": self.body,
            "tags": self.tags,
            "source_refs": self.source_refs,
            "confidence": self.confidence,
            "importance": self.importance,
            "privacy": self.privacy,
            "review_state": self.review_state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "revisit_at": self.revisit_at,
            "observed_at": self.observed_at,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "temporal_note": self.temporal_note,
            "relations": self.relations,
            "supersedes": self.relations.get("supersedes", []),
            "related_memory_ids": self.relations.get("related_to", []),
            "evidence": [evidence.to_wire() for evidence in self.evidence],
        }
        if self.payload:
            wire["payload"] = self.payload
        return wire

    def to_memory_object(self) -> "MemoryObject":
        """Return the open typed-memory envelope for this legacy entry."""

        payload: dict[str, object] = {
            "title": self.title,
            "body": self.body,
            "tags": self.tags,
            "revisit_at": self.revisit_at,
            "observed_at": self.observed_at,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "temporal_note": self.temporal_note,
            "relations": self.relations,
            "supersedes": self.relations.get("supersedes", []),
            "related_memory_ids": self.relations.get("related_to", []),
            "evidence": [evidence.to_wire() for evidence in self.evidence],
        }
        payload.update(self.payload)
        return MemoryObject(
            id=self.id,
            type=self.type,
            payload=payload,
            metadata={"entry_schema": "MemoryEntry/v1"},
            confidence=self.confidence,
            importance=self.importance,
            source_refs=self.source_refs,
            review_state=self.review_state,
            privacy=self.privacy,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> "MemoryEntry":
        return cls(
            id=_expect_str(data, "id"),
            type=_expect_memory_type(data, "type"),
            title=_expect_str(data, "title"),
            body=_expect_str(data, "body"),
            tags=_expect_str_list(data, "tags"),
            source_refs=_expect_str_list(data, "source_refs"),
            confidence=_expect_float(data, "confidence"),
            importance=_optional_float(data, "importance") or 0.5,
            privacy=_expect_privacy(data, "privacy"),
            review_state=_expect_review_state(data, "review_state"),
            created_at=_expect_str(data, "created_at"),
            updated_at=_expect_str(data, "updated_at"),
            revisit_at=_expect_optional_str(data, "revisit_at"),
            observed_at=_optional_str(data, "observed_at"),
            valid_from=_optional_str(data, "valid_from"),
            valid_until=_optional_str(data, "valid_until"),
            temporal_note=_optional_str(data, "temporal_note") or "",
            relations=_migrate_legacy_relations(data),
            evidence=_optional_evidence_list(data, "evidence"),
            payload=_optional_dict(data, "payload"),
        )

    @classmethod
    def from_memory_object(cls, memory: "MemoryObject") -> "MemoryEntry":
        payload = memory.payload
        relations = _optional_mapping_relations_dict(payload, "relations")
        if not relations:
            supersedes = _optional_mapping_str_list(payload, "supersedes")
            related = _optional_mapping_str_list(payload, "related_memory_ids")
            if supersedes:
                relations["supersedes"] = supersedes
            if related:
                relations["related_to"] = related
        known_fields = {
            "title", "body", "tags", "revisit_at", "observed_at",
            "valid_from", "valid_until", "temporal_note", "relations",
            "supersedes", "related_memory_ids", "evidence",
        }
        extra_payload = {k: v for k, v in payload.items() if k not in known_fields}
        return cls(
            id=memory.id,
            type=_memory_object_type_as_entry_type(memory.type),
            title=_expect_mapping_str(payload, "title"),
            body=_expect_mapping_str(payload, "body"),
            tags=_expect_mapping_str_list(payload, "tags"),
            source_refs=memory.source_refs,
            confidence=memory.confidence,
            importance=memory.importance,
            privacy=memory.privacy,
            review_state=memory.review_state,
            created_at=memory.created_at,
            updated_at=memory.updated_at,
            revisit_at=_expect_mapping_optional_str(payload, "revisit_at"),
            observed_at=_expect_mapping_optional_str(payload, "observed_at"),
            valid_from=_expect_mapping_optional_str(payload, "valid_from"),
            valid_until=_expect_mapping_optional_str(payload, "valid_until"),
            temporal_note=_optional_payload_str(payload, "temporal_note"),
            relations=relations,
            evidence=_optional_mapping_evidence_list(payload, "evidence"),
            payload=extra_payload,
        )


@dataclass(frozen=True)
class MemoryCandidate:
    """Proposed memory change awaiting review before durable persistence."""

    type: MemoryEntryType
    title: str
    body: str
    action: MemoryCandidateAction = "create"
    tags: list[str] = field(default_factory=empty_str_list)
    source_refs: list[str] = field(default_factory=empty_str_list)
    confidence: float = 0.7
    importance: float = 0.5
    privacy: PrivacyLevel = "private"
    review_state: MemoryCandidateReviewState = "pending"
    reason: str = ""
    id: str = field(default_factory=new_memory_candidate_id)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    reviewed_at: str | None = None
    target_entry_id: str | None = None
    observed_at: str | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    temporal_note: str = ""
    relations: dict[str, list[str]] = field(default_factory=empty_relations_dict)
    evidence: list[MemoryEvidence] = field(default_factory=empty_evidence_list)

    def with_updates(
        self,
        *,
        title: str | None = None,
        body: str | None = None,
        tags: list[str] | None = None,
        importance: float | None = None,
        review_state: MemoryCandidateReviewState | None = None,
        target_entry_id: str | None = None,
        observed_at: str | None = None,
        valid_from: str | None = None,
        valid_until: str | None = None,
        temporal_note: str | None = None,
    ) -> "MemoryCandidate":
        reviewed_at = now_iso() if review_state in {"accepted", "rejected"} else self.reviewed_at
        return MemoryCandidate(
            type=self.type,
            title=title if title is not None else self.title,
            body=body if body is not None else self.body,
            action=self.action,
            tags=tags if tags is not None else self.tags,
            source_refs=self.source_refs,
            confidence=self.confidence,
            importance=importance if importance is not None else self.importance,
            privacy=self.privacy,
            review_state=review_state if review_state is not None else self.review_state,
            reason=self.reason,
            id=self.id,
            created_at=self.created_at,
            updated_at=now_iso(),
            reviewed_at=reviewed_at,
            target_entry_id=target_entry_id if target_entry_id is not None else self.target_entry_id,
            observed_at=observed_at if observed_at is not None else self.observed_at,
            valid_from=valid_from if valid_from is not None else self.valid_from,
            valid_until=valid_until if valid_until is not None else self.valid_until,
            temporal_note=temporal_note if temporal_note is not None else self.temporal_note,
            relations=self.relations,
            evidence=self.evidence,
        )

    def to_entry(self, *, review_state: ReviewState = "draft") -> MemoryEntry:
        if self.action == "delete":
            raise ValueError("delete candidates cannot be converted to memory entries")
        return MemoryEntry(
            type=self.type,
            title=self.title,
            body=self.body,
            tags=self.tags,
            source_refs=self.source_refs,
            confidence=self.confidence,
            importance=self.importance,
            privacy=self.privacy,
            review_state=review_state,
            observed_at=self.observed_at,
            valid_from=self.valid_from,
            valid_until=self.valid_until,
            temporal_note=self.temporal_note,
            relations=self.relations,
            evidence=self.evidence,
        )

    def to_memory_object(self) -> MemoryObject:
        """Return the open typed-memory envelope for this candidate."""
        payload: dict[str, object] = {
            "title": self.title,
            "body": self.body,
            "tags": self.tags,
            "revisit_at": None,
            "observed_at": self.observed_at,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "temporal_note": self.temporal_note,
            "relations": self.relations,
            "supersedes": self.relations.get("supersedes", []),
            "related_memory_ids": self.relations.get("related_to", []),
            "evidence": [evidence.to_wire() for evidence in self.evidence],
        }
        return MemoryObject(
            id=self.id,
            type=self.type,
            payload=payload,
            metadata={"candidate_schema": "MemoryCandidate/v1"},
            confidence=self.confidence,
            importance=self.importance,
            source_refs=self.source_refs,
            review_state=cast(ReviewState, self.review_state),
            privacy=self.privacy,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    def to_wire(self) -> dict[str, object]:
        return {
            "id": self.id,
            "action": self.action,
            "type": self.type,
            "title": self.title,
            "body": self.body,
            "tags": self.tags,
            "source_refs": self.source_refs,
            "confidence": self.confidence,
            "importance": self.importance,
            "privacy": self.privacy,
            "review_state": self.review_state,
            "reason": self.reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "reviewed_at": self.reviewed_at,
            "target_entry_id": self.target_entry_id,
            "observed_at": self.observed_at,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "temporal_note": self.temporal_note,
            "relations": self.relations,
            "supersedes": self.relations.get("supersedes", []),
            "related_memory_ids": self.relations.get("related_to", []),
            "evidence": [evidence.to_wire() for evidence in self.evidence],
        }

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> "MemoryCandidate":
        return cls(
            id=_expect_str(data, "id"),
            action=_expect_candidate_action(data, "action"),
            type=_expect_memory_type(data, "type"),
            title=_expect_str(data, "title"),
            body=_expect_str(data, "body"),
            tags=_expect_str_list(data, "tags"),
            source_refs=_expect_str_list(data, "source_refs"),
            confidence=_expect_float(data, "confidence"),
            importance=_optional_float(data, "importance") or 0.5,
            privacy=_expect_privacy(data, "privacy"),
            review_state=_expect_candidate_review_state(data, "review_state"),
            reason=_optional_str(data, "reason") or "",
            created_at=_expect_str(data, "created_at"),
            updated_at=_expect_str(data, "updated_at"),
            reviewed_at=_optional_str(data, "reviewed_at"),
            target_entry_id=_optional_str(data, "target_entry_id"),
            observed_at=_optional_str(data, "observed_at"),
            valid_from=_optional_str(data, "valid_from"),
            valid_until=_optional_str(data, "valid_until"),
            temporal_note=_optional_str(data, "temporal_note") or "",
            relations=_migrate_legacy_relations(data),
            evidence=_optional_evidence_list(data, "evidence"),
        )


@dataclass(frozen=True)
class MemoryObject:
    """Open typed long-term memory envelope.

    The envelope is the forward-compatible storage boundary. Descriptors own
    payload validation and summaries for each registered memory type.
    """

    type: str
    payload: dict[str, object]
    metadata: dict[str, object] = field(default_factory=empty_object_dict)
    confidence: float = 1.0
    importance: float = 1.0
    source_refs: list[str] = field(default_factory=empty_str_list)
    review_state: ReviewState = "draft"
    privacy: PrivacyLevel = "private"
    id: str = field(default_factory=new_memory_entry_id)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_wire(self) -> dict[str, object]:
        return {
            "id": self.id,
            "type": self.type,
            "payload": self.payload,
            "metadata": self.metadata,
            "confidence": self.confidence,
            "importance": self.importance,
            "source_refs": self.source_refs,
            "review_state": self.review_state,
            "privacy": self.privacy,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> "MemoryObject":
        return cls(
            id=_expect_str(data, "id"),
            type=_expect_str(data, "type"),
            payload=_expect_dict(data, "payload"),
            metadata=_expect_dict(data, "metadata"),
            confidence=_expect_float(data, "confidence"),
            importance=_optional_float(data, "importance") or 1.0,
            source_refs=_expect_str_list(data, "source_refs"),
            review_state=_expect_review_state(data, "review_state"),
            privacy=_expect_privacy(data, "privacy"),
            created_at=_expect_str(data, "created_at"),
            updated_at=_expect_str(data, "updated_at"),
        )


@dataclass(frozen=True)
class MemoryValidationIssue:
    """One descriptor validation failure."""

    field: str
    message: str


class MemoryValidationError(ValueError):
    """Raised when a memory object fails descriptor validation."""

    def __init__(self, memory_type: str, issues: list[MemoryValidationIssue]) -> None:
        self.memory_type = memory_type
        self.issues = issues
        detail = "; ".join(f"{issue.field}: {issue.message}" for issue in issues)
        super().__init__(f"invalid {memory_type} memory: {detail}")


class MemoryTypeDescriptor(Protocol):
    """Behavior owned by one open memory type."""

    @property
    def type(self) -> str:
        raise NotImplementedError

    @property
    def description(self) -> str:
        raise NotImplementedError

    def validate(self, memory: MemoryObject) -> list[MemoryValidationIssue]:
        raise NotImplementedError

    def summarize(self, memory: MemoryObject) -> str:
        raise NotImplementedError

    def merge(self, existing: MemoryObject, incoming: MemoryObject) -> MemoryObject:
        """Return a merged memory object. By default, prefer incoming for title/body."""
        raise NotImplementedError

    def conflicts(self, a: MemoryObject, b: MemoryObject) -> bool:
        """Return True if two memories of this type conflict."""
        raise NotImplementedError

    def decay(self, memory: MemoryObject, now: str) -> MemoryObject | None:
        """Return updated memory after decay, or None if it should be removed."""
        raise NotImplementedError

    def retrieve(self, query: str, budget: int) -> bool:
        """Return True if this memory type is relevant to the query."""
        raise NotImplementedError

    def reflect(self, memory: MemoryObject, context: str) -> list[MemoryObject]:
        """Generate related memory candidates from reflection context."""
        raise NotImplementedError

    def example(self) -> MemoryObject:
        """Return a representative example of this memory type."""
        raise NotImplementedError

    def importance(self, memory: MemoryObject) -> float:
        """Return the importance score for this memory (0.0–1.0)."""
        raise NotImplementedError


class MemoryTypeRegistry:
    """Registry for typed memory behavior."""

    def __init__(self, descriptors: list[MemoryTypeDescriptor] | None = None) -> None:
        self._descriptors: dict[str, MemoryTypeDescriptor] = {}
        for descriptor in descriptors or []:
            self.register(descriptor)

    def register(self, descriptor: MemoryTypeDescriptor) -> None:
        self._descriptors[descriptor.type] = descriptor

    def get(self, memory_type: str) -> MemoryTypeDescriptor | None:
        return self._descriptors.get(memory_type)

    def validate(self, memory: MemoryObject) -> None:
        descriptor = self.get(memory.type)
        if descriptor is None:
            if memory.review_state != "draft":
                raise MemoryValidationError(
                    memory.type,
                    [MemoryValidationIssue("type", "unknown types must remain draft until a descriptor is available")],
                )
            return
        issues = descriptor.validate(memory)
        if issues:
            raise MemoryValidationError(memory.type, issues)

    def summarize(self, memory: MemoryObject) -> str:
        descriptor = self.get(memory.type)
        if descriptor is None:
            title = _optional_payload_str(memory.payload, "title")
            body = _optional_payload_str(memory.payload, "body")
            return title or body or f"{memory.type}:{memory.id}"
        return descriptor.summarize(memory)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._descriptors))

    def describe(self, memory_type: str) -> str:
        descriptor = self.get(memory_type)
        if descriptor is None:
            return "unknown type"
        return descriptor.description

    def merge(self, existing: MemoryObject, incoming: MemoryObject) -> MemoryObject:
        descriptor = self.get(existing.type)
        if descriptor is None:
            return _default_merge(existing, incoming)
        return descriptor.merge(existing, incoming)

    def conflicts(self, a: MemoryObject, b: MemoryObject) -> bool:
        descriptor = self.get(a.type)
        if descriptor is None:
            return _default_conflicts(a, b)
        return descriptor.conflicts(a, b)

    def decay(self, memory: MemoryObject, now: str) -> MemoryObject | None:
        descriptor = self.get(memory.type)
        if descriptor is None:
            return _default_decay(memory, now)
        return descriptor.decay(memory, now)

    def retrieve(self, memory_type: str, query: str, budget: int) -> bool:
        descriptor = self.get(memory_type)
        if descriptor is None:
            return _default_retrieve(query, budget)
        return descriptor.retrieve(query, budget)

    def reflect(self, memory: MemoryObject, context: str) -> list[MemoryObject]:
        descriptor = self.get(memory.type)
        if descriptor is None:
            return _default_reflect(memory, context)
        return descriptor.reflect(memory, context)

    def example(self, memory_type: str) -> MemoryObject | None:
        descriptor = self.get(memory_type)
        if descriptor is None:
            return None
        return descriptor.example()

    def importance(self, memory: MemoryObject) -> float:
        descriptor = self.get(memory.type)
        if descriptor is None:
            return _default_importance(memory)
        return descriptor.importance(memory)

    def __iter__(self):
        return iter(self._descriptors.values())


def _default_merge(existing: MemoryObject, incoming: MemoryObject) -> MemoryObject:
    """Default merge: preserve existing id/created_at, prefer incoming payload."""
    merged_payload = dict(existing.payload)
    merged_payload.update(incoming.payload)
    merged_metadata = dict(existing.metadata)
    merged_metadata.update(incoming.metadata)
    return MemoryObject(
        id=existing.id,
        type=existing.type,
        payload=merged_payload,
        metadata=merged_metadata,
        confidence=incoming.confidence,
        source_refs=list(dict.fromkeys(existing.source_refs + incoming.source_refs)),
        review_state=incoming.review_state,
        privacy=incoming.privacy,
        created_at=existing.created_at,
        updated_at=incoming.updated_at,
    )


def _default_conflicts(a: MemoryObject, b: MemoryObject) -> bool:
    """Default conflict: same id means same object, otherwise no conflict."""
    return a.id == b.id


def _default_decay(memory: MemoryObject, now: str) -> MemoryObject | None:
    """Default decay: no decay."""
    return memory


def _default_retrieve(query: str, budget: int) -> bool:
    """Default retrieval: always relevant."""
    return True


def _default_reflect(memory: MemoryObject, context: str) -> list[MemoryObject]:
    """Default reflection: no candidates."""
    return []


def _default_importance(memory: MemoryObject) -> float:
    """Default importance: use the stored importance or fall back to 0.5."""
    return memory.importance


@dataclass(frozen=True)
class RelationDescriptor:
    """Behavior metadata for one open symbolic relation."""

    name: str
    description: str
    source_field: str
    domain: tuple[str, ...] = ()
    range: tuple[str, ...] = ()
    symmetric: bool = False
    transitive: bool = False
    inverse: str | None = None
    temporal_policy: str = "inherits_source"
    confidence_policy: str = "inherits_source"
    retrieval_rule: str = "include_direct_neighbors"


class RelationDescriptorRegistry:
    """Registry for symbolic relation behavior."""

    def __init__(self, descriptors: list[RelationDescriptor] | None = None) -> None:
        self._descriptors: dict[str, RelationDescriptor] = {}
        for descriptor in descriptors or []:
            self.register(descriptor)

    def register(self, descriptor: RelationDescriptor) -> None:
        self._descriptors[descriptor.name] = descriptor

    def get(self, name: str) -> RelationDescriptor | None:
        return self._descriptors.get(name)

    def require(self, name: str) -> RelationDescriptor:
        descriptor = self.get(name)
        if descriptor is None:
            raise KeyError(f"unknown relation descriptor: {name}")
        return descriptor

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._descriptors))

    def __iter__(self):
        return iter(self._descriptors.values())


@dataclass(frozen=True)
class EntryPayloadDescriptor:
    """Descriptor for memory objects backed by a title/body entry payload."""

    type: str
    description: str
    default_importance: float = 0.5

    def validate(self, memory: MemoryObject) -> list[MemoryValidationIssue]:
        issues = _validate_entry_payload(memory.payload)
        confidence = memory.confidence
        if confidence < 0.0 or confidence > 1.0:
            issues.append(MemoryValidationIssue("confidence", "must be between 0 and 1"))
        return issues

    def summarize(self, memory: MemoryObject) -> str:
        title = _expect_mapping_str(memory.payload, "title")
        body = _expect_mapping_str(memory.payload, "body")
        return f"{title}: {body}"

    def merge(self, existing: MemoryObject, incoming: MemoryObject) -> MemoryObject:
        existing_tags = cast(list[str], existing.payload.get("tags", []))
        incoming_tags = cast(list[str], incoming.payload.get("tags", []))
        merged_tags = list(dict.fromkeys(existing_tags + incoming_tags))
        merged_payload = dict(existing.payload)
        merged_payload.update(incoming.payload)
        merged_payload["tags"] = merged_tags
        merged_metadata = dict(existing.metadata)
        merged_metadata.update(incoming.metadata)
        return MemoryObject(
            id=existing.id,
            type=existing.type,
            payload=merged_payload,
            metadata=merged_metadata,
            confidence=incoming.confidence,
            source_refs=list(dict.fromkeys(existing.source_refs + incoming.source_refs)),
            review_state=incoming.review_state,
            privacy=incoming.privacy,
            created_at=existing.created_at,
            updated_at=incoming.updated_at,
        )

    def conflicts(self, a: MemoryObject, b: MemoryObject) -> bool:
        a_title = _optional_payload_str(a.payload, "title")
        b_title = _optional_payload_str(b.payload, "title")
        if a_title and b_title and a_title.strip().lower() == b_title.strip().lower():
            return True
        return a.id == b.id

    def decay(self, memory: MemoryObject, now: str) -> MemoryObject | None:
        return memory

    def retrieve(self, query: str, budget: int) -> bool:
        return True

    def reflect(self, memory: MemoryObject, context: str) -> list[MemoryObject]:
        return []

    def example(self) -> MemoryObject:
        return MemoryObject(
            type=self.type,
            payload={"title": f"Example {self.type}", "body": self.description, "tags": []},
        )

    def importance(self, memory: MemoryObject) -> float:
        if memory.importance == 1.0:
            return self.default_importance
        return memory.importance


@dataclass(frozen=True)
class PersonaInstructionDescriptor:
    """Descriptor for persona instruction memory objects."""

    default_importance: float = 0.9

    @property
    def type(self) -> str:
        return "persona_instruction"

    @property
    def description(self) -> str:
        return "persona instruction memory"

    def validate(self, memory: MemoryObject) -> list[MemoryValidationIssue]:
        issues: list[MemoryValidationIssue] = []
        payload = memory.payload
        persona_id = payload.get("persona_id")
        if not isinstance(persona_id, str) or persona_id.strip() == "":
            issues.append(MemoryValidationIssue("payload.persona_id", "must be a non-empty string"))
        description = payload.get("description")
        if not isinstance(description, str) or description.strip() == "":
            issues.append(MemoryValidationIssue("payload.description", "must be a non-empty string"))
        routing_markers = payload.get("routing_markers")
        if routing_markers is not None:
            if not isinstance(routing_markers, list) or any(not isinstance(item, str) for item in cast(list[object], routing_markers)):
                issues.append(MemoryValidationIssue("payload.routing_markers", "must be a list of strings"))
        behavioral_notes = payload.get("behavioral_notes")
        if behavioral_notes is not None and not isinstance(behavioral_notes, str):
            issues.append(MemoryValidationIssue("payload.behavioral_notes", "must be a string"))
        confidence = memory.confidence
        if confidence < 0.0 or confidence > 1.0:
            issues.append(MemoryValidationIssue("confidence", "must be between 0 and 1"))
        return issues

    def summarize(self, memory: MemoryObject) -> str:
        persona_id = memory.payload.get("persona_id", "")
        description = memory.payload.get("description", "")
        return f"{persona_id}: {description}"

    def merge(self, existing: MemoryObject, incoming: MemoryObject) -> MemoryObject:
        merged_payload = dict(existing.payload)
        merged_payload.update(incoming.payload)
        merged_metadata = dict(existing.metadata)
        merged_metadata.update(incoming.metadata)
        return MemoryObject(
            id=existing.id,
            type=existing.type,
            payload=merged_payload,
            metadata=merged_metadata,
            confidence=incoming.confidence,
            source_refs=list(dict.fromkeys(existing.source_refs + incoming.source_refs)),
            review_state=incoming.review_state,
            privacy=incoming.privacy,
            created_at=existing.created_at,
            updated_at=incoming.updated_at,
        )

    def conflicts(self, a: MemoryObject, b: MemoryObject) -> bool:
        a_id = _optional_payload_str(a.payload, "persona_id")
        b_id = _optional_payload_str(b.payload, "persona_id")
        if a_id and b_id and a_id.strip().lower() == b_id.strip().lower():
            return True
        return a.id == b.id

    def decay(self, memory: MemoryObject, now: str) -> MemoryObject | None:
        return memory

    def retrieve(self, query: str, budget: int) -> bool:
        return True

    def reflect(self, memory: MemoryObject, context: str) -> list[MemoryObject]:
        return []

    def example(self) -> MemoryObject:
        return MemoryObject(
            type=self.type,
            payload={"persona_id": "analyst", "description": "Decomposes concepts and assumptions."},
        )

    def importance(self, memory: MemoryObject) -> float:
        if memory.importance == 1.0:
            return self.default_importance
        return memory.importance


def default_memory_type_registry() -> MemoryTypeRegistry:
    """Return built-in descriptors for the current typed-memory foundation."""

    return MemoryTypeRegistry(
        [
            EntryPayloadDescriptor("source_note", "a source-backed note", default_importance=0.4),
            EntryPayloadDescriptor("profile_fact", "a profile fact", default_importance=0.9),
            EntryPayloadDescriptor("belief", "a claim or stance", default_importance=0.7),
            EntryPayloadDescriptor("preference", "a durable preference", default_importance=0.6),
            EntryPayloadDescriptor("goal", "a desired future state", default_importance=0.8),
            EntryPayloadDescriptor("concept", "a concept definition or explanation", default_importance=0.5),
            EntryPayloadDescriptor("style_trait", "a user style trait", default_importance=0.5),
            EntryPayloadDescriptor("episode", "a concise event summary", default_importance=0.4),
            EntryPayloadDescriptor("open_question", "an unresolved question", default_importance=0.3),
            EntryPayloadDescriptor("instruction", "a behavior rule", default_importance=0.6),
            PersonaInstructionDescriptor(),
        ]
    )


def default_relation_descriptor_registry() -> RelationDescriptorRegistry:
    """Return built-in descriptors for current memory-link relations."""

    memory_node_types = (
        "source_note",
        "profile_fact",
        "belief",
        "preference",
        "goal",
        "concept",
        "style_trait",
        "episode",
        "open_question",
        "instruction",
    )
    return RelationDescriptorRegistry(
        [
            RelationDescriptor(
                name="supersedes",
                description="The source memory replaces or revises the target memory.",
                source_field="supersedes",
                domain=memory_node_types,
                range=memory_node_types,
                inverse="superseded_by",
                temporal_policy="source_validity_refines_target",
                confidence_policy="inherits_source",
                retrieval_rule="include_both_current_and_superseded",
            ),
            RelationDescriptor(
                name="related_to",
                description="The source memory is intentionally linked to the target memory.",
                source_field="related_to",
                domain=memory_node_types,
                range=memory_node_types,
                symmetric=True,
                inverse="related_to",
                temporal_policy="independent",
                confidence_policy="inherits_source",
                retrieval_rule="include_direct_neighbors",
            ),
            RelationDescriptor(
                name="supports",
                description="The source memory provides evidence or backing for the target memory.",
                source_field="supports",
                domain=memory_node_types,
                range=memory_node_types,
                inverse="supported_by",
                temporal_policy="independent",
                confidence_policy="inherits_source",
                retrieval_rule="include_direct_neighbors",
            ),
            RelationDescriptor(
                name="contradicts",
                description="The source memory opposes or conflicts with the target memory.",
                source_field="contradicts",
                domain=memory_node_types,
                range=memory_node_types,
                inverse="contradicted_by",
                temporal_policy="independent",
                confidence_policy="inherits_source",
                retrieval_rule="include_direct_neighbors",
            ),
            RelationDescriptor(
                name="refines",
                description="The source memory improves, clarifies, or narrows the target memory.",
                source_field="refines",
                domain=memory_node_types,
                range=memory_node_types,
                inverse="refined_by",
                temporal_policy="source_validity_refines_target",
                confidence_policy="inherits_source",
                retrieval_rule="include_direct_neighbors",
            ),
            RelationDescriptor(
                name="depends_on",
                description="The source memory requires or depends on the target memory.",
                source_field="depends_on",
                domain=memory_node_types,
                range=memory_node_types,
                transitive=True,
                inverse="required_by",
                temporal_policy="independent",
                confidence_policy="inherits_source",
                retrieval_rule="include_direct_neighbors",
            ),
        ]
    )


def _expect_str(data: dict[str, object], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str):
        raise ValueError(f"field '{field_name}' must be a string")
    return value


def _expect_optional_str(data: dict[str, object], field_name: str) -> str | None:
    value = data.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"field '{field_name}' must be a string or null")
    return value


def _optional_str(data: dict[str, object], field_name: str) -> str | None:
    value = data.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"field '{field_name}' must be a string or null")
    return value


def _optional_float(data: dict[str, object], field_name: str) -> float | None:
    value = data.get(field_name)
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    raise ValueError(f"field '{field_name}' must be a number or null")


def _optional_dict(data: dict[str, object], field_name: str) -> dict[str, object]:
    value = data.get(field_name)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"field '{field_name}' must be an object or null")
    return cast(dict[str, object], value)


def _expect_float(data: dict[str, object], field_name: str) -> float:
    value = data.get(field_name)
    if isinstance(value, int | float):
        return float(value)
    raise ValueError(f"field '{field_name}' must be a number")


def _expect_dict(data: dict[str, object], field_name: str) -> dict[str, object]:
    value = data.get(field_name)
    if not isinstance(value, dict):
        raise ValueError(f"field '{field_name}' must be an object")
    return cast(dict[str, object], value)


def _expect_str_list(data: dict[str, object], field_name: str) -> list[str]:
    value = data.get(field_name)
    if not isinstance(value, list):
        raise ValueError(f"field '{field_name}' must be a list")
    result: list[str] = []
    for item in cast(list[object], value):
        if not isinstance(item, str):
            raise ValueError(f"field '{field_name}' must contain only strings")
        result.append(item)
    return result


def _optional_str_list(data: dict[str, object], field_name: str) -> list[str]:
    value = data.get(field_name)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"field '{field_name}' must be a list")
    result: list[str] = []
    for item in cast(list[object], value):
        if not isinstance(item, str):
            raise ValueError(f"field '{field_name}' must contain only strings")
        result.append(item)
    return result


def _expect_memory_type(data: dict[str, object], field_name: str) -> MemoryEntryType:
    value = _expect_str(data, field_name)
    return cast(MemoryEntryType, value)


def _memory_object_type_as_entry_type(value: str) -> MemoryEntryType:
    if value not in {
        "source_note",
        "profile_fact",
        "belief",
        "preference",
        "goal",
        "concept",
        "style_trait",
        "episode",
        "open_question",
        "instruction",
        "persona_instruction",
    }:
        raise ValueError(f"unsupported memory entry type: {value}")
    return cast(MemoryEntryType, value)


def _expect_review_state(data: dict[str, object], field_name: str) -> ReviewState:
    value = _expect_str(data, field_name)
    if value not in {"draft", "reviewed", "rejected", "quarantined", "archived"}:
        raise ValueError(f"unsupported review state: {value}")
    return cast(ReviewState, value)


def _expect_candidate_action(data: dict[str, object], field_name: str) -> MemoryCandidateAction:
    value = _expect_str(data, field_name)
    if value not in {"create", "update", "merge", "delete"}:
        raise ValueError(f"unsupported candidate action: {value}")
    return cast(MemoryCandidateAction, value)


def _expect_candidate_review_state(data: dict[str, object], field_name: str) -> MemoryCandidateReviewState:
    value = _expect_str(data, field_name)
    if value not in {"pending", "accepted", "rejected"}:
        raise ValueError(f"unsupported candidate review state: {value}")
    return cast(MemoryCandidateReviewState, value)


def _expect_evidence_source_type(data: dict[str, object], field_name: str) -> MemoryEvidenceSourceType:
    value = _expect_str(data, field_name)
    if value not in {"thread", "manual", "source", "optimizer"}:
        raise ValueError(f"unsupported evidence source type: {value}")
    return cast(MemoryEvidenceSourceType, value)


def _expect_privacy(data: dict[str, object], field_name: str) -> PrivacyLevel:
    value = _expect_str(data, field_name)
    if value not in {"private", "shareable"}:
        raise ValueError(f"unsupported privacy level: {value}")
    return cast(PrivacyLevel, value)


def _validate_entry_payload(payload: Mapping[str, object]) -> list[MemoryValidationIssue]:
    issues: list[MemoryValidationIssue] = []
    title = payload.get("title")
    if not isinstance(title, str) or title.strip() == "":
        issues.append(MemoryValidationIssue("payload.title", "must be a non-empty string"))
    body = payload.get("body")
    if not isinstance(body, str) or body.strip() == "":
        issues.append(MemoryValidationIssue("payload.body", "must be a non-empty string"))
    tags = payload.get("tags", [])
    if not isinstance(tags, list) or any(not isinstance(item, str) for item in cast(list[object], tags)):
        issues.append(MemoryValidationIssue("payload.tags", "must be a list of strings"))
    revisit_at = payload.get("revisit_at")
    if revisit_at is not None and not isinstance(revisit_at, str):
        issues.append(MemoryValidationIssue("payload.revisit_at", "must be a string or null"))
    for field_name in ["observed_at", "valid_from", "valid_until", "temporal_note"]:
        value = payload.get(field_name)
        if value is not None and not isinstance(value, str):
            issues.append(MemoryValidationIssue(f"payload.{field_name}", "must be a string or null"))
    relations = payload.get("relations", {})
    if not isinstance(relations, dict):
        issues.append(MemoryValidationIssue("payload.relations", "must be an object"))
    else:
        for key, value in cast(dict[str, object], relations).items():
            if not isinstance(value, list) or any(not isinstance(item, str) for item in cast(list[object], value)):
                issues.append(MemoryValidationIssue(f"payload.relations.{key}", "must be a list of strings"))
    for field_name in ["supersedes", "related_memory_ids"]:
        value = payload.get(field_name, [])
        if not isinstance(value, list) or any(not isinstance(item, str) for item in cast(list[object], value)):
            issues.append(MemoryValidationIssue(f"payload.{field_name}", "must be a list of strings"))
    evidence = payload.get("evidence", [])
    if not isinstance(evidence, list):
        issues.append(MemoryValidationIssue("payload.evidence", "must be a list"))
    return issues


def _expect_mapping_str(data: Mapping[str, object], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str):
        raise ValueError(f"field '{field_name}' must be a string")
    return value


def _expect_mapping_optional_str(data: Mapping[str, object], field_name: str) -> str | None:
    value = data.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"field '{field_name}' must be a string or null")
    return value


def _expect_mapping_str_list(data: Mapping[str, object], field_name: str) -> list[str]:
    value = data.get(field_name)
    if not isinstance(value, list):
        raise ValueError(f"field '{field_name}' must be a list")
    result: list[str] = []
    for item in cast(list[object], value):
        if not isinstance(item, str):
            raise ValueError(f"field '{field_name}' must contain only strings")
        result.append(item)
    return result


def _optional_mapping_str_list(data: Mapping[str, object], field_name: str) -> list[str]:
    value = data.get(field_name)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"field '{field_name}' must be a list")
    result: list[str] = []
    for item in cast(list[object], value):
        if not isinstance(item, str):
            raise ValueError(f"field '{field_name}' must contain only strings")
        result.append(item)
    return result


def _optional_evidence_list(data: dict[str, object], field_name: str) -> list[MemoryEvidence]:
    value = data.get(field_name)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"field '{field_name}' must be a list")
    result: list[MemoryEvidence] = []
    for item in cast(list[object], value):
        if not isinstance(item, dict):
            raise ValueError(f"field '{field_name}' must contain only objects")
        result.append(MemoryEvidence.from_wire(cast(dict[str, object], item)))
    return result


def _optional_mapping_evidence_list(data: Mapping[str, object], field_name: str) -> list[MemoryEvidence]:
    value = data.get(field_name)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"field '{field_name}' must be a list")
    result: list[MemoryEvidence] = []
    for item in cast(list[object], value):
        if not isinstance(item, dict):
            raise ValueError(f"field '{field_name}' must contain only objects")
        result.append(MemoryEvidence.from_wire(cast(dict[str, object], item)))
    return result


def _optional_relations_dict(data: dict[str, object], field_name: str) -> dict[str, list[str]]:
    value = data.get(field_name)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"field '{field_name}' must be an object or null")
    result: dict[str, list[str]] = {}
    for k, v in cast(dict[str, object], value).items():
        if not isinstance(v, list):
            raise ValueError(f"field '{field_name}.{k}' must be a list")
        result[k] = []
        for item in cast(list[object], v):
            if not isinstance(item, str):
                raise ValueError(f"field '{field_name}.{k}' must contain only strings")
            result[k].append(item)
    return result


def _optional_mapping_relations_dict(data: Mapping[str, object], field_name: str) -> dict[str, list[str]]:
    value = data.get(field_name)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"field '{field_name}' must be an object or null")
    result: dict[str, list[str]] = {}
    for k, v in cast(dict[str, object], value).items():
        if not isinstance(v, list):
            raise ValueError(f"field '{field_name}.{k}' must be a list")
        result[k] = []
        for item in cast(list[object], v):
            if not isinstance(item, str):
                raise ValueError(f"field '{field_name}.{k}' must contain only strings")
            result[k].append(item)
    return result


def _optional_payload_str(data: Mapping[str, object], field_name: str) -> str:
    value = data.get(field_name)
    return value if isinstance(value, str) else ""
