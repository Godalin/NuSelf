"""Reason domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, TypeAlias, cast
from uuid import uuid4

ReasonStatus: TypeAlias = Literal["active", "paused", "resolved", "archived"]
StepKind: TypeAlias = Literal["progress", "no_change", "question", "synthesis", "contradiction", "resolution"]
ReasonPriority: TypeAlias = Literal["normal", "high"]

REASON_STATUSES: tuple[ReasonStatus, ...] = ("active", "paused", "resolved", "archived")
STEP_KINDS: tuple[StepKind, ...] = ("progress", "no_change", "question", "synthesis", "contradiction", "resolution")
REASON_PRIORITIES: tuple[ReasonPriority, ...] = ("normal", "high")

ACTIVE_STATUSES: tuple[ReasonStatus, ...] = ("active", "paused")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_thread_id() -> str:
    return f"reason-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:8]}"


def new_step_id() -> str:
    return f"step-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:8]}"


def _empty_str_list() -> list[str]:
    return []


@dataclass(frozen=True)
class ReasoningThread:
    id: str = field(default_factory=new_thread_id)
    question: str = ""
    status: ReasonStatus = "active"
    working_summary: str = ""
    hypotheses: list[str] = field(default_factory=_empty_str_list)
    open_questions: list[str] = field(default_factory=_empty_str_list)
    evidence_refs: list[str] = field(default_factory=_empty_str_list)
    priority: ReasonPriority = "normal"
    last_advanced_at: str | None = None
    next_review_after: str | None = None
    skip_next_advance_until: str | None = None
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        if self.status not in REASON_STATUSES:
            raise ValueError(f"invalid reason status: {self.status}")
        if self.priority not in REASON_PRIORITIES:
            raise ValueError(f"invalid reason priority: {self.priority}")
        if self.question.strip() == "":
            raise ValueError("reason question must not be empty")

    def to_wire(self) -> dict[str, object]:
        return {
            "id": self.id,
            "question": self.question,
            "status": self.status,
            "working_summary": self.working_summary,
            "hypotheses": self.hypotheses,
            "open_questions": self.open_questions,
            "evidence_refs": self.evidence_refs,
            "priority": self.priority,
            "last_advanced_at": self.last_advanced_at,
            "next_review_after": self.next_review_after,
            "skip_next_advance_until": self.skip_next_advance_until,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> ReasoningThread:
        return cls(
            id=_expect_str(data, "id"),
            question=_expect_str(data, "question"),
            status=_expect_reason_status(data, "status"),
            working_summary=_expect_str(data, "working_summary"),
            hypotheses=_optional_str_list(data, "hypotheses"),
            open_questions=_optional_str_list(data, "open_questions"),
            evidence_refs=_optional_str_list(data, "evidence_refs"),
            priority=_expect_reason_priority(data, "priority"),
            last_advanced_at=_optional_str(data, "last_advanced_at"),
            next_review_after=_optional_str(data, "next_review_after"),
            skip_next_advance_until=_optional_str(data, "skip_next_advance_until"),
            created_at=_expect_str(data, "created_at"),
            updated_at=_expect_str(data, "updated_at"),
        )

    def with_status(self, status: ReasonStatus) -> ReasoningThread:
        now = _now_iso()
        return ReasoningThread(
            id=self.id,
            question=self.question,
            status=status,
            working_summary=self.working_summary,
            hypotheses=list(self.hypotheses),
            open_questions=list(self.open_questions),
            evidence_refs=list(self.evidence_refs),
            priority=self.priority,
            last_advanced_at=self.last_advanced_at,
            next_review_after=self.next_review_after,
            skip_next_advance_until=self.skip_next_advance_until,
            created_at=self.created_at,
            updated_at=now,
        )


@dataclass(frozen=True)
class ReasoningStep:
    id: str = field(default_factory=new_step_id)
    thread_id: str = ""
    kind: StepKind = "progress"
    summary: str = ""
    delta: str = ""
    new_hypotheses: list[str] = field(default_factory=_empty_str_list)
    retired_hypotheses: list[str] = field(default_factory=_empty_str_list)
    new_open_questions: list[str] = field(default_factory=_empty_str_list)
    evidence_refs: list[str] = field(default_factory=_empty_str_list)
    tool_calls: tuple[tuple[str, dict[str, object]], ...] = ()
    confidence: float | None = None
    created_at: str = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        if self.kind not in STEP_KINDS:
            raise ValueError(f"invalid step kind: {self.kind}")
        if self.thread_id.strip() == "":
            raise ValueError("step thread_id must not be empty")
        if self.summary.strip() == "":
            raise ValueError("step summary must not be empty")

    def to_wire(self) -> dict[str, object]:
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "kind": self.kind,
            "summary": self.summary,
            "delta": self.delta,
            "new_hypotheses": self.new_hypotheses,
            "retired_hypotheses": self.retired_hypotheses,
            "new_open_questions": self.new_open_questions,
            "evidence_refs": self.evidence_refs,
            "tool_calls": [[name, args] for name, args in self.tool_calls],
            "confidence": self.confidence,
            "created_at": self.created_at,
        }

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> ReasoningStep:
        return cls(
            id=_expect_str(data, "id"),
            thread_id=_expect_str(data, "thread_id"),
            kind=_expect_step_kind(data, "kind"),
            summary=_expect_str(data, "summary"),
            delta=_expect_str(data, "delta"),
            new_hypotheses=_optional_str_list(data, "new_hypotheses"),
            retired_hypotheses=_optional_str_list(data, "retired_hypotheses"),
            new_open_questions=_optional_str_list(data, "new_open_questions"),
            evidence_refs=_optional_str_list(data, "evidence_refs"),
            tool_calls=_optional_tool_calls(data, "tool_calls"),
            confidence=_optional_float(data, "confidence"),
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


def _optional_str_list(data: dict[str, object], field_name: str) -> list[str]:
    value = data.get(field_name)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"field '{field_name}' must be a list of strings")
    raw = cast(list[object], value)
    if not all(isinstance(item, str) for item in raw):
        raise ValueError(f"field '{field_name}' must be a list of strings")
    return list(cast(list[str], raw))


def _optional_tool_calls(data: dict[str, object], field_name: str) -> tuple[tuple[str, dict[str, object]], ...]:
    value = data.get(field_name)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"field '{field_name}' must be a list")
    raw = cast(list[Any], value)  # pyright: ignore[reportUnknownVariableType]
    result: list[tuple[str, dict[str, object]]] = []
    for item in raw:
        if isinstance(item, list) and item and isinstance(item[0], str) and isinstance(item[1], dict):
            result.append((item[0], cast(dict[str, object], item[1])))
        elif isinstance(item, str) and "(" in item:
            result.append((item.split("(")[0], {"_raw": item}))
    return tuple(result)


def _optional_float(data: dict[str, object], field_name: str) -> float | None:
    value = data.get(field_name)
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    raise ValueError(f"field '{field_name}' must be a number or null")


def _expect_reason_status(data: dict[str, object], field_name: str) -> ReasonStatus:
    value = _expect_str(data, field_name)
    if value in REASON_STATUSES:
        return value  # pyright: ignore[reportReturnType]
    raise ValueError(f"field '{field_name}' must be a reason status")


def _expect_reason_priority(data: dict[str, object], field_name: str) -> ReasonPriority:
    value = _expect_str(data, field_name)
    if value in REASON_PRIORITIES:
        return value  # pyright: ignore[reportReturnType]
    raise ValueError(f"field '{field_name}' must be a reason priority")


def _expect_step_kind(data: dict[str, object], field_name: str) -> StepKind:
    value = _expect_str(data, field_name)
    if value in STEP_KINDS:
        return value  # pyright: ignore[reportReturnType]
    raise ValueError(f"field '{field_name}' must be a step kind")
