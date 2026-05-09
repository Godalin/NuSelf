"""Derived profile domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast
from uuid import NAMESPACE_URL, uuid5

from nuself.domain.memory import (
    MemoryCandidate,
    MemoryEvidence,
    PrivacyLevel,
    empty_evidence_list,
    empty_relations_dict,
    now_iso,
)


def empty_str_list() -> list[str]:
    return []


def _optional_float(data: dict[str, object], field_name: str) -> float | None:
    value = data.get(field_name)
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    raise ValueError(f"field '{field_name}' must be a number or null")


def new_profile_item_id(source_ref: str | None = None) -> str:
    if source_ref is None:
        return f"profile_{uuid5(NAMESPACE_URL, now_iso()).hex}"
    return f"profile_{uuid5(NAMESPACE_URL, source_ref).hex}"


@dataclass(frozen=True)
class ProfileItem:
    """Durable derived profile state."""

    type: str
    title: str
    body: str
    tags: list[str] = field(default_factory=empty_str_list)
    source_refs: list[str] = field(default_factory=empty_str_list)
    confidence: float = 1.0
    importance: float = 0.5
    privacy: PrivacyLevel = "private"
    id: str = field(default_factory=new_profile_item_id)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
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
        confidence: float | None = None,
        importance: float | None = None,
        observed_at: str | None = None,
        valid_from: str | None = None,
        valid_until: str | None = None,
        temporal_note: str | None = None,
    ) -> "ProfileItem":
        return ProfileItem(
            type=self.type,
            title=title if title is not None else self.title,
            body=body if body is not None else self.body,
            tags=tags if tags is not None else self.tags,
            source_refs=self.source_refs,
            confidence=confidence if confidence is not None else self.confidence,
            importance=importance if importance is not None else self.importance,
            privacy=self.privacy,
            id=self.id,
            created_at=self.created_at,
            updated_at=now_iso(),
            observed_at=observed_at if observed_at is not None else self.observed_at,
            valid_from=valid_from if valid_from is not None else self.valid_from,
            valid_until=valid_until if valid_until is not None else self.valid_until,
            temporal_note=temporal_note if temporal_note is not None else self.temporal_note,
            relations=self.relations,
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
            "importance": self.importance,
            "privacy": self.privacy,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
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
    def from_wire(cls, data: dict[str, object]) -> "ProfileItem":
        relations = _optional_relations_dict(data, "relations")
        if not relations:
            supersedes = _optional_str_list(data, "supersedes")
            related = _optional_str_list(data, "related_memory_ids")
            if supersedes:
                relations["supersedes"] = supersedes
            if related:
                relations["related_to"] = related
        return cls(
            id=_expect_str(data, "id"),
            type=_expect_str(data, "type"),
            title=_expect_str(data, "title"),
            body=_expect_str(data, "body"),
            tags=_expect_str_list(data, "tags"),
            source_refs=_expect_str_list(data, "source_refs"),
            confidence=_expect_float(data, "confidence"),
            importance=_optional_float(data, "importance") or 0.5,
            privacy=_expect_privacy(data, "privacy"),
            created_at=_expect_str(data, "created_at"),
            updated_at=_expect_str(data, "updated_at"),
            observed_at=_optional_str(data, "observed_at"),
            valid_from=_optional_str(data, "valid_from"),
            valid_until=_optional_str(data, "valid_until"),
            temporal_note=_optional_str(data, "temporal_note") or "",
            relations=relations,
            evidence=_optional_evidence_list(data, "evidence"),
        )

    @classmethod
    def from_candidate(cls, candidate: MemoryCandidate, *, item_id: str | None = None) -> "ProfileItem":
        return cls(
            id=item_id or new_profile_item_id(candidate.source_refs[0] if candidate.source_refs else None),
            type=candidate.type,
            title=candidate.title,
            body=candidate.body,
            tags=candidate.tags,
            source_refs=candidate.source_refs,
            confidence=candidate.confidence,
            privacy=candidate.privacy,
            observed_at=candidate.observed_at,
            valid_from=candidate.valid_from,
            valid_until=candidate.valid_until,
            temporal_note=candidate.temporal_note,
            relations=candidate.relations,
            evidence=candidate.evidence,
        )


def _expect_str(data: dict[str, object], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str):
        raise ValueError(f"field '{field_name}' must be a string")
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


def _expect_privacy(data: dict[str, object], field_name: str) -> PrivacyLevel:
    value = _expect_str(data, field_name)
    if value not in {"private", "shareable"}:
        raise ValueError(f"unsupported privacy level: {value}")
    return cast(PrivacyLevel, value)


def _optional_str_list(data: dict[str, object], field_name: str) -> list[str]:
    value = data.get(field_name)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"field '{field_name}' must be a list or null")
    result: list[str] = []
    for item in cast(list[object], value):
        if not isinstance(item, str):
            raise ValueError(f"field '{field_name}' must contain only strings")
        result.append(item)
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


def _optional_evidence_list(data: dict[str, object], field_name: str) -> list[MemoryEvidence]:
    value = data.get(field_name)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"field '{field_name}' must be a list or null")
    result: list[MemoryEvidence] = []
    for item in cast(list[object], value):
        if not isinstance(item, dict):
            raise ValueError(f"field '{field_name}' must contain only objects")
        result.append(MemoryEvidence.from_wire(cast(dict[str, object], item)))
    return result