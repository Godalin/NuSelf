"""Structured decision contract for the memory curator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias, cast

from pydantic import BaseModel, ConfigDict, Field

from nuself.domain.memory import (
    MemoryEntryType,
    default_memory_type_registry,
)
from nuself.memory.text import looks_like_raw_transcript

MemoryActionType: TypeAlias = Literal["create", "update", "ignore"]
DecisionStatus: TypeAlias = Literal["ready", "deferred"]


@dataclass(frozen=True)
class MemoryCuratorSettings:
    """Policy for one background memory curation run."""

    min_quality_chars: int = 120
    existing_memory_limit: int = 12
    auto_accept: bool = True


@dataclass(frozen=True)
class MemoryCuratorCursor:
    """Authoritative absolute position for one curated thread."""

    thread_id: str
    processed_message_count: int

    @classmethod
    def from_wire(
        cls,
        data: dict[str, object],
        *,
        expected_thread_id: str,
    ) -> MemoryCuratorCursor:
        thread_id = data.get("thread_id")
        if not isinstance(thread_id, str):
            raise ValueError("cursor field 'thread_id' must be a string")
        if thread_id != expected_thread_id:
            raise ValueError(
                "cursor thread identity mismatch: "
                f"expected {expected_thread_id!r}, got {thread_id!r}"
            )
        count = data.get("processed_message_count")
        if isinstance(count, bool) or not isinstance(count, int):
            raise ValueError(
                "cursor field 'processed_message_count' must be an integer"
            )
        if count < 0:
            raise ValueError(
                "cursor field 'processed_message_count' must be non-negative"
            )
        return cls(thread_id=thread_id, processed_message_count=count)

    def to_wire(self) -> dict[str, object]:
        return {
            "thread_id": self.thread_id,
            "processed_message_count": self.processed_message_count,
        }


@dataclass(frozen=True)
class MemoryCuratorResult:
    """Summary of a memory curator run."""

    processed_messages: int
    created: int
    updated: int
    ignored: int
    log_path: Path

    @property
    def changed(self) -> bool:
        return self.created > 0 or self.updated > 0

    def summary(self) -> str:
        return (
            f"processed={self.processed_messages} "
            f"created={self.created} updated={self.updated} "
            f"ignored={self.ignored}"
        )


@dataclass(frozen=True)
class MemoryAction:
    """One structured action proposed by the memory curator agent."""

    action: MemoryActionType
    title: str
    body: str
    type: MemoryEntryType = "episode"
    tags: tuple[str, ...] = ()
    entry_id: str | None = None
    confidence: float = 0.6
    reason: str = ""


@dataclass(frozen=True)
class MemoryDecision:
    """Structured decision returned by the curator agent."""

    status: DecisionStatus
    actions: tuple[MemoryAction, ...] = ()
    reason: str = ""


class CuratorActionItem(BaseModel):
    """One structured memory curation action from the LLM."""

    model_config = ConfigDict(strict=True, extra="forbid")

    action: Literal["create", "update", "ignore"] = Field(
        description="Memory action type."
    )
    title: str = Field(default="", description="Memory entry title.")
    body: str = Field(default="", description="Memory entry body.")
    type: str = Field(default="episode", description="Memory entry type.")
    tags: list[str] = Field(
        default_factory=lambda: list[str](),
        max_length=4,
        description="One to four short tags.",
    )
    entry_id: str | None = Field(
        default=None,
        description="Existing entry id to update.",
    )
    confidence: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Confidence from 0.0 to 1.0.",
    )
    reason: str = Field(default="", description="Reason for the action.")


class CuratorActionsOutput(BaseModel):
    """Structured curator actions response from the LLM."""

    model_config = ConfigDict(strict=True, extra="forbid")

    actions: list[CuratorActionItem] = Field(
        description="Memory curation actions."
    )


def actions_from_output(
    output: CuratorActionsOutput,
    *,
    allowed_types: tuple[str, ...] | None = None,
) -> list[MemoryAction]:
    return [
        action_from_item(item, allowed_types=allowed_types)
        for item in output.actions
    ]


def action_from_item(
    item: CuratorActionItem,
    *,
    allowed_types: tuple[str, ...] | None = None,
) -> MemoryAction:
    title = item.title.strip()
    body = item.body.strip()
    if item.action != "ignore" and (title == "" or body == ""):
        raise ValueError("memory mutation action requires title and body")
    tags = _normalize_tags(item.tags)
    if item.action != "ignore" and not tags:
        raise ValueError("memory mutation action requires tags")
    if item.action != "ignore" and looks_like_raw_transcript(body):
        raise ValueError(
            "memory mutation action body must not be a transcript"
        )
    if item.action == "update" and (
        item.entry_id is None or item.entry_id.strip() == ""
    ):
        raise ValueError("memory update action requires entry_id")
    memory_type = _memory_type(
        item.type,
        allowed_types=allowed_types,
    )
    return MemoryAction(
        action=item.action,
        type=memory_type,
        title=title,
        body=body,
        tags=tags,
        entry_id=item.entry_id,
        confidence=item.confidence,
        reason=item.reason,
    )


def _memory_type(
    value: str,
    *,
    allowed_types: tuple[str, ...] | None = None,
) -> MemoryEntryType:
    names = allowed_types or default_memory_type_registry().names()
    if value in names:
        return cast(MemoryEntryType, value)
    raise ValueError(f"unsupported memory type: {value}")


def _normalize_tags(tags: list[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        clean = tag.strip()
        if clean == "" or clean in seen:
            continue
        normalized.append(clean)
        seen.add(clean)
    return tuple(normalized)
