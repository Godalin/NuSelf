from __future__ import annotations

from pathlib import Path

from nuself.domain.memory import MemoryEntry
from nuself.llm import ChatMessage
from nuself.memory.optimizer import MemoryOptimizer, MemoryOptimizerSettings
from nuself.memory.repository import MemoryEntryRepository


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
    updated = repo.get(keeper.id)

    assert result.reviewed == 2
    assert result.updated == 1
    assert result.deleted == 1
    assert len(entries) == 1
    assert updated.body.startswith("NuSelf memory updates should be decided by an agent")
    assert updated.tags == ["memory", "curation"]
    assert updated.review_state == "draft"
    assert updated.source_refs[0].startswith("memory_optimize:")
    assert "memory_optimizer reviewed=2 updated=1 deleted=1 ignored=0" in result.log_path.read_text(encoding="utf-8")


def test_memory_optimizer_defers_without_agent_decision(tmp_path: Path) -> None:
    repo = MemoryEntryRepository(tmp_path)
    entry = repo.save(
        MemoryEntry(
            type="belief",
            title="Keep memory concise",
            body="The user wants concise memory entries.",
        )
    )
    optimizer = MemoryOptimizer(tmp_path, repository=repo)

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
