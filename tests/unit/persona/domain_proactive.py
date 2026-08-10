"""Tests for proactive domain models."""

from __future__ import annotations

import pytest

from nuself.reflection.model import EvidenceExcerpt, IdeaCandidate, RelevanceScore


def test_idea_candidate_round_trip() -> None:
    original = IdeaCandidate(
        id="c1",
        title="Test Candidate",
        body="A body",
        candidate_type="connection",
        confidence=0.8,
        novelty=0.7,
        urgency=0.6,
        interruption_cost=0.3,
        evidence_refs=("ref-1", "ref-2"),
        source_summary="summary",
        created_at="2024-01-01T00:00:00",
        evidence_excerpts=(
            EvidenceExcerpt("ref-1", "First evidence excerpt"),
            EvidenceExcerpt("ref-2", "Second evidence excerpt"),
        ),
    )
    wire = original.to_wire()
    restored = IdeaCandidate.from_wire(wire)
    assert restored == original


def test_idea_candidate_wire_has_no_conversation_identity() -> None:
    original = IdeaCandidate(
        id="c2",
        title="No Conversation",
        body="Body",
        candidate_type="question",
        confidence=0.5,
        novelty=0.5,
        urgency=0.5,
        interruption_cost=0.5,
        evidence_refs=(),
        source_summary="",
        created_at="2024-01-01T00:00:00",
    )
    wire = original.to_wire()
    assert "suggested_conversation_id" not in wire
    restored = IdeaCandidate.from_wire(wire)
    assert restored == original


def test_idea_candidate_invalid_type_raises() -> None:
    with pytest.raises(ValueError, match="unsupported candidate type"):
        IdeaCandidate.from_wire(
            {
                "id": "c1",
                "title": "T",
                "body": "B",
                "candidate_type": "invalid",
                "confidence": 0.5,
                "novelty": 0.5,
                "urgency": 0.5,
                "interruption_cost": 0.5,
                "evidence_refs": [],
                "source_summary": "",
                "created_at": "2024-01-01T00:00:00",
            }
        )


def test_relevance_score_round_trip() -> None:
    original = RelevanceScore(
        passes=True,
        novelty=0.8,
        confidence=0.7,
        urgency=0.6,
        interruption_cost=0.2,
        cooldown_ok=True,
        composite=0.75,
        reasons=("novel", "high_confidence"),
    )
    wire = original.to_wire()
    restored = RelevanceScore.from_wire(wire)
    assert restored == original


def test_relevance_score_invalid_bool_raises() -> None:
    with pytest.raises(ValueError, match="must be a boolean"):
        RelevanceScore.from_wire(
            {
                "passes": "yes",
                "novelty": 0.5,
                "confidence": 0.5,
                "urgency": 0.5,
                "interruption_cost": 0.5,
                "cooldown_ok": True,
                "composite": 0.5,
                "reasons": [],
            }
        )
