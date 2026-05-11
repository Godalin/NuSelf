from __future__ import annotations

from pathlib import Path

from nuself.agent.chat import ThreadMessage, ThreadState, ThreadStore
from nuself.domain.memory import (
    MemoryEntry,
    MemoryObject,
    MemoryTypeRegistry,
    MemoryValidationIssue,
)
from nuself.domain.profile import ProfileItem
from nuself.llm import ChatMessage
from nuself.memory.curator import MemoryCurator, MemoryCuratorSettings
from nuself.memory.repository import MemoryCandidateRepository, MemoryEntryRepository
from nuself.profile.repository import ProfileItemRepository


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
    curator = MemoryCurator(tmp_path, llm=llm, thread_store=thread_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

    result = curator.run_once()
    second_result = curator.run_once()
    candidates = MemoryCandidateRepository(tmp_path).list()

    assert result.processed_messages == 2
    assert result.created == 1
    assert second_result.processed_messages == 0
    assert len(candidates) == 1
    assert candidates[0].type == "episode"
    assert candidates[0].review_state == "pending"
    assert candidates[0].source_refs == ["thread:default:0-2"]
    assert candidates[0].evidence[0].source_type == "thread"
    assert candidates[0].evidence[0].source_ref == "thread:default:0-2"
    assert candidates[0].evidence[0].summary == "important memory model decision"
    assert "candidate=" in result.log_path.read_text(encoding="utf-8")


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
    curator = MemoryCurator(tmp_path, llm=llm, thread_store=thread_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

    result = curator.run_once()
    candidates = MemoryCandidateRepository(tmp_path).list()

    assert result.updated == 1
    assert candidates[0].body == "The user prefers concise memory previews."
    assert candidates[0].action == "update"
    assert candidates[0].target_entry_id == existing.id
    assert candidates[0].source_refs == ["thread:default:0-2"]
    assert repo.get(existing.id).body == "The user likes memory previews."


def test_memory_curator_includes_profile_context_in_prompt(tmp_path: Path) -> None:
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
    llm = FakeCuratorLLM('{"actions":[{"action":"ignore","reason":"no durable memory"}]}')
    curator = MemoryCurator(tmp_path, llm=llm, thread_store=thread_store, profile_repository=profile_repo, settings=MemoryCuratorSettings(auto_accept=False))

    curator.run_once()

    system_prompt, user_prompt = llm.calls[0]
    assert "Consider existing profile items" in system_prompt.content
    assert "Existing profile items:" in user_prompt.content
    assert "Concise output" in user_prompt.content


def test_memory_curator_defers_when_agent_is_unavailable(tmp_path: Path) -> None:
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
    class FailingCuratorLLM:
        def complete(self, messages: list[ChatMessage]) -> str:
            raise RuntimeError("LLM unavailable")

    repo = MemoryEntryRepository(tmp_path)
    curator = MemoryCurator(tmp_path, llm=FailingCuratorLLM(), thread_store=thread_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

    result = curator.run_once()

    assert result.processed_messages == 0
    assert result.created == 0
    assert repo.list() == []


def test_memory_curator_ignores_trivial_chat_when_agent_says_ignore(tmp_path: Path) -> None:
    thread_store = ThreadStore(tmp_path)
    thread_store.save(
        ThreadState(
            thread_id="default",
            messages=[
                ThreadMessage(role="user", content="NuSelf"),
                ThreadMessage(role="assistant", content="I am here."),
            ],
        )
    )
    llm = FakeCuratorLLM('{"actions":[{"action":"ignore","reason":"trivial name ping"}]}')
    repo = MemoryEntryRepository(tmp_path)
    curator = MemoryCurator(tmp_path, llm=llm, thread_store=thread_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

    result = curator.run_once()
    second_result = curator.run_once()

    assert result.processed_messages == 0
    assert result.ignored == 0
    assert second_result.processed_messages == 0
    assert llm.calls == []
    assert repo.list() == []


def test_memory_curator_processes_single_high_quality_turn(tmp_path: Path) -> None:
    thread_store = ThreadStore(tmp_path)
    thread_store.save(
        ThreadState(
            thread_id="default",
            messages=[
                ThreadMessage(
                    role="user",
                    content=(
                        "I decided that memory should be captured from the depth and quality of a discussion, "
                        "not from a fixed number of chat turns, because concise but important decisions matter."
                    ),
                ),
            ],
        )
    )
    llm = FakeCuratorLLM(
        '{"actions":[{"action":"create","type":"belief","title":"Memory quality threshold",'
        '"body":"The user wants memory curation to depend on discussion depth and quality, not turn count.",'
        '"confidence":0.85,"reason":"explicit memory-system decision"}]}'
    )
    repo = MemoryEntryRepository(tmp_path)
    curator = MemoryCurator(tmp_path, llm=llm, thread_store=thread_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

    result = curator.run_once()
    candidates = MemoryCandidateRepository(tmp_path).list()

    assert result.processed_messages == 1
    assert result.created == 1
    assert candidates[0].type == "belief"
    assert candidates[0].source_refs == ["thread:default:0-1"]


def test_memory_curator_uses_absolute_cursor_after_thread_compression(tmp_path: Path) -> None:
    thread_store = ThreadStore(tmp_path)
    thread_store.save(
        ThreadState(
            thread_id="default",
            summary="Earlier compressed discussion.",
            messages=[
                ThreadMessage(
                    role="user",
                    content="We decided that compressed threads must still allow new memory curation to continue.",
                ),
                ThreadMessage(role="assistant", content="I will keep using the absolute message range."),
            ],
            message_start_index=4,
            next_message_index=6,
        )
    )
    cursor_path = tmp_path / "private" / "memory" / "cursors" / "default.json"
    cursor_path.parent.mkdir(parents=True)
    cursor_path.write_text('{"thread_id":"default","processed_message_count":4}\n', encoding="utf-8")
    llm = FakeCuratorLLM(
        '{"actions":[{"action":"create","type":"episode","title":"Compressed cursor continuity",'
        '"body":"Memory curation should continue after thread compression by using absolute message indexes.",'
        '"confidence":0.8,"reason":"cursor correctness"}]}'
    )
    repo = MemoryEntryRepository(tmp_path)
    curator = MemoryCurator(tmp_path, llm=llm, thread_store=thread_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

    result = curator.run_once()
    second_result = curator.run_once()
    candidates = MemoryCandidateRepository(tmp_path).list()

    assert result.processed_messages == 2
    assert result.created == 1
    assert second_result.processed_messages == 0
    assert candidates[0].source_refs == ["thread:default:4-6"]


def test_memory_curator_rejects_raw_transcript_body(tmp_path: Path) -> None:
    thread_store = ThreadStore(tmp_path)
    thread_store.save(
        ThreadState(
            thread_id="default",
            messages=[
                ThreadMessage(role="user", content="We need conservative memory updates."),
                ThreadMessage(role="assistant", content="I will avoid raw transcript memory."),
            ],
        )
    )
    llm = FakeCuratorLLM(
        '{"actions":[{"action":"create","type":"episode","title":"Raw transcript",'
        '"body":"user: We need conservative memory updates. assistant: I will avoid raw transcript memory.",'
        '"confidence":0.9,"reason":"bad raw transcript"}]}'
    )
    repo = MemoryEntryRepository(tmp_path)
    curator = MemoryCurator(tmp_path, llm=llm, thread_store=thread_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

    result = curator.run_once()

    assert result.processed_messages == 0
    assert repo.list() == []


def test_memory_curator_accepts_fenced_json(tmp_path: Path) -> None:
    thread_store = ThreadStore(tmp_path)
    thread_store.save(
        ThreadState(
            thread_id="default",
            messages=[
                ThreadMessage(role="user", content="Use agent decisions for memory updates."),
                ThreadMessage(role="assistant", content="I will dispatch structured actions."),
            ],
        )
    )
    llm = FakeCuratorLLM(
        '```json\n{"actions":[{"action":"create","type":"episode","title":"Structured memory decisions",'
        '"body":"The user wants memory updates to be decided by an agent and dispatched as structured actions.",'
        '"confidence":0.82,"reason":"durable memory-system decision"}]}\n```'
    )
    repo = MemoryEntryRepository(tmp_path)
    curator = MemoryCurator(tmp_path, llm=llm, thread_store=thread_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

    result = curator.run_once()

    assert result.created == 1
    assert MemoryCandidateRepository(tmp_path).list()[0].title == "Structured memory decisions"


class RejectingEpisodeDescriptor:
    @property
    def type(self) -> str:
        return "episode"

    @property
    def description(self) -> str:
        return "rejects everything"

    def validate(self, memory: MemoryObject) -> list[MemoryValidationIssue]:
        return [MemoryValidationIssue("payload.body", "rejected by test descriptor")]

    def summarize(self, memory: MemoryObject) -> str:
        return "rejected"

    def merge(self, existing: MemoryObject, incoming: MemoryObject) -> MemoryObject:
        return incoming

    def conflicts(self, a: MemoryObject, b: MemoryObject) -> bool:
        return False

    def importance(self, memory: MemoryObject) -> float:
        return memory.importance

    def decay(self, memory: MemoryObject, now: str) -> MemoryObject | None:
        return memory

    def retrieve(self, query: str, budget: int) -> bool:
        return True

    def reflect(self, memory: MemoryObject, context: str) -> list[MemoryObject]:
        return []

    def example(self) -> MemoryObject:
        return MemoryObject(type=self.type, payload={"title": "Example episode", "body": "An event happened."})


def test_memory_curator_defers_descriptor_validation_until_candidate_acceptance(tmp_path: Path) -> None:
    thread_store = ThreadStore(tmp_path)
    thread_store.save(
        ThreadState(
            thread_id="default",
            messages=[
                ThreadMessage(role="user", content="Remember that descriptor validation gates memory writes."),
                ThreadMessage(role="assistant", content="I will validate proposed memory objects before saving."),
            ],
        )
    )
    llm = FakeCuratorLLM(
        '{"actions":[{"action":"create","type":"episode","title":"Descriptor validation",'
        '"body":"Curator writes should pass descriptor validation before persistence.",'
        '"confidence":0.8,"reason":"typed memory pipeline"}]}'
    )
    repo = MemoryEntryRepository(tmp_path, registry=MemoryTypeRegistry([RejectingEpisodeDescriptor()]))
    curator = MemoryCurator(tmp_path, llm=llm, thread_store=thread_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

    result = curator.run_once()

    assert result.created == 1
    assert result.ignored == 0
    assert repo.list() == []
    assert MemoryCandidateRepository(tmp_path).list()[0].title == "Descriptor validation"


def test_memory_curator_merges_duplicate_into_existing_entry(tmp_path: Path) -> None:
    thread_store = ThreadStore(tmp_path)
    thread_store.save(
        ThreadState(
            thread_id="default",
            messages=[
                ThreadMessage(
                    role="user",
                    content="I like shared working memory because it allows multiple terminals to stay in sync without losing context.",
                ),
                ThreadMessage(
                    role="assistant",
                    content="Shared working memory is useful for continuity. When one terminal disconnects, another can pick up the same conversation thread without gaps.",
                ),
            ],
        )
    )
    repo = MemoryEntryRepository(tmp_path)
    existing = repo.save(
        MemoryEntry(
            type="episode",
            title="Shared working memory",
            body="The user likes shared working memory.",
            review_state="reviewed",
        )
    )
    llm = FakeCuratorLLM(
        '{"actions":[{"action":"create","type":"episode","title":"Shared working memory",'
        '"body":"The user really likes shared working memory.",'
        '"confidence":0.8,"reason":"duplicate detection test"}]}'
    )
    curator = MemoryCurator(tmp_path, llm=llm, thread_store=thread_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

    result = curator.run_once()
    candidates = MemoryCandidateRepository(tmp_path).list()

    assert result.updated == 1
    assert result.created == 0
    assert len(candidates) == 1
    assert candidates[0].action == "update"
    assert candidates[0].target_entry_id == existing.id
    assert candidates[0].body == "The user really likes shared working memory."


def test_memory_curator_auto_accept_creates_entry(tmp_path: Path) -> None:
    """With auto_accept=True (default), candidates become entries immediately."""
    thread_store = ThreadStore(tmp_path)
    thread_store.save(
        ThreadState(
            thread_id="default",
            messages=[
                ThreadMessage(role="user", content=(
                    "I have decided to learn Rust for systems programming because I want "
                    "to build high-performance tools. I prefer it over C++ for memory safety."
                )),
                ThreadMessage(role="assistant", content="Great choice, Rust has excellent memory safety guarantees."),
            ],
        )
    )
    llm = FakeCuratorLLM(
        '{"actions":[{"action":"create","type":"belief","title":"Interest in Rust",'
        '"body":"The user wants to learn Rust for systems programming.",'
        '"confidence":0.85,"reason":"explicit learning goal"}]}'
    )
    repo = MemoryEntryRepository(tmp_path)
    curator = MemoryCurator(tmp_path, llm=llm, thread_store=thread_store, repository=repo)

    result = curator.run_once()

    # Candidate was auto-accepted → it's now an entry
    entries = repo.list()
    assert len(entries) == 1
    assert entries[0].title == "Interest in Rust"
    assert entries[0].review_state == "reviewed"
    assert result.created == 1

    # Candidate exists but is marked accepted
    candidates = MemoryCandidateRepository(tmp_path).list(include_reviewed=True)
    assert len(candidates) == 1
    assert candidates[0].review_state == "accepted"
