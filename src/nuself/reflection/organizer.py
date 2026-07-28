"""Reflection organizer for merging similar pending ideas."""

from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path

from nuself.reflection.repository import ReflectionEntry, ReflectionRepository
from nuself.runtime.observability import write_observed_log_event

SIMILARITY_THRESHOLD = 0.48


@dataclass(frozen=True)
class ReflectionOrganizationResult:
    """Summary of one organization pass."""

    merged_groups: int
    archived_entries: int


class ReflectionOrganizer:
    """Best-effort cleanup routine for pending reflection ideas."""

    def __init__(self, project_root: Path | None = None, repository: ReflectionRepository | None = None) -> None:
        self._project_root = project_root
        self._repository = repository or ReflectionRepository(project_root)

    def organize_pending(self) -> ReflectionOrganizationResult:
        pending = self._repository.list(status="pending")
        groups = _similar_groups(pending)
        archived_count = 0

        for group in groups:
            primary = _primary_entry(group)
            duplicates = [entry for entry in group if entry.id != primary.id]
            if not duplicates:
                continue
            self._repository.update(_merge_entries(primary, duplicates))
            for entry in duplicates:
                self._repository.archive(entry.id)
            archived_count += len(duplicates)

        result = ReflectionOrganizationResult(
            merged_groups=sum(1 for group in groups if len(group) > 1),
            archived_entries=archived_count,
        )
        if result.archived_entries:
            write_observed_log_event(
                "reflection",
                "organizer_completed",
                "reflection organizer merged similar pending entries",
                project_root=self._project_root,
                metadata={
                    "merged_groups": result.merged_groups,
                    "archived_entries": result.archived_entries,
                },
                status="completed",
                failure_event="organizer_audit_write_failed",
                failure_message="Could not record completed reflection organization",
                failure_metadata={
                    "merged_groups": result.merged_groups,
                    "archived_entries": result.archived_entries,
                },
            )
        return result


def _similar_groups(entries: list[ReflectionEntry]) -> list[list[ReflectionEntry]]:
    groups: list[list[ReflectionEntry]] = []
    assigned: set[str] = set()
    for entry in entries:
        if entry.id in assigned:
            continue
        group = [entry]
        assigned.add(entry.id)
        for other in entries:
            if other.id in assigned:
                continue
            if _similarity(entry, other) >= SIMILARITY_THRESHOLD:
                group.append(other)
                assigned.add(other.id)
        groups.append(group)
    return groups


def _primary_entry(entries: list[ReflectionEntry]) -> ReflectionEntry:
    return max(entries, key=lambda entry: (entry.composite_score, entry.confidence, entry.created_at, entry.id))


def _merge_entries(primary: ReflectionEntry, duplicates: list[ReflectionEntry]) -> ReflectionEntry:
    notes: list[str] = []
    for entry in sorted(duplicates, key=lambda item: (item.created_at, item.id)):
        snippet = " ".join(entry.body.split())
        if len(snippet) > 180:
            snippet = snippet[:177].rstrip() + "..."
        notes.append(f"- {entry.title}: {snippet}")
    body = primary.body
    if notes:
        body = "\n\nMerged similar reflection notes:\n" + "\n".join(notes) if body == "" else (
            body + "\n\nMerged similar reflection notes:\n" + "\n".join(notes)
        )
    return ReflectionEntry(
        id=primary.id,
        title=primary.title,
        body=body,
        candidate_type=primary.candidate_type,
        confidence=max([primary.confidence, *(entry.confidence for entry in duplicates)]),
        novelty=max([primary.novelty, *(entry.novelty for entry in duplicates)]),
        urgency=max([primary.urgency, *(entry.urgency for entry in duplicates)]),
        interruption_cost=min([primary.interruption_cost, *(entry.interruption_cost for entry in duplicates)]),
        composite_score=max([primary.composite_score, *(entry.composite_score for entry in duplicates)]),
        status="pending",
        discussion_approved=primary.discussion_approved,
        discussion_trace=primary.discussion_trace,
        deep_link=primary.deep_link,
        created_at=primary.created_at,
        reviewed_at=None,
    )


def _similarity(left: ReflectionEntry, right: ReflectionEntry) -> float:
    left_tokens = _tokens(f"{left.title} {left.body}")
    right_tokens = _tokens(f"{right.title} {right.body}")
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    return overlap / union


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9_\u4e00-\u9fff]+", text.casefold())
        if len(token) >= 2 and token not in _STOPWORDS
    }


_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "your",
    "you",
    "are",
    "可以",
    "一个",
    "这个",
    "那个",
    "我们",
}
