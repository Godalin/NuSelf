from __future__ import annotations

# pyright: reportUnusedImport=false

from memory_fixtures import (
    MemoryCurator,
    memory_candidate_repository,
    memory_curator_plan_store,
    memory_entry_repository,
    source_repository,
)

from collections.abc import Sequence
import json
from pathlib import Path
from typing import Literal

import pytest
from langchain_core.messages import BaseMessage

from nuself.trace.composition import compose_trace_services
from nuself.conversation import ConversationMessage, ConversationState
from conversation_fixtures import ConversationStore
from nuself.config.settings import runtime_paths
from nuself.agent.errors import AgentModelUnavailableError
from nuself.memory.model import (
    MemoryEntry,
    MemoryObject,
    MemoryTypeRegistry,
    MemoryValidationIssue,
)
from nuself.profile.model import ProfileItem
from nuself.log.reader import read_log_events
from nuself.memory.curator_contract import (
    CuratorActionsOutput,
    MemoryCuratorSettings,
    actions_from_output as _actions_from_output,
)
from nuself.memory.repository import (
    MemoryCandidateRepository,
    MemoryEntryRepository,
)
from nuself.profile.repository import ProfileItemRepository
from tests.backend import owned_backend


class FakeCuratorAgent:
    def __init__(self, output: CuratorActionsOutput) -> None:
        self.output = output
        self.calls: list[Sequence[BaseMessage]] = []

    def invoke(
        self,
        messages: Sequence[BaseMessage],
    ) -> CuratorActionsOutput:
        self.calls.append(messages)
        return self.output


def _curator_agent(response: str) -> FakeCuratorAgent:
    return FakeCuratorAgent(
        CuratorActionsOutput.model_validate_json(response)
    )


@pytest.mark.parametrize(
    "raw",
    [
        (
            '{"actions":[{"action":"create","type":"episode",'
            '"title":"Invalid confidence","body":"Body","tags":["memory"],'
            '"confidence":1.2}]}'
        ),
        (
            '{"actions":[{"action":"create","type":"episode",'
            '"title":"Coercive confidence","body":"Body","tags":["memory"],'
            '"confidence":true}]}'
        ),
        (
            '{"actions":[{"action":"create","type":"episode",'
            '"title":"Extra field","body":"Body","tags":["memory"],'
            '"confidence":0.8,"unknown":"value"}]}'
        ),
        (
            '{"actions":[{"action":"update","type":"episode",'
            '"title":"Missing target","body":"Body","tags":["memory"],'
            '"confidence":0.8}]}'
        ),
    ],
)
def test_curator_action_schema_fails_closed(raw: str) -> None:
    with pytest.raises(ValueError):
        output = CuratorActionsOutput.model_validate_json(raw)
        _actions_from_output(output, allowed_types=("episode",))


def test_curator_rejects_complete_batch_when_one_action_is_invalid(
    tmp_path: Path,
) -> None:
    conversation_store = ConversationStore(tmp_path)
    conversation_store.save(
        ConversationState(
            conversation_id="default",
            messages=[
                ConversationMessage(
                    role="user",
                    content=(
                        "Remember that curator decisions must be validated "
                        "completely before any memory candidate is written."
                    ),
                )
            ],
        )
    )
    agent = _curator_agent(
        '{"actions":['
        '{"action":"create","type":"episode","title":"Valid sibling",'
        '"body":"This action must not be partially applied.",'
        '"tags":["memory"],"confidence":0.8},'
        '{"action":"create","type":"unknown","title":"Invalid sibling",'
        '"body":"This invalid type rejects the batch.",'
        '"tags":["memory"],"confidence":0.8}'
        "]}"
    )
    curator = MemoryCurator(
        tmp_path,
        agent=agent,
        conversation_store=conversation_store,
        settings=MemoryCuratorSettings(auto_accept=False),
    )

    result = curator.run_once()

    assert result.processed_messages == 0
    assert memory_candidate_repository(tmp_path).list() == []


def test_memory_curator_creates_episode_and_advances_cursor(tmp_path: Path) -> None:
    conversation_store = ConversationStore(tmp_path)
    conversation_store.save(
        ConversationState(
            conversation_id="default",
            messages=[
                ConversationMessage(role="user", content="We should share working memory across terminals."),
                ConversationMessage(role="assistant", content="Agreed. The default stream should be shared."),
            ],
        )
    )
    agent = _curator_agent(
        '{"actions":[{"action":"create","type":"episode","title":"Shared working memory",'
        '"body":"The user decided that terminals attached to one NuSelf mind should share short-term memory.",'
        '"tags":["memory"],"confidence":0.8,"reason":"important memory model decision"}]}'
    )
    repo = memory_entry_repository(tmp_path)
    curator = MemoryCurator(tmp_path, agent=agent, conversation_store=conversation_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

    result = curator.run_once()
    second_result = curator.run_once()
    candidates = memory_candidate_repository(tmp_path).list()

    assert result.processed_messages == 2
    assert result.created == 1
    assert second_result.processed_messages == 0
    assert len(candidates) == 1
    assert candidates[0].type == "episode"
    assert candidates[0].tags == ("memory",)
    assert candidates[0].review_state == "pending"
    assert candidates[0].source_refs == ("test-interaction:default:0-2",)
    assert candidates[0].observed_at is not None
    assert candidates[0].evidence[0].source_type == "observation"
    assert candidates[0].evidence[0].source_ref == "test-interaction:default:0-2"
    assert candidates[0].evidence[0].observed_at == candidates[0].observed_at
    assert candidates[0].evidence[0].summary == "important memory model decision"
    events = read_log_events(
        project_root=tmp_path,
        component="memory",
    )
    assert [event.event for event in events[-2:]] == [
        "candidate_created",
        "curator_completed",
    ]
    assert events[-2].metadata is not None
    assert events[-2].metadata == {
        "candidate_id": candidates[0].id,
        "memory_type": "episode",
    }
    for line in result.log_path.read_text(
        encoding="utf-8"
    ).splitlines():
        assert isinstance(json.loads(line), dict)
def test_memory_curator_plan_write_fails_before_candidate_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation_store = ConversationStore(tmp_path)
    conversation_store.save(
        ConversationState(
            conversation_id="default",
            messages=[
                ConversationMessage(
                    role="user",
                    content=(
                        "Remember that a curator plan must be durable before "
                        "any candidate mutation begins."
                    ),
                )
            ],
        )
    )
    agent = _curator_agent(
        '{"actions":[{"action":"create","type":"episode",'
        '"title":"Plan-first commit",'
        '"body":"The plan is persisted before candidate effects.",'
        '"tags":["memory"],"confidence":0.9,'
        '"reason":"explicit commit-order requirement"}]}'
    )

    plan_store = memory_curator_plan_store(tmp_path)

    def fail_plan_write(
        _key: str,
        _payload: dict[str, object],
    ) -> None:
        raise OSError("plan store unavailable")

    monkeypatch.setattr(
        plan_store._collection,  # pyright: ignore[reportPrivateUsage]
        "put",
        fail_plan_write,
    )
    curator = MemoryCurator(
        tmp_path,
        agent=agent,
        conversation_store=conversation_store,
        settings=MemoryCuratorSettings(auto_accept=False),
        plan_store=plan_store,
    )

    with pytest.raises(OSError, match="plan store unavailable"):
        curator.run_once()

    assert len(agent.calls) == 1
    assert memory_candidate_repository(tmp_path).list() == []


def test_memory_curator_updates_existing_memory_as_draft(tmp_path: Path) -> None:
    conversation_store = ConversationStore(tmp_path)
    conversation_store.save(
        ConversationState(
            conversation_id="default",
            messages=[
                ConversationMessage(role="user", content="I prefer concise memory previews."),
                ConversationMessage(role="assistant", content="I will keep memory previews compact."),
            ],
        )
    )
    repo = memory_entry_repository(tmp_path)
    existing = repo.save(
        MemoryEntry(
            type="style_trait",
            title="Memory preview style",
            body="The user likes memory previews.",
            review_state="reviewed",
        )
    )
    agent = _curator_agent(
        '{"actions":[{"action":"update","entry_id":"'
        + existing.id
        + '","title":"Memory preview style","body":"The user prefers concise memory previews.",'
        '"tags":["memory","preview"],"confidence":0.75,"reason":"user clarified preview style"}]}'
    )
    curator = MemoryCurator(tmp_path, agent=agent, conversation_store=conversation_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

    result = curator.run_once()
    candidates = memory_candidate_repository(tmp_path).list()

    assert result.updated == 1
    assert candidates[0].body == "The user prefers concise memory previews."
    assert candidates[0].tags == ("memory", "preview")
    assert candidates[0].action == "update"
    assert candidates[0].target_entry_id == existing.id
    assert candidates[0].source_refs == ("test-interaction:default:0-2",)
    assert candidates[0].observed_at is not None
    assert repo.get(existing.id).body == "The user likes memory previews."


def test_memory_curator_includes_profile_context_in_prompt(tmp_path: Path) -> None:
    conversation_store = ConversationStore(tmp_path)
    conversation_store.save(
        ConversationState(
            conversation_id="default",
            messages=[
                ConversationMessage(role="user", content="I prefer concise memory previews."),
                ConversationMessage(role="assistant", content="I will keep memory previews compact."),
            ],
        )
    )
    profile_repo = ProfileItemRepository(runtime_paths(tmp_path), backend=owned_backend(tmp_path))
    profile_repo.save(
        ProfileItem(
            type="profile_fact",
            title="Concise output",
            body="Prefers concise command output.",
            tags=["cli"],
            source_refs=["source:profile:0"],
        )
    )
    agent = _curator_agent('{"actions":[{"action":"ignore","reason":"no durable memory"}]}')
    curator = MemoryCurator(tmp_path, agent=agent, conversation_store=conversation_store, profile_repository=profile_repo, settings=MemoryCuratorSettings(auto_accept=False))

    curator.run_once()

    system_prompt, user_prompt = agent.calls[0]
    assert "Consider existing profile items" in system_prompt.text
    assert "Existing profile items:" in user_prompt.text
    assert "Concise output" in user_prompt.text


def test_memory_curator_defers_when_agent_is_unavailable(tmp_path: Path) -> None:
    conversation_store = ConversationStore(tmp_path)
    conversation_store.save(
        ConversationState(
            conversation_id="default",
            messages=[
                ConversationMessage(role="user", content="Remember this local fallback path."),
                ConversationMessage(role="assistant", content="I can summarize it locally."),
            ],
        )
    )
    class FailingCuratorAgent:
        def invoke(
            self,
            messages: Sequence[BaseMessage],
        ) -> CuratorActionsOutput:
            raise AgentModelUnavailableError("LLM unavailable")

    repo = memory_entry_repository(tmp_path)
    curator = MemoryCurator(tmp_path, agent=FailingCuratorAgent(), conversation_store=conversation_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

    result = curator.run_once()

    assert result.processed_messages == 0
    assert result.created == 0
    assert repo.list() == []


def test_memory_curator_contention_is_deferred_without_model_or_mutation(
    tmp_path: Path,
) -> None:
    conversation_store = ConversationStore(tmp_path)
    conversation_store.save(
        ConversationState(
            conversation_id="default",
            messages=[
                ConversationMessage(
                    role="user",
                    content=(
                        "Remember this sufficiently detailed durable decision "
                        "so contention must prevent the curator model call."
                    ),
                ),
            ],
        )
    )
    agent = _curator_agent(
        '{"actions":[{"action":"ignore","reason":"not reached"}]}'
    )
    curator = MemoryCurator(
        tmp_path,
        agent=agent,
        conversation_store=conversation_store,
        settings=MemoryCuratorSettings(auto_accept=False),
    )

    observation = curator.prepare_observation()
    assert observation is not None
    with memory_curator_plan_store(tmp_path).exclusive(observation.id):
        result = curator.run_once()

    assert result.processed_messages == 0
    assert result.created == 0
    assert result.updated == 0
    assert result.ignored == 0
    assert agent.calls == []
    assert memory_candidate_repository(tmp_path).list() == []
    assert curator._test_observations.get(observation.id).status == "pending"  # pyright: ignore[reportPrivateUsage]
    events = [
        event
        for event in read_log_events(
            project_root=tmp_path,
            component="memory",
        )
        if event.event == "curator_contended"
    ]
    assert len(events) == 1
    assert events[0].status == "deferred"
    assert events[0].metadata == {"observation_id": observation.id}


@pytest.mark.parametrize(
    "failure",
    [
        RuntimeError("curator implementation failed"),
        ValueError("curator implementation returned invalid state"),
    ],
)
def test_memory_curator_propagates_untyped_agent_errors(
    tmp_path: Path,
    failure: Exception,
) -> None:
    conversation_store = ConversationStore(tmp_path)
    conversation_store.save(
        ConversationState(
            conversation_id="default",
            messages=[
                ConversationMessage(
                    role="user",
                    content=(
                        "Remember this important preference because it should "
                        "exercise the curator agent decision boundary."
                    ),
                ),
            ],
        )
    )

    class BrokenCuratorAgent:
        def invoke(
            self,
            messages: Sequence[BaseMessage],
        ) -> CuratorActionsOutput:
            del messages
            raise failure

    curator = MemoryCurator(
        tmp_path,
        agent=BrokenCuratorAgent(),
        conversation_store=conversation_store,
        settings=MemoryCuratorSettings(auto_accept=False),
    )

    with pytest.raises(type(failure)) as captured:
        curator.run_once()

    assert captured.value is failure


def test_memory_curator_ignores_trivial_chat_when_agent_says_ignore(tmp_path: Path) -> None:
    conversation_store = ConversationStore(tmp_path)
    conversation_store.save(
        ConversationState(
            conversation_id="default",
            messages=[
                ConversationMessage(role="user", content="NuSelf"),
                ConversationMessage(role="assistant", content="I am here."),
            ],
        )
    )
    agent = _curator_agent('{"actions":[{"action":"ignore","reason":"trivial name ping"}]}')
    repo = memory_entry_repository(tmp_path)
    curator = MemoryCurator(tmp_path, agent=agent, conversation_store=conversation_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

    result = curator.run_once()
    second_result = curator.run_once()

    assert result.processed_messages == 0
    assert result.ignored == 0
    assert second_result.processed_messages == 0
    assert agent.calls == []
    assert repo.list() == []


@pytest.mark.parametrize(
    "content",
    [
        "请记住我不喜欢早会。",
        "以后回答尽量简洁。",
        "今後は簡潔に答えてください。",
        "Please 記住 this preference。",
    ],
)
def test_memory_curator_fast_gate_accepts_multilingual_durable_signal(
    tmp_path: Path,
    content: str,
) -> None:
    conversation_store = ConversationStore(tmp_path)
    conversation_store.save(
        ConversationState(
            conversation_id="default",
            messages=[ConversationMessage(role="user", content=content)],
        )
    )
    agent = _curator_agent(
        '{"actions":[{"action":"create","type":"preference",'
        '"title":"Response preference","body":"The user stated a durable '
        'response preference.","tags":["preference"],"confidence":0.8,'
        '"reason":"explicit durable preference"}]}'
    )
    curator = MemoryCurator(
        tmp_path,
        agent=agent,
        conversation_store=conversation_store,
        settings=MemoryCuratorSettings(auto_accept=False),
    )

    result = curator.run_once()

    assert result.processed_messages == 1
    assert result.created == 1
    assert len(agent.calls) == 1
    assert len(memory_candidate_repository(tmp_path).list()) == 1


def test_memory_curator_processes_single_high_quality_turn(tmp_path: Path) -> None:
    conversation_store = ConversationStore(tmp_path)
    conversation_store.save(
        ConversationState(
            conversation_id="default",
            messages=[
                ConversationMessage(
                    role="user",
                    content=(
                        "I decided that memory should be captured from the depth and quality of a discussion, "
                        "not from a fixed number of chat turns, because concise but important decisions matter."
                    ),
                ),
            ],
        )
    )
    agent = _curator_agent(
        '{"actions":[{"action":"create","type":"belief","title":"Memory quality threshold",'
        '"body":"The user wants memory curation to depend on discussion depth and quality, not turn count.",'
        '"tags":["memory"],"confidence":0.85,"reason":"explicit memory-system decision"}]}'
    )
    repo = memory_entry_repository(tmp_path)
    curator = MemoryCurator(tmp_path, agent=agent, conversation_store=conversation_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

    result = curator.run_once()
    candidates = memory_candidate_repository(tmp_path).list()

    assert result.processed_messages == 1
    assert result.created == 1
    assert candidates[0].type == "belief"
    assert candidates[0].source_refs == ("test-interaction:default:0-1",)


def test_memory_curator_accepts_projected_content_after_conversation_compression(tmp_path: Path) -> None:
    conversation_store = ConversationStore(tmp_path)
    conversation_store.save(
        ConversationState(
            conversation_id="default",
            summary="Earlier compressed discussion.",
            messages=[
                ConversationMessage(
                    role="user",
                    content="We decided that compressed threads must still allow new memory curation to continue.",
                ),
                ConversationMessage(role="assistant", content="I will keep using the absolute message range."),
            ],
            message_start_index=4,
            next_message_index=6,
        )
    )
    agent = _curator_agent(
        '{"actions":[{"action":"create","type":"episode","title":"Compressed cursor continuity",'
        '"body":"Memory curation should continue after conversation compression by using absolute message indexes.",'
        '"tags":["memory"],"confidence":0.8,"reason":"cursor correctness"}]}'
    )
    repo = memory_entry_repository(tmp_path)
    curator = MemoryCurator(tmp_path, agent=agent, conversation_store=conversation_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

    result = curator.run_once()
    second_result = curator.run_once()
    candidates = memory_candidate_repository(tmp_path).list()

    assert result.processed_messages == 2
    assert result.created == 1
    assert second_result.processed_messages == 0
    assert candidates[0].source_refs == ("test-interaction:default:4-6",)


def test_memory_curator_rejects_raw_transcript_body(tmp_path: Path) -> None:
    conversation_store = ConversationStore(tmp_path)
    conversation_store.save(
        ConversationState(
            conversation_id="default",
            messages=[
                ConversationMessage(role="user", content="We need conservative memory updates."),
                ConversationMessage(role="assistant", content="I will avoid raw transcript memory."),
            ],
        )
    )
    agent = _curator_agent(
        '{"actions":[{"action":"create","type":"episode","title":"Raw transcript",'
        '"body":"user: We need conservative memory updates. assistant: I will avoid raw transcript memory.",'
        '"tags":["memory"],"confidence":0.9,"reason":"bad raw transcript"}]}'
    )
    repo = memory_entry_repository(tmp_path)
    curator = MemoryCurator(tmp_path, agent=agent, conversation_store=conversation_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

    result = curator.run_once()

    assert result.processed_messages == 0
    assert repo.list() == []


def test_memory_curator_rejects_create_without_tags(tmp_path: Path) -> None:
    conversation_store = ConversationStore(tmp_path)
    conversation_store.save(
        ConversationState(
            conversation_id="default",
            messages=[
                ConversationMessage(role="user", content="Remember that memory entries need explicit tags."),
                ConversationMessage(role="assistant", content="I will require tags on curated memory candidates."),
            ],
        )
    )
    agent = _curator_agent(
        '{"actions":[{"action":"create","type":"episode","title":"Missing tags",'
        '"body":"Curated memory candidates should include tags.",'
        '"confidence":0.9,"reason":"bad missing tags"}]}'
    )
    repo = memory_entry_repository(tmp_path)
    curator = MemoryCurator(tmp_path, agent=agent, conversation_store=conversation_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

    result = curator.run_once()

    assert result.processed_messages == 0
    assert memory_candidate_repository(tmp_path).list() == []
    assert repo.list() == []


def test_memory_curator_rejects_unknown_memory_type(tmp_path: Path) -> None:
    conversation_store = ConversationStore(tmp_path)
    conversation_store.save(
        ConversationState(
            conversation_id="default",
            messages=[
                ConversationMessage(role="user", content="Remember that unknown memory types should not be coerced."),
                ConversationMessage(role="assistant", content="I will reject unsupported memory action types."),
            ],
        )
    )
    agent = _curator_agent(
        '{"actions":[{"action":"create","type":"made_up_type","title":"Unknown type",'
        '"body":"Unknown memory types should not be silently coerced.",'
        '"tags":["memory"],"confidence":0.9,"reason":"bad unknown type"}]}'
    )
    repo = memory_entry_repository(tmp_path)
    curator = MemoryCurator(
        tmp_path,
        agent=agent,
        conversation_store=conversation_store,
        repository=repo,
        settings=MemoryCuratorSettings(auto_accept=False),
    )

    result = curator.run_once()

    assert result.processed_messages == 0
    assert memory_candidate_repository(tmp_path).list() == []
    assert repo.list() == []


def test_memory_curator_accepts_typed_structured_output(
    tmp_path: Path,
) -> None:
    conversation_store = ConversationStore(tmp_path)
    conversation_store.save(
        ConversationState(
            conversation_id="default",
            messages=[
                ConversationMessage(role="user", content="Use agent decisions for memory updates."),
                ConversationMessage(role="assistant", content="I will dispatch structured actions."),
            ],
        )
    )
    agent = _curator_agent(
        '{"actions":[{"action":"create","type":"episode","title":"Structured memory decisions",'
        '"body":"The user wants memory updates to be decided by an agent and dispatched as structured actions.",'
        '"tags":["memory"],"confidence":0.82,"reason":"durable memory-system decision"}]}'
    )
    repo = memory_entry_repository(tmp_path)
    curator = MemoryCurator(tmp_path, agent=agent, conversation_store=conversation_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

    result = curator.run_once()

    assert result.created == 1
    assert memory_candidate_repository(tmp_path).list()[0].title == "Structured memory decisions"


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
    conversation_store = ConversationStore(tmp_path)
    conversation_store.save(
        ConversationState(
            conversation_id="default",
            messages=[
                ConversationMessage(role="user", content="Remember that descriptor validation gates memory writes."),
                ConversationMessage(role="assistant", content="I will validate proposed memory objects before saving."),
            ],
        )
    )
    agent = _curator_agent(
        '{"actions":[{"action":"create","type":"episode","title":"Descriptor validation",'
        '"body":"Curator writes should pass descriptor validation before persistence.",'
        '"tags":["memory"],"confidence":0.8,"reason":"typed memory pipeline"}]}'
    )
    repo = memory_entry_repository(tmp_path, registry=MemoryTypeRegistry([RejectingEpisodeDescriptor()]))
    curator = MemoryCurator(tmp_path, agent=agent, conversation_store=conversation_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

    result = curator.run_once()

    assert result.created == 1
    assert result.ignored == 0
    assert repo.list() == []
    assert memory_candidate_repository(tmp_path).list()[0].title == "Descriptor validation"


def test_memory_curator_merges_duplicate_into_existing_entry(tmp_path: Path) -> None:
    conversation_store = ConversationStore(tmp_path)
    conversation_store.save(
        ConversationState(
            conversation_id="default",
            messages=[
                ConversationMessage(
                    role="user",
                    content="I like shared working memory because it allows multiple terminals to stay in sync without losing context.",
                ),
                ConversationMessage(
                    role="assistant",
                    content="Shared working memory is useful for continuity. When one terminal disconnects, another can pick up the same conversation without gaps.",
                ),
            ],
        )
    )
    repo = memory_entry_repository(tmp_path)
    existing = repo.save(
        MemoryEntry(
            type="episode",
            title="Shared working memory",
            body="The user likes shared working memory.",
            review_state="reviewed",
        )
    )
    agent = _curator_agent(
        '{"actions":[{"action":"create","type":"episode","title":"Shared working memory",'
        '"body":"The user really likes shared working memory.",'
        '"tags":["memory"],"confidence":0.8,"reason":"duplicate detection test"}]}'
    )
    curator = MemoryCurator(tmp_path, agent=agent, conversation_store=conversation_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

    result = curator.run_once()
    candidates = memory_candidate_repository(tmp_path).list()

    assert result.updated == 1
    assert result.created == 0
    assert len(candidates) == 1
    assert candidates[0].action == "update"
    assert candidates[0].target_entry_id == existing.id
    assert candidates[0].body == "The user really likes shared working memory."


def test_memory_curator_auto_accept_creates_entry(tmp_path: Path) -> None:
    """With auto_accept=True (default), candidates become entries immediately."""
    conversation_store = ConversationStore(tmp_path)
    conversation_store.save(
        ConversationState(
            conversation_id="default",
            messages=[
                ConversationMessage(role="user", content=(
                    "I have decided to learn Rust for systems programming because I want "
                    "to build high-performance tools. I prefer it over C++ for memory safety."
                )),
                ConversationMessage(role="assistant", content="Great choice, Rust has excellent memory safety guarantees."),
            ],
        )
    )
    agent = _curator_agent(
        '{"actions":[{"action":"create","type":"belief","title":"Interest in Rust",'
        '"body":"The user wants to learn Rust for systems programming.",'
        '"tags":["rust"],"confidence":0.85,"reason":"explicit learning goal"}]}'
    )
    repo = memory_entry_repository(tmp_path)
    curator = MemoryCurator(tmp_path, agent=agent, conversation_store=conversation_store, repository=repo)

    result = curator.run_once()

    # Candidate was auto-accepted → it's now an entry
    entries = repo.list()
    assert len(entries) == 1
    assert entries[0].title == "Interest in Rust"
    assert entries[0].tags == ("rust",)
    assert entries[0].review_state == "reviewed"
    assert result.created == 1

    # Candidate exists but is marked accepted
    candidates = memory_candidate_repository(tmp_path).list(include_reviewed=True)
    assert len(candidates) == 1
    assert candidates[0].review_state == "accepted"


def test_curator_audit_failure_cannot_replay_committed_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation_store = ConversationStore(tmp_path)
    conversation_store.save(
        ConversationState(
            conversation_id="default",
            messages=[
                ConversationMessage(
                    role="user",
                    content=(
                        "Remember that curator audit storage is auxiliary "
                        "after candidate and cursor persistence."
                    ),
                )
            ],
        )
    )
    agent = _curator_agent(
        '{"actions":[{"action":"create","type":"episode",'
        '"title":"Curator audit boundary",'
        '"body":"Curator audit writes are auxiliary.",'
        '"tags":["memory"],"confidence":0.8,'
        '"reason":"explicit durability requirement"}]}'
    )

    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("audit store unavailable")

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        fail_log,
    )
    curator = MemoryCurator(
        tmp_path,
        agent=agent,
        conversation_store=conversation_store,
        settings=MemoryCuratorSettings(auto_accept=False),
    )

    with pytest.warns(RuntimeWarning) as captured:
        result = curator.run_once()

    assert result.created == 1
    assert len(memory_candidate_repository(tmp_path).list()) == 1
    assert curator.run_once().processed_messages == 0
    assert len(agent.calls) == 1
    assert any(
        "runtime/observability_sink_failed" in str(warning.message)
        for warning in captured
    )


def test_curator_trace_diagnostics_cannot_replace_reviewed_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nuself.trace.service import TraceRecorder

    conversation_store = ConversationStore(tmp_path)
    conversation_store.save(
        ConversationState(
            conversation_id="default",
            messages=[
                ConversationMessage(
                    role="user",
                    content=(
                        "Remember that trace persistence is auxiliary after "
                        "a reviewed memory entry is saved."
                    ),
                )
            ],
        )
    )
    agent = _curator_agent(
        '{"actions":[{"action":"create","type":"episode",'
        '"title":"Trace boundary","body":"Trace writes are auxiliary.",'
        '"tags":["trace"],"confidence":0.8,'
        '"reason":"explicit provenance requirement"}]}'
    )

    def fail_trace(*args: object, **kwargs: object) -> None:
        raise OSError("trace store unavailable")

    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("audit store unavailable")

    monkeypatch.setattr(
        TraceRecorder,
        "record_memory_update",
        fail_trace,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        fail_log,
    )
    repository = memory_entry_repository(tmp_path)
    curator = MemoryCurator(
        tmp_path,
        agent=agent,
        conversation_store=conversation_store,
        repository=repository,
        trace_recorder=compose_trace_services(
            runtime_paths(tmp_path),
            owned_backend(tmp_path),
        ).recorder,
    )

    with pytest.warns(RuntimeWarning) as captured:
        result = curator.run_once()

    assert result.created == 1
    [entry] = repository.list()
    assert entry.review_state == "reviewed"
    assert curator.run_once().processed_messages == 0
    messages = [str(warning.message) for warning in captured]
    assert any(
        "component=memory event=trace_recording_failed "
        "observed_error=trace store unavailable"
        in message
        for message in messages
    )


def test_auto_accept_update_trace_retains_update_action(
    tmp_path: Path,
) -> None:
    conversation_store = ConversationStore(tmp_path)
    conversation_store.save(
        ConversationState(
            conversation_id="default",
            messages=[
                ConversationMessage(
                    role="user",
                    content=(
                        "Remember that I updated the durable memory policy: "
                        "curator traces must retain whether an existing "
                        "entry was updated."
                    ),
                )
            ],
        )
    )
    repository = memory_entry_repository(tmp_path)
    existing = repository.save(
        MemoryEntry(
            type="episode",
            title="Curator trace policy",
            body="Curator traces record memory changes.",
            review_state="reviewed",
        )
    )
    agent = _curator_agent(
        '{"actions":[{"action":"update","entry_id":"'
        + existing.id
        + '","type":"episode","title":"Curator trace policy",'
        '"body":"Curator traces retain create and update actions.",'
        '"tags":["trace"],"confidence":0.9,'
        '"reason":"explicit policy update"}]}'
    )
    curator = MemoryCurator(
        tmp_path,
        agent=agent,
        conversation_store=conversation_store,
        repository=repository,
        trace_recorder=compose_trace_services(
            runtime_paths(tmp_path),
            owned_backend(tmp_path),
        ).recorder,
    )

    result = curator.run_once()

    assert result.updated == 1
    [trace] = compose_trace_services(
        runtime_paths(tmp_path),
        owned_backend(tmp_path),
    ).query.list_traces(
        kind="memory_update"
    )
    assert trace.metadata["action"] == "update"


def test_memory_curator_reports_recoverable_auto_accept_failure(
    tmp_path: Path,
) -> None:
    conversation_store = ConversationStore(tmp_path)
    conversation_store.save(
        ConversationState(
            conversation_id="default",
            messages=[
                ConversationMessage(
                    role="user",
                    content=(
                        "Remember that invalid candidate promotion must remain "
                        "visible and recoverable without replaying this turn."
                    ),
                )
            ],
        )
    )
    agent = _curator_agent(
        '{"actions":[{"action":"create","type":"episode",'
        '"title":"Recoverable promotion","body":"Keep pending.",'
        '"tags":["memory"],"confidence":0.8,'
        '"reason":"explicit durability requirement"}]}'
    )
    repo = memory_entry_repository(
        tmp_path,
        registry=MemoryTypeRegistry([RejectingEpisodeDescriptor()]),
    )
    curator = MemoryCurator(
        tmp_path,
        agent=agent,
        conversation_store=conversation_store,
        repository=repo,
    )

    result = curator.run_once()
    second = curator.run_once()

    assert result.created == 1
    assert second.processed_messages == 0
    assert len(agent.calls) == 1
    assert repo.list() == []
    candidates = memory_candidate_repository(tmp_path).list()
    assert len(candidates) == 1
    assert candidates[0].review_state == "pending"
    event = [
        item
        for item in read_log_events(
            project_root=tmp_path,
            component="memory",
        )
        if item.event == "auto_accept_failed"
    ][-1]
    assert event.metadata == {
        "candidate_id": candidates[0].id,
        "action": "create",
        "memory_type": "episode",
        "target_entry_id": None,
    }
    assert event.error is not None
    assert event.level == "warning"
    assert event.status == "degraded"
    assert "rejected by test descriptor" in event.error


@pytest.mark.parametrize(
    ("accept_error", "expected_error"),
    [
        (OSError("candidate storage unavailable"), "candidate storage unavailable"),
        (RuntimeError("candidate transaction failed"), "candidate transaction failed"),
    ],
    ids=["storage-failure", "transaction-failure"],
)
def test_memory_curator_does_not_replay_durable_candidate_after_auto_accept_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    accept_error: Exception,
    expected_error: str,
) -> None:
    conversation_store = ConversationStore(tmp_path)
    conversation_store.save(
        ConversationState(
            conversation_id="default",
            messages=[
                ConversationMessage(
                    role="user",
                    content=(
                        "Remember that a durable candidate must prevent source "
                        "replay even when automatic acceptance storage fails."
                    ),
                )
            ],
        )
    )
    agent = _curator_agent(
        '{"actions":[{"action":"create","type":"episode",'
        '"title":"Storage boundary","body":"Keep the durable candidate.",'
        '"tags":["memory"],"confidence":0.8,'
        '"reason":"source replay safety"}]}'
    )
    candidate_repo = memory_candidate_repository(tmp_path)

    def fail_accept(
        candidate_id: str,
        *,
        target_review_state: Literal["draft", "reviewed"] = "draft",
    ) -> MemoryEntry:
        assert target_review_state == "reviewed"
        raise accept_error

    monkeypatch.setattr(candidate_repo, "accept", fail_accept)
    curator = MemoryCurator(
        tmp_path,
        agent=agent,
        conversation_store=conversation_store,
        candidate_repository=candidate_repo,
    )

    result = curator.run_once()
    second = curator.run_once()

    assert result.created == 1
    assert second.processed_messages == 0
    assert len(agent.calls) == 1
    [candidate] = candidate_repo.list()
    assert candidate.review_state == "pending"
    [observation] = curator._test_observations.list()  # pyright: ignore[reportPrivateUsage]
    assert observation.status == "processed"
    event = [
        item
        for item in read_log_events(
            project_root=tmp_path,
            component="memory",
        )
        if item.event == "auto_accept_failed"
    ][-1]
    assert event.metadata == {
        "candidate_id": candidate.id,
        "action": "create",
        "memory_type": "episode",
        "target_entry_id": None,
    }
    assert event.error is not None
    assert expected_error in event.error
