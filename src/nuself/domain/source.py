"""Source document domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, TypeAlias, cast
from uuid import uuid5, NAMESPACE_URL

from nuself.clock import utc_now_iso
from nuself.domain.memory import PrivacyLevel

SourceKind: TypeAlias = Literal["markdown", "text"]


def empty_str_list() -> list[str]:
    return []


def source_id_for_path(path: Path) -> str:
    return f"src_{uuid5(NAMESPACE_URL, str(path.resolve())).hex}"


def chunk_id_for(source_id: str, index: int) -> str:
    return f"{source_id}_chunk_{index:04d}"


@dataclass(frozen=True)
class SourceDocument:
    """Imported source document metadata."""

    id: str
    title: str
    path: str
    kind: SourceKind
    origin: str = "local"
    privacy: PrivacyLevel = "private"
    tags: list[str] = field(default_factory=empty_str_list)
    source_date: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_wire(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "path": self.path,
            "kind": self.kind,
            "origin": self.origin,
            "privacy": self.privacy,
            "tags": self.tags,
            "source_date": self.source_date,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> "SourceDocument":
        return cls(
            id=_expect_str(data, "id"),
            title=_expect_str(data, "title"),
            path=_expect_str(data, "path"),
            kind=_expect_kind(data, "kind"),
            origin=_optional_str(data, "origin") or "local",
            privacy=_expect_privacy(data, "privacy"),
            tags=_expect_str_list(data, "tags"),
            source_date=_optional_str(data, "source_date"),
            created_at=_expect_str(data, "created_at"),
            updated_at=_expect_str(data, "updated_at"),
        )


@dataclass(frozen=True)
class SourceChunk:
    """Stable chunk extracted from a source document."""

    id: str
    source_id: str
    source_ref: str
    index: int
    text: str
    title: str
    path: str
    created_at: str = field(default_factory=utc_now_iso)

    def to_wire(self) -> dict[str, object]:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "source_ref": self.source_ref,
            "index": self.index,
            "text": self.text,
            "title": self.title,
            "path": self.path,
            "created_at": self.created_at,
        }

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> "SourceChunk":
        return cls(
            id=_expect_str(data, "id"),
            source_id=_expect_str(data, "source_id"),
            source_ref=_expect_str(data, "source_ref"),
            index=_expect_int(data, "index"),
            text=_expect_str(data, "text"),
            title=_expect_str(data, "title"),
            path=_expect_str(data, "path"),
            created_at=_expect_str(data, "created_at"),
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


def _expect_int(data: dict[str, object], field_name: str) -> int:
    value = data.get(field_name)
    if not isinstance(value, int):
        raise ValueError(f"field '{field_name}' must be an integer")
    return value


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


def _expect_kind(data: dict[str, object], field_name: str) -> SourceKind:
    value = _expect_str(data, field_name)
    if value not in {"markdown", "text"}:
        raise ValueError(f"unsupported source kind: {value}")
    return cast(SourceKind, value)


def _expect_privacy(data: dict[str, object], field_name: str) -> PrivacyLevel:
    value = _expect_str(data, field_name)
    if value not in {"private", "shareable"}:
        raise ValueError(f"unsupported privacy level: {value}")
    return cast(PrivacyLevel, value)
