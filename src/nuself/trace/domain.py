"""Trace domain models."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, TypeAlias, cast
from uuid import uuid4

from nuself.clock import utc_now, utc_now_iso
from nuself.runtime.messages import freeze_json_value, thaw_json_value

TraceKind: TypeAlias = Literal[
    "chat_turn",
    "memory_update",
    "reflection",
    "reason_thread",
    "reason_step",
    "promotion",
    "decision",
    "persona_prompt_created",
    "persona_disabled",
    "persona_enabled",
]
TraceVisibility: TypeAlias = Literal["private", "shareable", "internal"]
TraceRelation: TypeAlias = Literal[
    "supports",
    "derived",
    "contradicts",
    "revises",
    "summarizes",
    "triggered",
    "cites",
]

TRACE_KINDS: tuple[TraceKind, ...] = (
    "chat_turn",
    "memory_update",
    "reflection",
    "reason_thread",
    "reason_step",
    "promotion",
    "decision",
    "persona_prompt_created",
    "persona_disabled",
    "persona_enabled",
)
TRACE_VISIBILITIES: tuple[TraceVisibility, ...] = ("private", "shareable", "internal")
TRACE_RELATIONS: tuple[TraceRelation, ...] = (
    "supports",
    "derived",
    "contradicts",
    "revises",
    "summarizes",
    "triggered",
    "cites",
)


def new_trace_id() -> str:
    return f"trace-{_timestamp_id()}-{uuid4().hex[:8]}"


def new_trace_link_id() -> str:
    return f"tracelink-{_timestamp_id()}-{uuid4().hex[:8]}"


def _timestamp_id() -> str:
    return utc_now().strftime("%Y%m%dT%H%M%S%fZ")


@dataclass(frozen=True)
class ThoughtTrace:
    """One durable thought provenance record."""

    kind: TraceKind
    title: str
    summary: str
    id: str = field(default_factory=new_trace_id)
    inputs: Sequence[str] = ()
    evidence_refs: Sequence[str] = ()
    derived_from: Sequence[str] = ()
    outputs: Sequence[str] = ()
    participants: Sequence[str] = ()
    decision_points: Sequence[str] = ()
    conversation_id: str | None = None
    visibility: TraceVisibility = "private"
    created_at: str = field(default_factory=utc_now_iso)
    metadata: Mapping[str, object] = field(
        default_factory=dict[str, object]
    )

    def __post_init__(self) -> None:
        if self.kind not in TRACE_KINDS:
            raise ValueError(f"invalid trace kind: {self.kind}")
        if self.visibility not in TRACE_VISIBILITIES:
            raise ValueError(f"invalid trace visibility: {self.visibility}")
        if self.title.strip() == "":
            raise ValueError("trace title must not be empty")
        if self.summary.strip() == "":
            raise ValueError("trace summary must not be empty")
        for field_name in (
            "inputs",
            "evidence_refs",
            "derived_from",
            "outputs",
            "participants",
            "decision_points",
        ):
            object.__setattr__(
                self,
                field_name,
                _freeze_str_sequence(
                    getattr(self, field_name),
                    field_name=field_name,
                ),
            )
        object.__setattr__(
            self,
            "metadata",
            _freeze_metadata(self.metadata, field_name="metadata"),
        )

    def to_wire(self) -> dict[str, object]:
        record = {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "summary": self.summary,
            "inputs": self.inputs,
            "evidence_refs": self.evidence_refs,
            "derived_from": self.derived_from,
            "outputs": self.outputs,
            "participants": self.participants,
            "decision_points": self.decision_points,
            "conversation_id": self.conversation_id,
            "visibility": self.visibility,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }
        return cast(dict[str, object], thaw_json_value(record))

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> "ThoughtTrace":
        return cls(
            id=_expect_str(data, "id"),
            kind=_expect_trace_kind(data, "kind"),
            title=_expect_str(data, "title"),
            summary=_expect_str(data, "summary"),
            inputs=_optional_str_list(data, "inputs"),
            evidence_refs=_optional_str_list(data, "evidence_refs"),
            derived_from=_optional_str_list(data, "derived_from"),
            outputs=_optional_str_list(data, "outputs"),
            participants=_optional_str_list(data, "participants"),
            decision_points=_optional_str_list(data, "decision_points"),
            conversation_id=_optional_str(data, "conversation_id"),
            visibility=_expect_trace_visibility(data, "visibility"),
            created_at=_expect_str(data, "created_at"),
            metadata=_optional_dict(data, "metadata"),
        )


@dataclass(frozen=True)
class TraceLink:
    """One relationship between traces or external artifacts."""

    source_id: str
    target_id: str
    relation: TraceRelation
    summary: str
    id: str = field(default_factory=new_trace_link_id)
    created_at: str = field(default_factory=utc_now_iso)
    metadata: Mapping[str, object] = field(
        default_factory=dict[str, object]
    )

    def __post_init__(self) -> None:
        if self.source_id.strip() == "":
            raise ValueError("trace link source_id must not be empty")
        if self.target_id.strip() == "":
            raise ValueError("trace link target_id must not be empty")
        if self.relation not in TRACE_RELATIONS:
            raise ValueError(f"invalid trace relation: {self.relation}")
        if self.summary.strip() == "":
            raise ValueError("trace link summary must not be empty")
        object.__setattr__(
            self,
            "metadata",
            _freeze_metadata(self.metadata, field_name="metadata"),
        )

    def to_wire(self) -> dict[str, object]:
        record = {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation": self.relation,
            "summary": self.summary,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }
        return cast(dict[str, object], thaw_json_value(record))

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> "TraceLink":
        return cls(
            id=_expect_str(data, "id"),
            source_id=_expect_str(data, "source_id"),
            target_id=_expect_str(data, "target_id"),
            relation=_expect_trace_relation(data, "relation"),
            summary=_expect_str(data, "summary"),
            created_at=_expect_str(data, "created_at"),
            metadata=_optional_dict(data, "metadata"),
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


def _optional_dict(
    data: dict[str, object],
    field_name: str,
) -> Mapping[str, object]:
    value = data.get(field_name)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"field '{field_name}' must be an object")
    return cast(dict[str, object], value)


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


def _freeze_metadata(
    value: object,
    *,
    field_name: str,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"field '{field_name}' must be a mapping")
    mapping = cast(Mapping[object, object], value)
    frozen = freeze_json_value(mapping)
    if not isinstance(frozen, Mapping):
        raise TypeError(f"field '{field_name}' must be a mapping")
    return cast(Mapping[str, object], frozen)


def _expect_trace_kind(data: dict[str, object], field_name: str) -> TraceKind:
    value = _expect_str(data, field_name)
    if value not in TRACE_KINDS:
        raise ValueError(f"field '{field_name}' must be a trace kind")
    return value


def _expect_trace_visibility(data: dict[str, object], field_name: str) -> TraceVisibility:
    value = _expect_str(data, field_name)
    if value not in TRACE_VISIBILITIES:
        raise ValueError(f"field '{field_name}' must be a trace visibility")
    return value


def _expect_trace_relation(data: dict[str, object], field_name: str) -> TraceRelation:
    value = _expect_str(data, field_name)
    if value not in TRACE_RELATIONS:
        raise ValueError(f"field '{field_name}' must be a trace relation")
    return value
