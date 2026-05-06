from __future__ import annotations

from pathlib import Path

from nuself.agent.chat import ThreadMessage, ThreadState, ThreadStore
from nuself.domain.memory import MemoryEntry
from nuself.llm import ChatMessage
from nuself.memory.curator import MemoryCurator
from nuself.memory.repository import MemoryEntryRepository


class FakeCuratorLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[list[ChatMessage]] = []

    def complete(self, messages: list[ChatMessage]) -> str:
        self.calls.append(messages)
        return self.response


def test_memory_curator_creates_episode_and_advances_cursor(tmp_path: Path) -> None:
    thread_store = ThreadStore(tmp_path)
    thread_store.save(
        ThreadState(
            thread_id="default",
            messages=[
                ThreadMessage(role="user", content="We should share working memory across terminals."),
                ThreadMessage(role="assistant", content="Agreed. The default stream should be shared."),
            ],
        )
    )
    llm = FakeCuratorLLM(
        '{"actions":[{"action":"create","type":"episode","title":"Shared working memory",'
        '"body":"The user decided that terminals attached to one NuSelf mind should share short-term memory.",'
        '"confidence":0.8,"reason":"important memory model decision"}]}'
    )
    repo = MemoryEntryRepository(tmp_path)
    curator = MemoryCurator(tmp_path, llm=llm, thread_store=thread_store, repository=repo)

    result = curator.run_once()
    second_result = curator.run_once()
    entries = repo.list()

    assert result.processed_messages == 2
    assert result.created == 1
    assert second_result.processed_messages == 0
    assert len(entries) == 1
    assert entries[0].type == "episode"
    assert entries[0].review_state == "reviewed"
    assert entries[0].source_refs == ["thread:default:0-2"]
    assert "created=1" in result.log_path.read_text(encoding="utf-8")


def test_memory_curator_updates_existing_memory_as_draft(tmp_path: Path) -> None:
    thread_store = ThreadStore(tmp_path)
    thread_store.save(
        ThreadState(
            thread_id="default",
            messages=[
                ThreadMessage(role="user", content="I prefer concise memory previews."),
                ThreadMessage(role="assistant", content="I will keep memory previews compact."),
            ],
        )
    )
    repo = MemoryEntryRepository(tmp_path)
    existing = repo.save(
        MemoryEntry(
            type="style_trait",
            title="Memory preview style",
            body="The user likes memory previews.",
            review_state="reviewed",
        )
    )
    llm = FakeCuratorLLM(
        '{"actions":[{"action":"update","entry_id":"'
        + existing.id
        + '","title":"Memory preview style","body":"The user prefers concise memory previews.",'
        '"confidence":0.75,"reason":"user clarified preview style"}]}'
    )
    curator = MemoryCurator(tmp_path, llm=llm, thread_store=thread_store, repository=repo)

    result = curator.run_once()
    updated = repo.get(existing.id)

    assert result.updated == 1
    assert updated.body == "The user prefers concise memory previews."
    assert updated.review_state == "draft"
    assert updated.source_refs == ["thread:default:0-2"]


def test_memory_curator_uses_local_episode_when_llm_is_unavailable(tmp_path: Path) -> None:
    thread_store = ThreadStore(tmp_path)
    thread_store.save(
        ThreadState(
            thread_id="default",
            messages=[
                ThreadMessage(role="user", content="Remember this local fallback path."),
                ThreadMessage(role="assistant", content="I can summarize it locally."),
            ],
        )
    )
    repo = MemoryEntryRepository(tmp_path)
    curator = MemoryCurator(tmp_path, thread_store=thread_store, repository=repo)

    result = curator.run_once()

    assert result.created == 1
    assert repo.list()[0].title.startswith("Conversation:")
