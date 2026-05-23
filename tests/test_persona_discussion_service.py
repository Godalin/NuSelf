from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nuself.domain.proactive import IdeaCandidate
from nuself.persona import SharedPersonaDiscussionService


@dataclass(frozen=True)
class _FakeResult:
    approved: bool = True
    winner_persona_ids: tuple[str, ...] = ("analyst_self",)
    revised_title: str = "Revised title"
    revised_body: str = "Revised body"
    scores: dict[str, float] = None  # type: ignore[assignment]
    blocking_vetos: tuple[str, ...] = ()
    reason: str = "delegated"
    discussion_trace: tuple[str, ...] = ("trace line",)
    emergent_persona_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.scores is None:  # type: ignore[reportUnnecessaryComparison]
            object.__setattr__(self, "scores", {"analyst_self": 0.9})


class _FakeDiscussion:
    def __init__(self) -> None:
        self.calls: list[IdeaCandidate] = []

    def discuss(self, candidate: IdeaCandidate, *, on_trace_entry: object | None = None) -> _FakeResult:
        self.calls.append(candidate)
        return _FakeResult()


def test_shared_persona_discussion_service_delegates_to_engine(tmp_path: Path) -> None:
    fake = _FakeDiscussion()
    service = SharedPersonaDiscussionService(project_root=tmp_path, discussion=fake)  # type: ignore[arg-type]
    candidate = IdeaCandidate(
        id="cand-1",
        title="Discuss architecture",
        body="We should compare two designs.",
        candidate_type="question",
        confidence=0.8,
        novelty=0.6,
        urgency=0.4,
        interruption_cost=0.2,
        evidence_refs=(),
        suggested_thread_id=None,
        source_summary="summary",
        created_at="2026-05-12T00:00:00Z",
    )

    result = service.discuss(candidate)

    assert fake.calls == [candidate]
    assert result.approved is True
    assert result.reason == "delegated"
    assert result.winner_persona_ids == ("analyst_self",)
