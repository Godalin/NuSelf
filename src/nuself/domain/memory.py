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
    "style_trait",
    "episode",
    "open_question",
    "instruction",
]

ReviewState: TypeAlias = Literal["draft", "reviewed", "rejected"]
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
    supersedes: list[str] = field(default_factory=empty_str_list)
    related_memory_ids: list[str] = field(default_factory=empty_str_list)
    evidence: list[MemoryEvidence] = field(default_factory=empty_evidence_list)

    def with_updates(
        self,
        *,
        title: str | None = None,
        body: str | None = None,
        tags: list[str] | None = None,
        confidence: float | None = None,
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
            supersedes=self.supersedes,
            related_memory_ids=self.related_memory_ids,
            evidence=self.evidence,
        )

    def to_wire(self) -> dict[str, object]:
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "body": self.body,
            "tags": self.tags,
            "source_refs": self.source_refs,
            "confidence": self.confidence,
            "privacy": self.privacy,
            "review_state": self.review_state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "revisit_at": self.revisit_at,
            "observed_at": self.observed_at,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "temporal_note": self.temporal_note,
            "supersedes": self.supersedes,
            "related_memory_ids": self.related_memory_ids,
            "evidence": [evidence.to_wire() for evidence in self.evidence],
        }

    def to_memory_object(self) -> "MemoryObject":
        """Return the open typed-memory envelope for this legacy entry."""

        return MemoryObject(
            id=self.id,
            type=self.type,
            payload={
                "title": self.title,
                "body": self.body,
                "tags": self.tags,
                "revisit_at": self.revisit_at,
                "observed_at": self.observed_at,
                "valid_from": self.valid_from,
                "valid_until": self.valid_until,
                "temporal_note": self.temporal_note,
                "supersedes": self.supersedes,
                "related_memory_ids": self.related_memory_ids,
                "evidence": [evidence.to_wire() for evidence in self.evidence],
            },
            metadata={"entry_schema": "MemoryEntry/v1"},
            confidence=self.confidence,
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
            privacy=_expect_privacy(data, "privacy"),
            review_state=_expect_review_state(data, "review_state"),
            created_at=_expect_str(data, "created_at"),
            updated_at=_expect_str(data, "updated_at"),
            revisit_at=_expect_optional_str(data, "revisit_at"),
            observed_at=_optional_str(data, "observed_at"),
            valid_from=_optional_str(data, "valid_from"),
            valid_until=_optional_str(data, "valid_until"),
            temporal_note=_optional_str(data, "temporal_note") or "",
            supersedes=_optional_str_list(data, "supersedes"),
            related_memory_ids=_optional_str_list(data, "related_memory_ids"),
            evidence=_optional_evidence_list(data, "evidence"),
        )

    @classmethod
    def from_memory_object(cls, memory: "MemoryObject") -> "MemoryEntry":
        payload = memory.payload
        return cls(
            id=memory.id,
            type=_memory_object_type_as_entry_type(memory.type),
            title=_expect_mapping_str(payload, "title"),
            body=_expect_mapping_str(payload, "body"),
            tags=_expect_mapping_str_list(payload, "tags"),
            source_refs=memory.source_refs,
            confidence=memory.confidence,
            privacy=memory.privacy,
            review_state=memory.review_state,
            created_at=memory.created_at,
            updated_at=memory.updated_at,
            revisit_at=_expect_mapping_optional_str(payload, "revisit_at"),
            observed_at=_expect_mapping_optional_str(payload, "observed_at"),
            valid_from=_expect_mapping_optional_str(payload, "valid_from"),
            valid_until=_expect_mapping_optional_str(payload, "valid_until"),
            temporal_note=_optional_payload_str(payload, "temporal_note"),
            supersedes=_optional_mapping_str_list(payload, "supersedes"),
            related_memory_ids=_optional_mapping_str_list(payload, "related_memory_ids"),
            evidence=_optional_mapping_evidence_list(payload, "evidence"),
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
    supersedes: list[str] = field(default_factory=empty_str_list)
    related_memory_ids: list[str] = field(default_factory=empty_str_list)
    evidence: list[MemoryEvidence] = field(default_factory=empty_evidence_list)

    def with_updates(
        self,
        *,
        title: str | None = None,
        body: str | None = None,
        tags: list[str] | None = None,
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
            supersedes=self.supersedes,
            related_memory_ids=self.related_memory_ids,
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
            privacy=self.privacy,
            review_state=review_state,
            observed_at=self.observed_at,
            valid_from=self.valid_from,
            valid_until=self.valid_until,
            temporal_note=self.temporal_note,
            supersedes=self.supersedes,
            related_memory_ids=self.related_memory_ids,
            evidence=self.evidence,
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
            "supersedes": self.supersedes,
            "related_memory_ids": self.related_memory_ids,
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
            supersedes=_optional_str_list(data, "supersedes"),
            related_memory_ids=_optional_str_list(data, "related_memory_ids"),
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

    def validate(self, memory: MemoryObject) -> list[MemoryValidationIssue]:
        raise NotImplementedError

    def summarize(self, memory: MemoryObject) -> str:
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


@dataclass(frozen=True)
class EntryPayloadDescriptor:
    """Descriptor for memory objects backed by a title/body entry payload."""

    type: str
    required_body_hint: str

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


def default_memory_type_registry() -> MemoryTypeRegistry:
    """Return built-in descriptors for the current typed-memory foundation."""

    return MemoryTypeRegistry(
        [
            EntryPayloadDescriptor("source_note", "a source-backed note"),
            EntryPayloadDescriptor("profile_fact", "a profile fact"),
            EntryPayloadDescriptor("belief", "a claim or stance"),
            EntryPayloadDescriptor("preference", "a durable preference"),
            EntryPayloadDescriptor("style_trait", "a user style trait"),
            EntryPayloadDescriptor("episode", "a concise event summary"),
            EntryPayloadDescriptor("open_question", "an unresolved question"),
            EntryPayloadDescriptor("instruction", "a behavior rule"),
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
    if value not in {
        "source_note",
        "profile_fact",
        "belief",
        "preference",
        "style_trait",
        "episode",
        "open_question",
        "instruction",
    }:
        raise ValueError(f"unsupported memory entry type: {value}")
    return cast(MemoryEntryType, value)


def _memory_object_type_as_entry_type(value: str) -> MemoryEntryType:
    if value not in {
        "source_note",
        "profile_fact",
        "belief",
        "preference",
        "style_trait",
        "episode",
        "open_question",
        "instruction",
    }:
        raise ValueError(f"unsupported memory entry type: {value}")
    return cast(MemoryEntryType, value)


def _expect_review_state(data: dict[str, object], field_name: str) -> ReviewState:
    value = _expect_str(data, field_name)
    if value not in {"draft", "reviewed", "rejected"}:
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


def _optional_payload_str(data: Mapping[str, object], field_name: str) -> str:
    value = data.get(field_name)
    return value if isinstance(value, str) else ""
