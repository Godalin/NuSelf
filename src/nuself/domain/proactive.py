"""Proactive agent domain models: idea candidates and relevance scores."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

IdeaCandidateType = Literal[
    "contradiction",
    "connection",
    "question",
    "action",
    "profile_update",
    "share_bundle",
]


@dataclass(frozen=True)
class IdeaCandidate:
    """One proactive idea proposed for user attention."""

    id: str
    title: str
    body: str
    candidate_type: IdeaCandidateType
    confidence: float
    novelty: float
    urgency: float
    interruption_cost: float
    evidence_refs: tuple[str, ...]
    source_summary: str
    created_at: str

    def to_wire(self) -> dict[str, object]:
        wire: dict[str, object] = {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "candidate_type": self.candidate_type,
            "confidence": self.confidence,
            "novelty": self.novelty,
            "urgency": self.urgency,
            "interruption_cost": self.interruption_cost,
            "evidence_refs": list(self.evidence_refs),
            "source_summary": self.source_summary,
            "created_at": self.created_at,
        }
        return wire

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> "IdeaCandidate":
        return cls(
            id=_expect_str(data, "id"),
            title=_expect_str(data, "title"),
            body=_expect_str(data, "body"),
            candidate_type=_expect_candidate_type(data, "candidate_type"),
            confidence=_expect_float(data, "confidence"),
            novelty=_expect_float(data, "novelty"),
            urgency=_expect_float(data, "urgency"),
            interruption_cost=_expect_float(data, "interruption_cost"),
            evidence_refs=_string_tuple(data.get("evidence_refs")),
            source_summary=_expect_str(data, "source_summary"),
            created_at=_expect_str(data, "created_at"),
        )


@dataclass(frozen=True)
class RelevanceScore:
    """Multi-dimensional relevance assessment for one candidate."""

    passes: bool
    novelty: float
    confidence: float
    urgency: float
    interruption_cost: float
    cooldown_ok: bool
    composite: float
    reasons: tuple[str, ...]

    def to_wire(self) -> dict[str, object]:
        return {
            "passes": self.passes,
            "novelty": self.novelty,
            "confidence": self.confidence,
            "urgency": self.urgency,
            "interruption_cost": self.interruption_cost,
            "cooldown_ok": self.cooldown_ok,
            "composite": self.composite,
            "reasons": list(self.reasons),
        }

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> "RelevanceScore":
        return cls(
            passes=_expect_bool(data, "passes"),
            novelty=_expect_float(data, "novelty"),
            confidence=_expect_float(data, "confidence"),
            urgency=_expect_float(data, "urgency"),
            interruption_cost=_expect_float(data, "interruption_cost"),
            cooldown_ok=_expect_bool(data, "cooldown_ok"),
            composite=_expect_float(data, "composite"),
            reasons=_string_tuple(data.get("reasons")),
        )


# --- helpers ---


def _expect_str(data: dict[str, object], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str):
        raise ValueError(f"field '{field_name}' must be a string")
    return value


def _expect_float(data: dict[str, object], field_name: str) -> float:
    value = data.get(field_name)
    if isinstance(value, int):
        return float(value)
    if not isinstance(value, float):
        raise ValueError(f"field '{field_name}' must be a number")
    return value


def _expect_bool(data: dict[str, object], field_name: str) -> bool:
    value = data.get(field_name)
    if not isinstance(value, bool):
        raise ValueError(f"field '{field_name}' must be a boolean")
    return value


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    result: list[str] = []
    for item in cast(list[object], value):
        if isinstance(item, str) and item.strip() != "":
            result.append(item.strip())
    return tuple(result)


def _expect_candidate_type(data: dict[str, object], field_name: str) -> IdeaCandidateType:
    value = _expect_str(data, field_name)
    if value not in {"contradiction", "connection", "question", "action", "profile_update", "share_bundle"}:
        raise ValueError(f"unsupported candidate type: {value}")
    return cast(IdeaCandidateType, value)
