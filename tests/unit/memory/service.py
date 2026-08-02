from __future__ import annotations

# pyright: reportUnusedImport=false

from memory_fixtures import (
    memory_candidate_repository,
    memory_entry_repository,
    source_repository,
)

from pathlib import Path

from nuself.config import runtime_paths
from nuself.memory.model import MemoryEntry
from nuself.profile.model import ProfileItem
from nuself.memory.service import MemoryQuery, MemoryService
from nuself.memory.repository import MemoryEntryRepository
from nuself.memory.source_repository import SourceRepository
from nuself.profile.repository import ProfileItemRepository
from tests.backend import owned_backend


def test_memory_query_ranks_relevant_entries_with_reasons(tmp_path: Path) -> None:
    repo = memory_entry_repository(tmp_path)
    relevant = repo.save(
        MemoryEntry(
            type="belief",
            title="Clarity matters",
            body="Prefer explicit assumptions.",
            tags=["style"],
            review_state="reviewed",
        )
    )
    repo.save(
        MemoryEntry(
            type="episode",
            title="Unrelated dinner note",
            body="We talked about food.",
            tags=["daily"],
        )
    )
    service = MemoryService(repo)

    matches = service.search(MemoryQuery(text="clarity and assumptions"))

    assert [match.entry.id for match in matches] == [relevant.id]
    assert "title" in matches[0].reasons
    assert "body" in matches[0].reasons
    assert "reviewed" in matches[0].reasons


def test_memory_query_packs_context_with_metadata(tmp_path: Path) -> None:
    repo = memory_entry_repository(tmp_path)
    entry = repo.save(
        MemoryEntry(
            type="style_trait",
            title="Direct style",
            body="Prefer direct answers.",
            tags=["style"],
            observed_at="2026-05-07T10:00:00+00:00",
            valid_from="2026-05-07",
            temporal_note="Observed during CLI output discussion.",
        )
    )
    service = MemoryService(repo)

    packed = service.pack(MemoryQuery(text="direct style"))

    assert len(packed.matches) == 1
    assert entry.id in packed.text
    assert "Memory entries:" in packed.text
    assert "type=style_trait" in packed.text
    assert "observed_at=2026-05-07T10:00:00+00:00" in packed.text
    assert "valid_from=2026-05-07" in packed.text
    assert "updated_at=" in packed.text
    assert "temporal_note=Observed during CLI output discussion." in packed.text
    assert "match=" in packed.text


def test_memory_query_packs_source_chunks_with_references(tmp_path: Path) -> None:
    source_path = tmp_path / "source.md"
    source_path.write_text(
        "\n".join(
            [
                "---",
                "title: Source Context",
                "tags: [retrieval]",
                "date: 2026-05-08",
                "---",
                "Source chunks provide durable evidence.",
            ]
        ),
        encoding="utf-8",
    )
    entry_repo = memory_entry_repository(tmp_path)
    source_repo = source_repository(tmp_path)
    source_repo.ingest_path(source_path)
    service = MemoryService(entry_repo, source_repo)

    packed = service.pack(MemoryQuery(text="durable evidence"))

    assert packed.matches == ()
    assert len(packed.source_matches) == 1
    assert "Source chunks:" in packed.text
    assert "Source Context" in packed.text
    assert "ref=source:" in packed.text
    assert "source_date=2026-05-08" in packed.text
    assert "updated_at=" in packed.text
    assert "Source chunks provide durable evidence." in packed.text


def test_memory_query_packs_profile_items_with_references(tmp_path: Path) -> None:
    entry_repo = memory_entry_repository(tmp_path)
    profile_repo = ProfileItemRepository(runtime_paths(tmp_path), backend=owned_backend(tmp_path))
    profile_repo.save(
        ProfileItem(
            type="profile_fact",
            title="Concise output",
            body="Prefers concise command output.",
            tags=["cli", "style"],
            source_refs=["source:profile:0"],
            observed_at="2026-05-07",
        )
    )
    service = MemoryService(entry_repo, profile_repository=profile_repo)

    packed = service.pack(MemoryQuery(text="concise command"))

    assert len(packed.profile_matches) == 1
    assert packed.matches == ()
    assert "Profile items:" in packed.text
    assert "Concise output" in packed.text
    assert "source:profile:0" in packed.text
    assert "observed_at=2026-05-07" in packed.text


def test_memory_query_returns_empty_context_for_irrelevant_query(tmp_path: Path) -> None:
    repo = memory_entry_repository(tmp_path)
    repo.save(
        MemoryEntry(
            type="belief",
            title="Clarity matters",
            body="Prefer explicit assumptions.",
            tags=["style"],
        )
    )
    service = MemoryService(repo)

    packed = service.pack(MemoryQuery(text="weather forecast"))

    assert packed.text == ""
    assert packed.matches == ()


def test_memory_query_includes_profile_items_in_default_chat_context(tmp_path: Path) -> None:
    profile_repo = ProfileItemRepository(runtime_paths(tmp_path), backend=owned_backend(tmp_path))
    profile_repo.save(
        ProfileItem(
            type="profile_fact",
            title="Direct style",
            body="Prefer direct answers.",
            tags=["style"],
            source_refs=["source:profile:0"],
        )
    )
    service = MemoryService(memory_entry_repository(tmp_path), profile_repository=profile_repo)

    packed = service.pack(MemoryQuery(text="direct answers"))

    assert len(packed.profile_matches) == 1
    assert "Profile items:" in packed.text
    assert "Direct style" in packed.text


def test_memory_query_uses_type_descriptor_affinity(tmp_path: Path) -> None:
    repo = memory_entry_repository(tmp_path)
    style = repo.save(
        MemoryEntry(
            type="style_trait",
            title="Concise output",
            body="Keep answers compact and direct.",
            tags=["communication"],
            review_state="reviewed",
        )
    )
    repo.save(
        MemoryEntry(
            type="belief",
            title="Architecture boundary",
            body="File-backed memory is authoritative.",
            tags=["architecture"],
            review_state="reviewed",
        )
    )
    service = MemoryService(repo)

    matches = service.search(MemoryQuery(text="how should you respond"))

    assert [match.entry.id for match in matches] == [style.id]
    assert "type_descriptor" in matches[0].reasons


def test_memory_query_filters_by_type_and_tag(tmp_path: Path) -> None:
    repo = memory_entry_repository(tmp_path)
    repo.save(
        MemoryEntry(
            type="belief",
            title="Clarity matters",
            body="Prefer explicit assumptions.",
            tags=["style"],
            review_state="reviewed",
        )
    )
    goal = repo.save(
        MemoryEntry(
            type="goal",
            title="LangGraph preparation",
            body="Prepare memory tools before graph migration.",
            tags=["runtime"],
            review_state="reviewed",
        )
    )
    service = MemoryService(repo)

    matches = service.search(MemoryQuery(text="current goal", memory_types=("goal",), tags=("runtime",)))

    assert [match.entry.id for match in matches] == [goal.id]
    assert "type_descriptor" in matches[0].reasons


def test_memory_query_expands_related_entries(tmp_path: Path) -> None:
    repo = memory_entry_repository(tmp_path)
    related = repo.save(
        MemoryEntry(
            type="concept",
            title="Descriptor retrieval",
            body="Use type descriptors to shape retrieval.",
            tags=["memory"],
            review_state="reviewed",
        )
    )
    direct = repo.save(
        MemoryEntry(
            type="goal",
            title="Current memory goal",
            body="Improve retrieval before graph migration.",
            tags=["memory"],
            relations={"related_to": [related.id]},
            review_state="reviewed",
        )
    )
    service = MemoryService(repo)

    matches = service.search(MemoryQuery(text="current goal", limit=4))

    assert [match.entry.id for match in matches] == [direct.id, related.id]
    assert matches[1].reasons == (f"related_to:{direct.id}",)


def test_memory_query_expands_superseded_by_entries(tmp_path: Path) -> None:
    repo = memory_entry_repository(tmp_path)
    old = repo.save(
        MemoryEntry(
            type="belief",
            title="Legacy category model",
            body="Memory categories are fixed.",
            tags=["memory"],
            review_state="reviewed",
        )
    )
    replacement = repo.save(
        MemoryEntry(
            type="belief",
            title="Open typed memory model",
            body="Memory types are descriptor-backed and open.",
            tags=["memory"],
            relations={"supersedes": [old.id]},
            review_state="reviewed",
        )
    )
    service = MemoryService(repo)

    matches = service.search(MemoryQuery(text="legacy fixed categories", limit=4))

    assert [match.entry.id for match in matches] == [old.id, replacement.id]
    assert matches[1].reasons == (f"superseded_by:{old.id}",)


def test_memory_query_respects_retrieval_rule_score_penalty(tmp_path: Path) -> None:
    repo = memory_entry_repository(tmp_path)
    superseded = repo.save(
        MemoryEntry(
            type="belief",
            title="Old model",
            body="Closed categories.",
            review_state="reviewed",
        )
    )
    neighbor = repo.save(
        MemoryEntry(
            type="concept",
            title="Neighbor concept",
            body="Just a linked idea.",
            review_state="reviewed",
        )
    )
    current = repo.save(
        MemoryEntry(
            type="belief",
            title="Open descriptor model",
            body="Types are descriptor-backed.",
            review_state="reviewed",
            relations={"supersedes": [superseded.id], "related_to": [neighbor.id]},
        )
    )
    service = MemoryService(repo)

    matches = service.search(MemoryQuery(text="descriptor", limit=4))

    assert matches[0].entry.id == current.id
    superseded_match = next(m for m in matches if m.entry.id == superseded.id)
    neighbor_match = next(m for m in matches if m.entry.id == neighbor.id)
    assert superseded_match.score > neighbor_match.score


def test_memory_query_expands_transitive_relation_closure(tmp_path: Path) -> None:
    repo = memory_entry_repository(tmp_path)
    root = repo.save(
        MemoryEntry(
            type="goal",
            title="Build graph retrieval",
            body="Wire graph traversal into memory retrieval.",
            review_state="reviewed",
        )
    )
    dependency = repo.save(
        MemoryEntry(
            type="goal",
            title="Build index",
            body="Create the projection.",
            review_state="reviewed",
        )
    )
    deep_dependency = repo.save(
        MemoryEntry(
            type="goal",
            title="Define relations",
            body="Register symbolic behavior.",
            review_state="reviewed",
        )
    )
    repo.save(
        MemoryEntry(
            type=root.type,
            title=root.title,
            body=root.body,
            id=root.id,
            review_state=root.review_state,
            relations={"depends_on": [dependency.id]},
        )
    )
    repo.save(
        MemoryEntry(
            type=dependency.type,
            title=dependency.title,
            body=dependency.body,
            id=dependency.id,
            review_state=dependency.review_state,
            relations={"depends_on": [deep_dependency.id]},
        )
    )
    service = MemoryService(repo)

    matches = service.search(MemoryQuery(text="graph retrieval", limit=6))

    assert [match.entry.id for match in matches] == [root.id, dependency.id, deep_dependency.id]
    assert matches[1].reasons == (f"depends_on:{root.id}",)
    assert matches[2].reasons == (f"depends_on_closure:{root.id}",)


def test_memory_query_uses_registry_retrieve_to_filter_types(tmp_path: Path) -> None:
    from nuself.memory.model import (
        MemoryObject,
        MemoryTypeRegistry,
        MemoryValidationIssue,
    )

    class HidingBeliefDescriptor:
        @property
        def type(self) -> str:
            return "belief"

        @property
        def description(self) -> str:
            return "hides on 'hide' query"

        def validate(self, memory: MemoryObject) -> list[MemoryValidationIssue]:
            return []

        def summarize(self, memory: MemoryObject) -> str:
            return "belief"

        def merge(self, existing: MemoryObject, incoming: MemoryObject) -> MemoryObject:
            return incoming

        def conflicts(self, a: MemoryObject, b: MemoryObject) -> bool:
            return False

        def importance(self, memory: MemoryObject) -> float:
            return memory.importance

        def decay(self, memory: MemoryObject, now: str) -> MemoryObject | None:
            return memory

        def retrieve(self, query: str, budget: int) -> bool:
            return "hide" not in query.casefold()

        def reflect(self, memory: MemoryObject, context: str) -> list[MemoryObject]:
            return []

        def example(self) -> MemoryObject:
            return MemoryObject(type=self.type, payload={"title": "Example", "body": "B"})

    repo = memory_entry_repository(tmp_path)
    belief = repo.save(
        MemoryEntry(
            type="belief",
            title="Hidden belief",
            body="This visible belief should be hidden when query contains hide.",
            review_state="reviewed",
        )
    )
    preference = repo.save(
        MemoryEntry(
            type="preference",
            title="Visible preference",
            body="This preference is a belief that should always be visible.",
            review_state="reviewed",
        )
    )
    registry = MemoryTypeRegistry([HidingBeliefDescriptor()])
    service = MemoryService(repo, registry=registry)

    normal_matches = service.search(MemoryQuery(text="visible", limit=6))
    hidden_matches = service.search(MemoryQuery(text="hide belief", limit=6))

    assert any(match.entry.id == belief.id for match in normal_matches)
    assert not any(match.entry.id == belief.id for match in hidden_matches)
    assert any(match.entry.id == preference.id for match in hidden_matches)


def test_query_uses_importance_in_scoring(tmp_path: Path) -> None:
    repo = memory_entry_repository(tmp_path)
    low = repo.save(
        MemoryEntry(
            type="episode",
            title="Low importance note",
            body="This has low importance.",
            importance=0.1,
            review_state="reviewed",
        )
    )
    high = repo.save(
        MemoryEntry(
            type="episode",
            title="High importance note",
            body="This has high importance.",
            importance=0.9,
            review_state="reviewed",
        )
    )
    service = MemoryService(repo)
    matches = service.search(MemoryQuery(text="note", limit=6))
    high_match = next(m for m in matches if m.entry.id == high.id)
    low_match = next(m for m in matches if m.entry.id == low.id)
    assert high_match.score > low_match.score
    assert "importance" in high_match.reasons
    assert "importance" in low_match.reasons


def test_query_filters_by_min_importance(tmp_path: Path) -> None:
    repo = memory_entry_repository(tmp_path)
    low = repo.save(
        MemoryEntry(
            type="episode",
            title="Low importance note",
            body="This has low importance.",
            importance=0.1,
            review_state="reviewed",
        )
    )
    high = repo.save(
        MemoryEntry(
            type="episode",
            title="High importance note",
            body="This has high importance.",
            importance=0.9,
            review_state="reviewed",
        )
    )
    service = MemoryService(repo)
    all_matches = service.search(MemoryQuery(text="note", limit=6))
    assert len(all_matches) == 2

    filtered = service.search(MemoryQuery(text="note", limit=6, min_importance=0.5))
    assert len(filtered) == 1
    assert filtered[0].entry.id == high.id
    assert not any(match.entry.id == low.id for match in filtered)
