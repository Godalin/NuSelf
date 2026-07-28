"""Reason domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypeAlias, cast
from uuid import uuid4

from nuself.clock import utc_now, utc_now_iso

ReasonStatus: TypeAlias = Literal["active", "paused", "resolved", "archived"]
StepKind: TypeAlias = Literal["progress", "no_change", "question", "synthesis", "contradiction", "resolution", "planning"]
ReasonPriority: TypeAlias = Literal["normal", "high"]
TerminalStatus: TypeAlias = Literal["continue", "suggest_resolved", "suggest_paused"]

REASON_STATUSES: tuple[ReasonStatus, ...] = ("active", "paused", "resolved", "archived")
STEP_KINDS: tuple[StepKind, ...] = ("progress", "no_change", "question", "synthesis", "contradiction", "resolution", "planning")
REASON_PRIORITIES: tuple[ReasonPriority, ...] = ("normal", "high")
TERMINAL_STATUSES: tuple[TerminalStatus, ...] = ("continue", "suggest_resolved", "suggest_paused")

ACTIVE_STATUSES: tuple[ReasonStatus, ...] = ("active", "paused")


def new_thread_id() -> str:
    return f"reason-{utc_now().strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:8]}"


def new_step_id() -> str:
    return f"step-{utc_now().strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:8]}"


def _empty_str_list() -> list[str]:
    return []


@dataclass(frozen=True)
class TrackedItem:
    """A single tracked item in reasoning state — can represent any kind of active
    clue, pending question, step plan, etc. The *kind* field is free-text so the
    LLM adapts it to the task (character, suspect, hypothesis, plot_thread, ...)."""

    label: str
    description: str = ""
    kind: str = ""
    status: str = "active"

    def to_wire(self) -> dict[str, object]:
        return {"label": self.label, "description": self.description, "kind": self.kind, "status": self.status}

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> TrackedItem:
        raw_label = data.get("label")
        label = str(raw_label) if raw_label is not None else ""
        raw_desc = data.get("description")
        description = str(raw_desc) if isinstance(raw_desc, str) else ""
        raw_kind = data.get("kind")
        kind = str(raw_kind) if isinstance(raw_kind, str) else ""
        raw_status = data.get("status")
        status = str(raw_status) if isinstance(raw_status, str) else "active"
        return cls(label=label, description=description, kind=kind, status=status)



@dataclass(frozen=True)
class ReasoningThread:
    id: str = field(default_factory=new_thread_id)
    topic: str = ""
    status: ReasonStatus = "active"
    working_summary: str = ""
    evidence_refs: list[str] = field(default_factory=_empty_str_list)
    priority: ReasonPriority = "normal"
    last_advanced_at: str | None = None
    next_review_after: str | None = None
    skip_next_advance_until: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    active_items_data: tuple[dict[str, object], ...] = ()
    pending_items_data: tuple[dict[str, object], ...] = ()
    next_steps_data: tuple[dict[str, object], ...] = ()
    mandates_data: tuple[str, ...] = ()
    reasoning_prompt: str = ""

    def __post_init__(self) -> None:
        if self.status not in REASON_STATUSES:
            raise ValueError(f"invalid reason status: {self.status}")
        if self.priority not in REASON_PRIORITIES:
            raise ValueError(f"invalid reason priority: {self.priority}")
        if self.topic.strip() == "":
            raise ValueError("reason topic must not be empty")

    @property
    def active_items(self) -> list[TrackedItem]:
        return [TrackedItem.from_wire(d) for d in self.active_items_data]

    @property
    def pending_items(self) -> list[TrackedItem]:
        return [TrackedItem.from_wire(d) for d in self.pending_items_data]

    @property
    def next_steps(self) -> list[TrackedItem]:
        return [TrackedItem.from_wire(d) for d in self.next_steps_data]

    @property
    def mandates(self) -> list[str]:
        return list(self.mandates_data)

    def to_wire(self) -> dict[str, object]:
        return {
            "id": self.id,
            "topic": self.topic,
            "status": self.status,
            "working_summary": self.working_summary,
            "active_items_data": [t for t in self.active_items_data],
            "pending_items_data": [t for t in self.pending_items_data],
            "next_steps_data": [t for t in self.next_steps_data],
            "mandates_data": [m for m in self.mandates_data],
            "reasoning_prompt": self.reasoning_prompt,
            "evidence_refs": self.evidence_refs,
            "priority": self.priority,
            "last_advanced_at": self.last_advanced_at,
            "skip_next_advance_until": self.skip_next_advance_until,
            "next_review_after": self.next_review_after,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> ReasoningThread:
        return cls(
            id=_expect_str(data, "id"),
            topic=_expect_str(data, "topic"),
            status=_expect_reason_status(data, "status"),
            working_summary=_expect_str(data, "working_summary"),
            evidence_refs=_optional_str_list(data, "evidence_refs"),
            priority=_expect_reason_priority(data, "priority"),
            last_advanced_at=_optional_str(data, "last_advanced_at"),
            next_review_after=_optional_str(data, "next_review_after"),
            skip_next_advance_until=_optional_str(data, "skip_next_advance_until"),
            created_at=_expect_str(data, "created_at"),
            updated_at=_expect_str(data, "updated_at"),
            active_items_data=_optional_tracked_items(data, "active_items_data"),
            pending_items_data=_optional_tracked_items(data, "pending_items_data"),
            next_steps_data=_optional_tracked_items(data, "next_steps_data"),
            mandates_data=_optional_mandates(data, "mandates_data"),
            reasoning_prompt=_optional_str_with_default(data, "reasoning_prompt"),
        )

    def with_status(self, status: ReasonStatus) -> ReasoningThread:
        now = utc_now_iso()
        return ReasoningThread(
            id=self.id,
            topic=self.topic,
            status=status,
            working_summary=self.working_summary,
            evidence_refs=list(self.evidence_refs),
            priority=self.priority,
            last_advanced_at=self.last_advanced_at,
            next_review_after=self.next_review_after,
            skip_next_advance_until=self.skip_next_advance_until,
            created_at=self.created_at,
            updated_at=now,
            active_items_data=self.active_items_data,
            pending_items_data=self.pending_items_data,
            next_steps_data=self.next_steps_data,
            mandates_data=self.mandates_data,
            reasoning_prompt=self.reasoning_prompt,
        )


@dataclass(frozen=True)
class ReasoningStep:
    id: str = field(default_factory=new_step_id)
    thread_id: str = ""
    kind: StepKind = "progress"
    summary: str = ""
    delta: str = ""
    evidence_refs: list[str] = field(default_factory=_empty_str_list)
    output: str = ""
    tool_logs: tuple[dict[str, object], ...] = ()
    confidence: float | None = None
    created_at: str = field(default_factory=utc_now_iso)
    new_findings_data: tuple[dict[str, object], ...] = ()
    new_pending_data: tuple[dict[str, object], ...] = ()
    retired_findings_data: tuple[dict[str, object], ...] = ()
    next_steps_data: tuple[dict[str, object], ...] = ()
    terminal_status: TerminalStatus = "continue"
    terminal_reason: str = ""

    def __post_init__(self) -> None:
        if self.kind not in STEP_KINDS:
            raise ValueError(f"invalid step kind: {self.kind}")
        if self.terminal_status not in TERMINAL_STATUSES:
            raise ValueError(f"invalid terminal status: {self.terminal_status}")
        if self.thread_id.strip() == "":
            raise ValueError("step thread_id must not be empty")
        if self.summary.strip() == "":
            raise ValueError("step summary must not be empty")

    @property
    def new_findings(self) -> list[TrackedItem]:
        return [TrackedItem.from_wire(d) for d in self.new_findings_data]

    @property
    def new_pending(self) -> list[TrackedItem]:
        return [TrackedItem.from_wire(d) for d in self.new_pending_data]

    @property
    def retired_findings(self) -> list[TrackedItem]:
        return [TrackedItem.from_wire(d) for d in self.retired_findings_data]

    @property
    def next_steps(self) -> list[TrackedItem]:
        return [TrackedItem.from_wire(d) for d in self.next_steps_data]

    def to_wire(self) -> dict[str, object]:
        result: dict[str, object] = {
            "id": self.id,
            "thread_id": self.thread_id,
            "kind": self.kind,
            "summary": self.summary,
            "delta": self.delta,
            "evidence_refs": self.evidence_refs,
            "output": self.output,
            "tool_logs": [dict(t) for t in self.tool_logs],
            "confidence": self.confidence,
            "created_at": self.created_at,
            "new_findings_data": [t for t in self.new_findings_data],
            "new_pending_data": [t for t in self.new_pending_data],
            "retired_findings_data": [t for t in self.retired_findings_data],
            "next_steps_data": [t for t in self.next_steps_data],
            "terminal_status": self.terminal_status,
            "terminal_reason": self.terminal_reason,
        }
        return result

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> ReasoningStep:
        return cls(
            id=_expect_str(data, "id"),
            thread_id=_expect_str(data, "thread_id"),
            kind=_expect_step_kind(data, "kind"),
            summary=_expect_str(data, "summary"),
            delta=_expect_str(data, "delta"),
            evidence_refs=_optional_str_list(data, "evidence_refs"),
            output=_optional_str_with_default(data, "output"),
            tool_logs=_optional_tool_logs(data, "tool_logs"),
            confidence=_optional_float(data, "confidence"),
            created_at=_expect_str(data, "created_at"),
            new_findings_data=_optional_tracked_items(data, "new_findings_data"),
            new_pending_data=_optional_tracked_items(data, "new_pending_data"),
            retired_findings_data=_optional_tracked_items(data, "retired_findings_data"),
            next_steps_data=_optional_tracked_items(data, "next_steps_data"),
            terminal_status=_optional_terminal_status(data, "terminal_status"),
            terminal_reason=_optional_str_with_default(data, "terminal_reason"),
        )


# A concrete alias to help type inference in other modules
ReasonStepList: TypeAlias = list[ReasoningStep]


def partition_steps(items: ReasonStepList, size: int) -> list[ReasonStepList]:
    """Partition a list of ReasoningStep into chunks of the given size."""
    if size < 1:
        raise ValueError("segment_size must be a positive integer")
    result: list[ReasonStepList] = []
    for i in range(0, len(items), size):
        result.append(items[i : i + size])
    return result


def _optional_tracked_items(data: dict[str, object], field_name: str) -> tuple[dict[str, object], ...]:
    value = data.get(field_name)
    if value is None:
        return ()
    if not isinstance(value, list):
        return ()
    raw = cast(list[object], value)
    result: list[dict[str, object]] = []
    for item in raw:
        if isinstance(item, dict):
            result.append(cast(dict[str, object], item))
    return tuple(result)


def _optional_mandates(data: dict[str, object], field_name: str) -> tuple[str, ...]:
    value = data.get(field_name)
    if value is None:
        return ()
    if not isinstance(value, list):
        return ()
    raw = cast(list[object], value)
    return tuple(str(item) for item in raw if isinstance(item, str))


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


def _optional_str_with_default(data: dict[str, object], field_name: str, default: str = "") -> str:
    value = data.get(field_name)
    if isinstance(value, str):
        return value
    return default


def _optional_tool_logs(data: dict[str, object], field_name: str) -> tuple[dict[str, object], ...]:
    value = data.get(field_name)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"field '{field_name}' must be a list")
    result: list[dict[str, object]] = []
    for item in cast(list[object], value):
        if not isinstance(item, dict):
            raise ValueError(f"field '{field_name}' must contain objects")
        result.append(cast(dict[str, object], item))
    return tuple(result)


def _optional_float(data: dict[str, object], field_name: str) -> float | None:
    value = data.get(field_name)
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    raise ValueError(f"field '{field_name}' must be a number or null")


def _optional_terminal_status(data: dict[str, object], field_name: str) -> TerminalStatus:
    value = data.get(field_name)
    if value is None:
        return "continue"
    if isinstance(value, str) and value in TERMINAL_STATUSES:
        return value  # pyright: ignore[reportReturnType]
    raise ValueError(f"field '{field_name}' must be a terminal status")


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
