"""Memory entry domain model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, TypeAlias, cast
from uuid import uuid4

MemoryEntryType: TypeAlias = Literal[
    "source_note",
    "profile_fact",
    "belief",
    "style_trait",
    "episode",
    "open_question",
    "instruction",
]

ReviewState: TypeAlias = Literal["draft", "reviewed", "rejected"]
PrivacyLevel: TypeAlias = Literal["private", "shareable"]


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_memory_entry_id() -> str:
    return f"mem_{uuid4().hex}"


def empty_str_list() -> list[str]:
    return []


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

    def with_updates(
        self,
        *,
        title: str | None = None,
        body: str | None = None,
        tags: list[str] | None = None,
        confidence: float | None = None,
        review_state: ReviewState | None = None,
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
        }

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


def _expect_memory_type(data: dict[str, object], field_name: str) -> MemoryEntryType:
    value = _expect_str(data, field_name)
    if value not in {
        "source_note",
        "profile_fact",
        "belief",
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


def _expect_privacy(data: dict[str, object], field_name: str) -> PrivacyLevel:
    value = _expect_str(data, field_name)
    if value not in {"private", "shareable"}:
        raise ValueError(f"unsupported privacy level: {value}")
    return cast(PrivacyLevel, value)
