"""Reason domain models."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, TypeAlias, cast
from uuid import uuid4

from nuself.clock import utc_now, utc_now_iso
from nuself.runtime.messages import freeze_json_value, thaw_json_value

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
    def from_wire(cls, data: Mapping[str, object]) -> TrackedItem:
        label = data.get("label")
        if not isinstance(label, str) or not label.strip():
            raise ValueError("tracked item field 'label' must be a non-empty string")

        def optional_string(field_name: str, default: str) -> str:
            value = data.get(field_name, default)
            if not isinstance(value, str):
                raise ValueError(
                    f"tracked item field '{field_name}' must be a string"
                )
            return value

        return cls(
            label=label,
            description=optional_string("description", ""),
            kind=optional_string("kind", ""),
            status=optional_string("status", "active"),
        )



@dataclass(frozen=True)
class ReasoningThread:
    id: str = field(default_factory=new_thread_id)
    topic: str = ""
    status: ReasonStatus = "active"
    working_summary: str = ""
    evidence_refs: Sequence[str] = ()
    priority: ReasonPriority = "normal"
    last_advanced_at: str | None = None
    next_review_after: str | None = None
    skip_next_advance_until: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    active_items_data: tuple[Mapping[str, object], ...] = ()
    pending_items_data: tuple[Mapping[str, object], ...] = ()
    next_steps_data: tuple[Mapping[str, object], ...] = ()
    mandates_data: tuple[str, ...] = ()
    reasoning_prompt: str = ""

    def __post_init__(self) -> None:
        if self.status not in REASON_STATUSES:
            raise ValueError(f"invalid reason status: {self.status}")
        if self.priority not in REASON_PRIORITIES:
            raise ValueError(f"invalid reason priority: {self.priority}")
        if self.topic.strip() == "":
            raise ValueError("reason topic must not be empty")
        _validate_aware_iso(self.created_at, field_name="created_at")
        _validate_aware_iso(self.updated_at, field_name="updated_at")
        for field_name in (
            "last_advanced_at",
            "next_review_after",
            "skip_next_advance_until",
        ):
            _validate_optional_aware_iso(
                getattr(self, field_name),
                field_name=field_name,
            )
        object.__setattr__(
            self,
            "evidence_refs",
            _freeze_str_sequence(self.evidence_refs, field_name="evidence_refs"),
        )
        for field_name in (
            "active_items_data",
            "pending_items_data",
            "next_steps_data",
        ):
            object.__setattr__(
                self,
                field_name,
                _freeze_mapping_sequence(
                    getattr(self, field_name),
                    field_name=field_name,
                ),
            )
        object.__setattr__(
            self,
            "mandates_data",
            _freeze_str_sequence(
                self.mandates_data,
                field_name="mandates_data",
            ),
        )

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
        record = {
            "id": self.id,
            "topic": self.topic,
            "status": self.status,
            "working_summary": self.working_summary,
            "active_items_data": self.active_items_data,
            "pending_items_data": self.pending_items_data,
            "next_steps_data": self.next_steps_data,
            "mandates_data": self.mandates_data,
            "reasoning_prompt": self.reasoning_prompt,
            "evidence_refs": self.evidence_refs,
            "priority": self.priority,
            "last_advanced_at": self.last_advanced_at,
            "skip_next_advance_until": self.skip_next_advance_until,
            "next_review_after": self.next_review_after,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        return cast(dict[str, object], thaw_json_value(record))

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> ReasoningThread:
        return cls(
            id=_expect_str(data, "id"),
            topic=_expect_str(data, "topic"),
            status=_expect_reason_status(data, "status"),
            working_summary=_expect_str(data, "working_summary"),
            evidence_refs=_expect_str_list(data, "evidence_refs"),
            priority=_expect_reason_priority(data, "priority"),
            last_advanced_at=_expect_optional_str(data, "last_advanced_at"),
            next_review_after=_expect_optional_str(data, "next_review_after"),
            skip_next_advance_until=_expect_optional_str(
                data,
                "skip_next_advance_until",
            ),
            created_at=_expect_str(data, "created_at"),
            updated_at=_expect_str(data, "updated_at"),
            active_items_data=_expect_tracked_items(data, "active_items_data"),
            pending_items_data=_expect_tracked_items(data, "pending_items_data"),
            next_steps_data=_expect_tracked_items(data, "next_steps_data"),
            mandates_data=_expect_mandates(data, "mandates_data"),
            reasoning_prompt=_expect_str(data, "reasoning_prompt"),
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
    evidence_refs: Sequence[str] = ()
    output: str = ""
    tool_logs: tuple[Mapping[str, object], ...] = ()
    confidence: float | None = None
    created_at: str = field(default_factory=utc_now_iso)
    new_findings_data: tuple[Mapping[str, object], ...] = ()
    new_pending_data: tuple[Mapping[str, object], ...] = ()
    retired_findings_data: tuple[Mapping[str, object], ...] = ()
    next_steps_data: tuple[Mapping[str, object], ...] = ()
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
        object.__setattr__(
            self,
            "evidence_refs",
            _freeze_str_sequence(self.evidence_refs, field_name="evidence_refs"),
        )
        for field_name in (
            "tool_logs",
            "new_findings_data",
            "new_pending_data",
            "retired_findings_data",
            "next_steps_data",
        ):
            object.__setattr__(
                self,
                field_name,
                _freeze_mapping_sequence(
                    getattr(self, field_name),
                    field_name=field_name,
                ),
            )

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
        result = {
            "id": self.id,
            "thread_id": self.thread_id,
            "kind": self.kind,
            "summary": self.summary,
            "delta": self.delta,
            "evidence_refs": self.evidence_refs,
            "output": self.output,
            "tool_logs": self.tool_logs,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "new_findings_data": self.new_findings_data,
            "new_pending_data": self.new_pending_data,
            "retired_findings_data": self.retired_findings_data,
            "next_steps_data": self.next_steps_data,
            "terminal_status": self.terminal_status,
            "terminal_reason": self.terminal_reason,
        }
        return cast(dict[str, object], thaw_json_value(result))

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> ReasoningStep:
        return cls(
            id=_expect_str(data, "id"),
            thread_id=_expect_str(data, "thread_id"),
            kind=_expect_step_kind(data, "kind"),
            summary=_expect_str(data, "summary"),
            delta=_expect_str(data, "delta"),
            evidence_refs=_expect_str_list(data, "evidence_refs"),
            output=_expect_str(data, "output"),
            tool_logs=_expect_tool_logs(data, "tool_logs"),
            confidence=_expect_optional_float(data, "confidence"),
            created_at=_expect_str(data, "created_at"),
            new_findings_data=_expect_tracked_items(data, "new_findings_data"),
            new_pending_data=_expect_tracked_items(data, "new_pending_data"),
            retired_findings_data=_expect_tracked_items(
                data,
                "retired_findings_data",
            ),
            next_steps_data=_expect_tracked_items(data, "next_steps_data"),
            terminal_status=_expect_terminal_status(data, "terminal_status"),
            terminal_reason=_expect_str(data, "terminal_reason"),
        )


def partition_steps(
    items: list[ReasoningStep],
    size: int,
) -> list[list[ReasoningStep]]:
    """Partition a list of ReasoningStep into chunks of the given size."""
    if size < 1:
        raise ValueError("segment_size must be a positive integer")
    result: list[list[ReasoningStep]] = []
    for i in range(0, len(items), size):
        result.append(items[i : i + size])
    return result


def _expect_tracked_items(
    data: dict[str, object],
    field_name: str,
) -> tuple[Mapping[str, object], ...]:
    value = data.get(field_name)
    if not isinstance(value, list):
        raise ValueError(f"field '{field_name}' must be a list")
    raw = cast(list[object], value)
    result: list[dict[str, object]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"field '{field_name}' must contain objects")
        result.append(cast(dict[str, object], item))
    return tuple(result)


def _expect_mandates(
    data: dict[str, object],
    field_name: str,
) -> tuple[str, ...]:
    value = data.get(field_name)
    if not isinstance(value, list):
        raise ValueError(f"field '{field_name}' must be a list of strings")
    raw = cast(list[object], value)
    if not all(isinstance(item, str) for item in raw):
        raise ValueError(f"field '{field_name}' must be a list of strings")
    return tuple(cast(list[str], raw))


def _expect_str(data: dict[str, object], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str):
        raise ValueError(f"field '{field_name}' must be a string")
    return value


def _expect_optional_str(
    data: dict[str, object],
    field_name: str,
) -> str | None:
    if field_name not in data:
        raise ValueError(f"field '{field_name}' must be a string or null")
    value = data[field_name]
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"field '{field_name}' must be a string or null")
    return value


def _expect_str_list(
    data: dict[str, object],
    field_name: str,
) -> list[str]:
    value = data.get(field_name)
    if not isinstance(value, list):
        raise ValueError(f"field '{field_name}' must be a list of strings")
    raw = cast(list[object], value)
    if not all(isinstance(item, str) for item in raw):
        raise ValueError(f"field '{field_name}' must be a list of strings")
    return list(cast(list[str], raw))


def _expect_tool_logs(
    data: dict[str, object],
    field_name: str,
) -> tuple[Mapping[str, object], ...]:
    value = data.get(field_name)
    if not isinstance(value, list):
        raise ValueError(f"field '{field_name}' must be a list")
    result: list[dict[str, object]] = []
    for item in cast(list[object], value):
        if not isinstance(item, dict):
            raise ValueError(f"field '{field_name}' must contain objects")
        result.append(cast(dict[str, object], item))
    return tuple(result)


def _freeze_str_sequence(
    value: object,
    *,
    field_name: str,
) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise TypeError(f"field '{field_name}' must be a sequence of strings")
    items = cast(Sequence[object], value)
    if not all(isinstance(item, str) for item in items):
        raise TypeError(f"field '{field_name}' must be a sequence of strings")
    return tuple(cast(Sequence[str], items))


def _freeze_mapping_sequence(
    value: object,
    *,
    field_name: str,
) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"field '{field_name}' must be a tuple of mappings")
    items = cast(tuple[object, ...], value)
    frozen = freeze_json_value(items)
    if not isinstance(frozen, tuple):
        raise TypeError(f"field '{field_name}' must contain mappings")
    frozen_items = cast(tuple[object, ...], frozen)
    if not all(isinstance(item, Mapping) for item in frozen_items):
        raise TypeError(f"field '{field_name}' must contain mappings")
    return cast(tuple[Mapping[str, object], ...], frozen_items)


def _expect_optional_float(
    data: dict[str, object],
    field_name: str,
) -> float | None:
    if field_name not in data:
        raise ValueError(f"field '{field_name}' must be a number or null")
    value = data[field_name]
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"field '{field_name}' must be a number or null")
    if isinstance(value, int | float):
        return float(value)
    raise ValueError(f"field '{field_name}' must be a number or null")


def _expect_terminal_status(
    data: dict[str, object],
    field_name: str,
) -> TerminalStatus:
    value = _expect_str(data, field_name)
    if value in TERMINAL_STATUSES:
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


def _validate_optional_aware_iso(
    value: object,
    *,
    field_name: str,
) -> None:
    if value is None:
        return
    _validate_aware_iso(value, field_name=field_name)


def _validate_aware_iso(
    value: object,
    *,
    field_name: str,
) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"field '{field_name}' must be an ISO-8601 timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"field '{field_name}' must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"field '{field_name}' must include a timezone")
