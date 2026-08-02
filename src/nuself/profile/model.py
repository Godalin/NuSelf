"""Derived profile domain models."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import cast
from uuid import NAMESPACE_URL, uuid5

from nuself.clock import utc_now_iso
from nuself.memory.model import (
    MemoryCandidate,
    MemoryEvidence,
    PrivacyLevel,
)
from nuself.runtime.messages import freeze_json_value, thaw_json_value


def _optional_float(data: dict[str, object], field_name: str) -> float | None:
    value = data.get(field_name)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"field '{field_name}' must be a number or null")
    if isinstance(value, int | float):
        return float(value)
    raise ValueError(f"field '{field_name}' must be a number or null")


def _optional_float_default(
    data: dict[str, object],
    field_name: str,
    *,
    default: float,
) -> float:
    value = _optional_float(data, field_name)
    return default if value is None else value


def _freeze_str_sequence(
    value: object,
    *,
    field_name: str,
) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise TypeError(f"field '{field_name}' must be a sequence of strings")
    items = cast(Sequence[object], value)
    if not all(isinstance(item, str) for item in items):
        raise TypeError(f"field '{field_name}' must contain only strings")
    return tuple(cast(Sequence[str], items))


def _freeze_relations(
    value: object,
    *,
    field_name: str,
) -> Mapping[str, Sequence[str]]:
    if not isinstance(value, Mapping):
        raise TypeError(f"field '{field_name}' must be a mapping")
    relations = cast(Mapping[object, object], value)
    normalized: dict[str, tuple[str, ...]] = {}
    for key, targets in relations.items():
        if not isinstance(key, str):
            raise TypeError(f"field '{field_name}' keys must be strings")
        normalized[key] = _freeze_str_sequence(
            targets,
            field_name=f"{field_name}.{key}",
        )
    frozen = freeze_json_value(normalized)
    if not isinstance(frozen, Mapping):
        raise TypeError(f"field '{field_name}' must be a mapping")
    return cast(Mapping[str, Sequence[str]], frozen)


def _freeze_evidence(
    value: object,
    *,
    field_name: str,
) -> tuple[MemoryEvidence, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise TypeError(
            f"field '{field_name}' must be a sequence of MemoryEvidence"
        )
    items = cast(Sequence[object], value)
    if not all(isinstance(item, MemoryEvidence) for item in items):
        raise TypeError(
            f"field '{field_name}' must contain only MemoryEvidence"
        )
    return tuple(cast(Sequence[MemoryEvidence], items))


def new_profile_item_id(source_ref: str | None = None) -> str:
    if source_ref is None:
        return f"profile_{uuid5(NAMESPACE_URL, utc_now_iso()).hex}"
    return f"profile_{uuid5(NAMESPACE_URL, source_ref).hex}"


@dataclass(frozen=True)
class ProfileItem:
    """Durable derived profile state."""

    type: str
    title: str
    body: str
    tags: Sequence[str] = field(default_factory=list[str])
    source_refs: Sequence[str] = field(default_factory=list[str])
    confidence: float = 1.0
    importance: float = 0.5
    privacy: PrivacyLevel = "private"
    id: str = field(default_factory=new_profile_item_id)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    observed_at: str | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    temporal_note: str = ""
    relations: Mapping[str, Sequence[str]] = field(
        default_factory=dict[str, list[str]]
    )
    evidence: Sequence[MemoryEvidence] = field(
        default_factory=list[MemoryEvidence]
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "tags",
            _freeze_str_sequence(self.tags, field_name="tags"),
        )
        object.__setattr__(
            self,
            "source_refs",
            _freeze_str_sequence(self.source_refs, field_name="source_refs"),
        )
        object.__setattr__(
            self,
            "relations",
            _freeze_relations(self.relations, field_name="relations"),
        )
        object.__setattr__(
            self,
            "evidence",
            _freeze_evidence(self.evidence, field_name="evidence"),
        )

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
            updated_at=utc_now_iso(),
            observed_at=observed_at if observed_at is not None else self.observed_at,
            valid_from=valid_from if valid_from is not None else self.valid_from,
            valid_until=valid_until if valid_until is not None else self.valid_until,
            temporal_note=temporal_note if temporal_note is not None else self.temporal_note,
            relations=self.relations,
            evidence=self.evidence,
        )

    def to_wire(self) -> dict[str, object]:
        wire = {
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
            "evidence": [evidence.to_wire() for evidence in self.evidence],
        }
        return cast(dict[str, object], thaw_json_value(wire))

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> "ProfileItem":
        for field_name in ("supersedes", "related_memory_ids"):
            if field_name in data:
                raise ValueError(
                    f"obsolete profile relation field '{field_name}'; "
                    "use 'relations'"
                )
        relations = _expect_relations_dict(data, "relations")
        return cls(
            id=_expect_str(data, "id"),
            type=_expect_str(data, "type"),
            title=_expect_str(data, "title"),
            body=_expect_str(data, "body"),
            tags=_expect_str_list(data, "tags"),
            source_refs=_expect_str_list(data, "source_refs"),
            confidence=_expect_float(data, "confidence"),
            importance=_optional_float_default(
                data,
                "importance",
                default=0.5,
            ),
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
            tags=list(candidate.tags),
            source_refs=list(candidate.source_refs),
            confidence=candidate.confidence,
            privacy=candidate.privacy,
            observed_at=candidate.observed_at,
            valid_from=candidate.valid_from,
            valid_until=candidate.valid_until,
            temporal_note=candidate.temporal_note,
            relations={
                key: list(values)
                for key, values in candidate.relations.items()
            },
            evidence=list(candidate.evidence),
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


def _expect_relations_dict(
    data: dict[str, object],
    field_name: str,
) -> dict[str, list[str]]:
    if field_name not in data:
        raise ValueError(f"missing required field '{field_name}'")
    value = data[field_name]
    if not isinstance(value, dict):
        raise ValueError(f"field '{field_name}' must be an object")
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
