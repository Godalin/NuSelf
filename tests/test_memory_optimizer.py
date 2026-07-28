from __future__ import annotations

from pathlib import Path

from nuself.domain.memory import MemoryEntry
from nuself.domain.profile import ProfileItem
from nuself.llm import ChatMessage
from nuself.memory.optimizer import MemoryOptimizer, MemoryOptimizerSettings
from nuself.memory.repository import MemoryCandidateRepository, MemoryEntryRepository
from nuself.profile.repository import ProfileItemRepository


class FakeOptimizerLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[list[ChatMessage]] = []

    def complete(self, messages: list[ChatMessage]) -> str:
        self.calls.append(messages)
        return self.response


def test_memory_optimizer_updates_and_deletes_duplicate_entries(tmp_path: Path) -> None:
    repo = MemoryEntryRepository(tmp_path)
    keeper = repo.save(
        MemoryEntry(
            type="belief",
            title="Memory strategy",
            body="Memory should be curated by an agent.",
            tags=["memory"],
            review_state="reviewed",
        )
    )
    duplicate = repo.save(
        MemoryEntry(
            type="episode",
            title="Memory note",
            body="We discussed that memory updates need agent decisions.",
            tags=["memory"],
        )
    )
    llm = FakeOptimizerLLM(
        '{"actions":[{"action":"update","entry_id":"'
        + keeper.id
        + '","type":"belief","title":"Memory strategy",'
        '"body":"NuSelf memory updates should be decided by an agent, applied as structured actions, '
        'and kept as concise long-term summaries rather than raw chat transcripts.",'
        '"tags":["memory","curation"],"confidence":0.86,"reason":"merged overlapping entries"},'
        '{"action":"delete","entry_id":"'
        + duplicate.id
        + '","reason":"fully merged into '
        + keeper.id
        + '"}]}'
    )
    optimizer = MemoryOptimizer(tmp_path, llm=llm, repository=repo)

    result = optimizer.run_once()
    entries = repo.list()
    candidates = MemoryCandidateRepository(tmp_path).list()

    assert result.reviewed == 2
    assert result.updated == 1
    assert result.deleted == 1
    assert len(entries) == 2
    assert len(candidates) == 2
    assert candidates[0].action in {"update", "delete"}
    assert {candidate.action for candidate in candidates} == {"update", "delete"}
    update_candidate = next(candidate for candidate in candidates if candidate.action == "update")
    assert update_candidate.body.startswith("NuSelf memory updates should be decided by an agent")
    assert update_candidate.tags == ("memory", "curation")
    assert update_candidate.target_entry_id == keeper.id
    assert update_candidate.source_refs[0].startswith("memory_optimize:")
    assert "memory_optimizer reviewed=2 updated=1 deleted=1 ignored=0" in result.log_path.read_text(encoding="utf-8")


def test_memory_optimizer_includes_profile_context_in_prompt(tmp_path: Path) -> None:
    repo = MemoryEntryRepository(tmp_path)
    repo.save(MemoryEntry(type="belief", title="Keep memory concise", body="The user wants concise memory entries."))
    profile_repo = ProfileItemRepository(tmp_path)
    profile_repo.save(
        ProfileItem(
            type="profile_fact",
            title="Concise output",
            body="Prefers concise command output.",
            tags=["cli"],
            source_refs=["source:profile:0"],
        )
    )
    llm = FakeOptimizerLLM('{"actions":[{"action":"ignore","entry_id":"unused","reason":"no changes"}]}')
    optimizer = MemoryOptimizer(tmp_path, llm=llm, repository=repo, profile_repository=profile_repo)

    optimizer.run_once()

    system_prompt, user_prompt = llm.calls[0]
    assert "Consider existing profile items" in system_prompt.content
    assert "Existing profile items:" in user_prompt.content
    assert "Concise output" in user_prompt.content


def test_memory_optimizer_defers_without_agent_decision(tmp_path: Path) -> None:
    repo = MemoryEntryRepository(tmp_path)
    entry = repo.save(
        MemoryEntry(
            type="belief",
            title="Keep memory concise",
            body="The user wants concise memory entries.",
        )
    )
    class FailingOptimizerLLM:
        def complete(self, messages: list[ChatMessage]) -> str:
            raise RuntimeError("LLM unavailable")

    optimizer = MemoryOptimizer(tmp_path, llm=FailingOptimizerLLM(), repository=repo)

    result = optimizer.run_once()

    assert result.reviewed == 0
    assert result.updated == 0
    assert result.deleted == 0
    assert repo.get(entry.id).body == "The user wants concise memory entries."


def test_memory_optimizer_rejects_raw_transcript_body(tmp_path: Path) -> None:
    repo = MemoryEntryRepository(tmp_path)
    entry = repo.save(
        MemoryEntry(
            type="episode",
            title="Messy transcript",
            body="A messy memory entry.",
        )
    )
    llm = FakeOptimizerLLM(
        '{"actions":[{"action":"update","entry_id":"'
        + entry.id
        + '","title":"Raw transcript","body":"user: hello assistant: hi",'
        '"reason":"bad transcript"}]}'
    )
    optimizer = MemoryOptimizer(tmp_path, llm=llm, repository=repo)

    result = optimizer.run_once()

    assert result.reviewed == 0
    assert repo.get(entry.id).title == "Messy transcript"


def test_memory_optimizer_uses_registry_memory_types(tmp_path: Path) -> None:
    repo = MemoryEntryRepository(tmp_path)
    entry = repo.save(
        MemoryEntry(
            type="instruction",
            title="Old instruction",
            body="Old instruction body.",
        )
    )
    llm = FakeOptimizerLLM(
        '{"actions":[{"action":"update","entry_id":"'
        + entry.id
        + '","type":"persona_instruction","title":"Persona instruction",'
        '"body":"Use persona instructions as durable behavior guidance.",'
        '"tags":["persona"],"confidence":0.8,"reason":"new typed memory type"}]}'
    )
    optimizer = MemoryOptimizer(tmp_path, llm=llm, repository=repo)

    result = optimizer.run_once()
    candidates = MemoryCandidateRepository(tmp_path).list()

    assert result.updated == 1
    assert candidates[0].type == "persona_instruction"


def test_memory_optimizer_rejects_unknown_memory_type(tmp_path: Path) -> None:
    repo = MemoryEntryRepository(tmp_path)
    entry = repo.save(
        MemoryEntry(
            type="belief",
            title="Known type",
            body="Known type body.",
        )
    )
    llm = FakeOptimizerLLM(
        '{"actions":[{"action":"update","entry_id":"'
        + entry.id
        + '","type":"made_up_type","title":"Bad type",'
        '"body":"Unknown memory types should not be silently accepted.",'
        '"tags":["memory"],"confidence":0.8,"reason":"bad type"}]}'
    )
    optimizer = MemoryOptimizer(tmp_path, llm=llm, repository=repo)

    result = optimizer.run_once()

    assert result.reviewed == 0
    assert MemoryCandidateRepository(tmp_path).list() == []


def test_memory_optimizer_respects_limit(tmp_path: Path) -> None:
    repo = MemoryEntryRepository(tmp_path)
    for title in ["First", "Second"]:
        repo.save(MemoryEntry(type="belief", title=title, body=f"{title} body."))
    llm = FakeOptimizerLLM('{"actions":[{"action":"ignore","entry_id":"unused","reason":"no changes"}]}')
    optimizer = MemoryOptimizer(
        tmp_path,
        llm=llm,
        repository=repo,
        settings=MemoryOptimizerSettings(memory_limit=1),
    )

    result = optimizer.run_once()

    assert result.reviewed == 1
