from __future__ import annotations

from collections.abc import Sequence
import json
from pathlib import Path
from typing import Literal

import pytest
from langchain_core.messages import BaseMessage

from nuself.agent.chat import ThreadMessage, ThreadState, ThreadStore
from nuself.agent.errors import AgentModelUnavailableError
from nuself.domain.memory import (
    MemoryEntry,
    MemoryObject,
    MemoryTypeRegistry,
    MemoryValidationIssue,
)
from nuself.domain.profile import ProfileItem
from nuself.logs import read_log_events
from nuself.memory.curator import (
    CuratorActionsOutput,
    MemoryCurator,
    MemoryCuratorSettings,
    _actions_from_output,  # pyright: ignore[reportPrivateUsage]
)
from nuself.memory.curator_plan import MemoryCuratorPlanStore
from nuself.memory.repository import (
    MemoryCandidateRepository,
    MemoryEntryRepository,
)
from nuself.profile.repository import ProfileItemRepository
from nuself.storage import get_default_backend


def _stored_record(
    root: Path,
    collection: str,
    record_id: str,
) -> dict[str, object] | None:
    return get_default_backend(root).collection(collection).get(record_id)


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
    thread_store = ThreadStore(tmp_path)
    thread_store.save(
        ThreadState(
            thread_id="default",
            messages=[
                ThreadMessage(
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
        thread_store=thread_store,
        settings=MemoryCuratorSettings(auto_accept=False),
    )

    result = curator.run_once()

    assert result.processed_messages == 0
    assert MemoryCandidateRepository(tmp_path).list() == []


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
    agent = _curator_agent(
        '{"actions":[{"action":"create","type":"episode","title":"Shared working memory",'
        '"body":"The user decided that terminals attached to one NuSelf mind should share short-term memory.",'
        '"tags":["memory"],"confidence":0.8,"reason":"important memory model decision"}]}'
    )
    repo = MemoryEntryRepository(tmp_path)
    curator = MemoryCurator(tmp_path, agent=agent, thread_store=thread_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

    result = curator.run_once()
    second_result = curator.run_once()
    candidates = MemoryCandidateRepository(tmp_path).list()

    assert result.processed_messages == 2
    assert result.created == 1
    assert second_result.processed_messages == 0
    assert len(candidates) == 1
    assert candidates[0].type == "episode"
    assert candidates[0].tags == ("memory",)
    assert candidates[0].review_state == "pending"
    assert candidates[0].source_refs == ("thread:default:0-2",)
    assert candidates[0].observed_at is not None
    assert candidates[0].evidence[0].source_type == "thread"
    assert candidates[0].evidence[0].source_ref == "thread:default:0-2"
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
    assert _stored_record(
        tmp_path, "memory_curator_cursors", "default"
    ) == {
        "id": "default",
        "thread_id": "default",
        "processed_message_count": 2,
    }


@pytest.mark.parametrize(
    "cursor_record",
    [
        {"thread_id": "other", "processed_message_count": 0},
        {"thread_id": "default", "processed_message_count": True},
        {"thread_id": "default", "processed_message_count": -1},
    ],
)
def test_memory_curator_rejects_corrupt_cursor_without_replay(
    tmp_path: Path,
    cursor_record: dict[str, object],
) -> None:
    thread_store = ThreadStore(tmp_path)
    thread_store.save(
        ThreadState(
            thread_id="default",
            messages=[
                ThreadMessage(
                    role="user",
                    content=(
                        "We decided that malformed cursor state must never "
                        "replay already processed durable conversation history."
                    ),
                )
            ],
        )
    )
    get_default_backend(tmp_path).collection(
        "memory_curator_cursors"
    ).put("default", cursor_record)
    agent = _curator_agent('{"actions":[]}')
    curator = MemoryCurator(
        tmp_path,
        agent=agent,
        thread_store=thread_store,
        settings=MemoryCuratorSettings(auto_accept=False),
    )

    with pytest.raises(
        ValueError,
        match="invalid memory curator cursor",
    ):
        curator.run_once()

    assert agent.calls == []
    assert MemoryCandidateRepository(tmp_path).list() == []
    event = read_log_events(
        project_root=tmp_path,
        component="memory",
    )[-1]
    assert event.event == "record_decode_failed"
    assert event.metadata == {
        "collection": "memory_curator_cursors",
        "record_id": "default",
    }


@pytest.mark.parametrize(
    ("auto_accept", "candidate_state"),
    [(False, "pending"), (True, "accepted")],
)
def test_memory_curator_resumes_saved_plan_after_cursor_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    auto_accept: bool,
    candidate_state: str,
) -> None:
    first_message = ThreadMessage(
        role="user",
        content=(
            "Remember that a failed curator cursor write must resume the "
            "saved decision without invoking the model again."
        ),
    )
    thread_store = ThreadStore(tmp_path)
    thread_store.save(
        ThreadState(thread_id="default", messages=[first_message])
    )
    agent = _curator_agent(
        '{"actions":[{"action":"create","type":"episode",'
        '"title":"Resumable curator plan",'
        '"body":"Cursor failure resumes the exact saved decision.",'
        '"tags":["memory"],"confidence":0.9,'
        '"reason":"explicit replay-safety requirement"}]}'
    )
    curator = MemoryCurator(
        tmp_path,
        agent=agent,
        thread_store=thread_store,
        settings=MemoryCuratorSettings(auto_accept=auto_accept),
    )
    real_cursor_put = curator._cursor_collection.put  # pyright: ignore[reportPrivateUsage]
    fail_cursor = True

    def fail_first_cursor_write(
        key: str,
        payload: dict[str, object],
    ) -> None:
        nonlocal fail_cursor
        if fail_cursor:
            fail_cursor = False
            raise OSError("cursor store unavailable")
        real_cursor_put(key, payload)

    monkeypatch.setattr(
        curator._cursor_collection,  # pyright: ignore[reportPrivateUsage]
        "put",
        fail_first_cursor_write,
    )

    with pytest.raises(OSError, match="cursor store unavailable"):
        curator.run_once()

    candidate_repo = MemoryCandidateRepository(tmp_path)
    [first_candidate] = candidate_repo.list(include_reviewed=True)
    thread_store.save(
        ThreadState(
            thread_id="default",
            messages=[
                first_message,
                ThreadMessage(
                    role="user",
                    content=(
                        "Remember that messages arriving during recovery "
                        "belong to the next curator range."
                    ),
                ),
            ],
        )
    )

    resumed = curator.run_once()

    assert resumed.processed_messages == 1
    assert resumed.created == 1
    assert len(agent.calls) == 1
    [resumed_candidate] = candidate_repo.list(include_reviewed=True)
    assert resumed_candidate == first_candidate
    assert resumed_candidate.review_state == candidate_state
    assert resumed_candidate.source_refs == ("thread:default:0-1",)
    assert len(MemoryEntryRepository(tmp_path).list()) == int(auto_accept)
    assert _stored_record(
        tmp_path, "memory_curator_cursors", "default"
    ) == {
        "id": "default",
        "thread_id": "default",
        "processed_message_count": 1,
    }

    later = curator.run_once()

    assert later.processed_messages == 1
    assert len(agent.calls) == 2
    candidates = candidate_repo.list(include_reviewed=True)
    assert len(candidates) == 2
    assert {candidate.source_refs for candidate in candidates} == {
        ("thread:default:0-1",),
        ("thread:default:1-2",),
    }
    assert _stored_record(
        tmp_path, "memory_curator_cursors", "default"
    ) == {
        "id": "default",
        "thread_id": "default",
        "processed_message_count": 2,
    }


def test_memory_curator_plan_write_fails_before_candidate_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread_store = ThreadStore(tmp_path)
    thread_store.save(
        ThreadState(
            thread_id="default",
            messages=[
                ThreadMessage(
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

    plan_store = MemoryCuratorPlanStore(tmp_path)

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
        thread_store=thread_store,
        settings=MemoryCuratorSettings(auto_accept=False),
        plan_store=plan_store,
    )

    with pytest.raises(OSError, match="plan store unavailable"):
        curator.run_once()

    assert len(agent.calls) == 1
    assert MemoryCandidateRepository(tmp_path).list() == []
    assert (
        get_default_backend(tmp_path)
        .collection("memory_curator_cursors")
        .get("default")
        is None
    )


def test_memory_curator_rejects_incompatible_plan_without_model_replay(
    tmp_path: Path,
) -> None:
    thread_store = ThreadStore(tmp_path)
    thread_store.save(
        ThreadState(
            thread_id="default",
            messages=[
                ThreadMessage(
                    role="user",
                    content=(
                        "Remember that incompatible curator plans require "
                        "repair instead of speculative model replay."
                    ),
                )
            ],
        )
    )
    get_default_backend(tmp_path).collection(
        "memory_curator_plans"
    ).put(
        "default",
        {
                "thread_id": "default",
                "source_start": 0,
                "source_end": 2,
                "observed_at": "2026-07-29T00:00:00+00:00",
                "actions": [
                    {
                        "action": "ignore",
                        "title": "",
                        "body": "",
                        "type": "episode",
                        "tags": [],
                        "entry_id": None,
                        "confidence": 0.6,
                        "reason": "no durable signal",
                    }
                ],
            },
    )
    agent = _curator_agent('{"actions":[]}')
    curator = MemoryCurator(
        tmp_path,
        agent=agent,
        thread_store=thread_store,
        settings=MemoryCuratorSettings(auto_accept=False),
    )

    with pytest.raises(ValueError, match="invalid memory curator plan"):
        curator.run_once()

    assert agent.calls == []
    assert MemoryCandidateRepository(tmp_path).list() == []
    event = read_log_events(
        project_root=tmp_path,
        component="memory",
    )[-1]
    assert event.event == "record_decode_failed"
    assert event.metadata == {
        "collection": "memory_curator_plans",
        "record_id": "default",
    }


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
    agent = _curator_agent(
        '{"actions":[{"action":"update","entry_id":"'
        + existing.id
        + '","title":"Memory preview style","body":"The user prefers concise memory previews.",'
        '"tags":["memory","preview"],"confidence":0.75,"reason":"user clarified preview style"}]}'
    )
    curator = MemoryCurator(tmp_path, agent=agent, thread_store=thread_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

    result = curator.run_once()
    candidates = MemoryCandidateRepository(tmp_path).list()

    assert result.updated == 1
    assert candidates[0].body == "The user prefers concise memory previews."
    assert candidates[0].tags == ("memory", "preview")
    assert candidates[0].action == "update"
    assert candidates[0].target_entry_id == existing.id
    assert candidates[0].source_refs == ("thread:default:0-2",)
    assert candidates[0].observed_at is not None
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
    agent = _curator_agent('{"actions":[{"action":"ignore","reason":"no durable memory"}]}')
    curator = MemoryCurator(tmp_path, agent=agent, thread_store=thread_store, profile_repository=profile_repo, settings=MemoryCuratorSettings(auto_accept=False))

    curator.run_once()

    system_prompt, user_prompt = agent.calls[0]
    assert "Consider existing profile items" in system_prompt.text
    assert "Existing profile items:" in user_prompt.text
    assert "Concise output" in user_prompt.text


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
    class FailingCuratorAgent:
        def invoke(
            self,
            messages: Sequence[BaseMessage],
        ) -> CuratorActionsOutput:
            raise AgentModelUnavailableError("LLM unavailable")

    repo = MemoryEntryRepository(tmp_path)
    curator = MemoryCurator(tmp_path, agent=FailingCuratorAgent(), thread_store=thread_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

    result = curator.run_once()

    assert result.processed_messages == 0
    assert result.created == 0
    assert repo.list() == []


def test_memory_curator_contention_is_deferred_without_model_or_mutation(
    tmp_path: Path,
) -> None:
    thread_store = ThreadStore(tmp_path)
    thread_store.save(
        ThreadState(
            thread_id="default",
            messages=[
                ThreadMessage(
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
        thread_store=thread_store,
        settings=MemoryCuratorSettings(auto_accept=False),
    )

    with MemoryCuratorPlanStore(tmp_path).exclusive("default"):
        result = curator.run_once()

    assert result.processed_messages == 0
    assert result.created == 0
    assert result.updated == 0
    assert result.ignored == 0
    assert agent.calls == []
    assert MemoryCandidateRepository(tmp_path).list() == []
    assert _stored_record(
        tmp_path, "memory_curator_cursors", "default"
    ) is None
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
    assert events[0].metadata == {"thread_id": "default"}


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
    thread_store = ThreadStore(tmp_path)
    thread_store.save(
        ThreadState(
            thread_id="default",
            messages=[
                ThreadMessage(
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
        thread_store=thread_store,
        settings=MemoryCuratorSettings(auto_accept=False),
    )

    with pytest.raises(type(failure)) as captured:
        curator.run_once()

    assert captured.value is failure


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
    agent = _curator_agent('{"actions":[{"action":"ignore","reason":"trivial name ping"}]}')
    repo = MemoryEntryRepository(tmp_path)
    curator = MemoryCurator(tmp_path, agent=agent, thread_store=thread_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

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
    thread_store = ThreadStore(tmp_path)
    thread_store.save(
        ThreadState(
            thread_id="default",
            messages=[ThreadMessage(role="user", content=content)],
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
        thread_store=thread_store,
        settings=MemoryCuratorSettings(auto_accept=False),
    )

    result = curator.run_once()

    assert result.processed_messages == 1
    assert result.created == 1
    assert len(agent.calls) == 1
    assert len(MemoryCandidateRepository(tmp_path).list()) == 1


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
    agent = _curator_agent(
        '{"actions":[{"action":"create","type":"belief","title":"Memory quality threshold",'
        '"body":"The user wants memory curation to depend on discussion depth and quality, not turn count.",'
        '"tags":["memory"],"confidence":0.85,"reason":"explicit memory-system decision"}]}'
    )
    repo = MemoryEntryRepository(tmp_path)
    curator = MemoryCurator(tmp_path, agent=agent, thread_store=thread_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

    result = curator.run_once()
    candidates = MemoryCandidateRepository(tmp_path).list()

    assert result.processed_messages == 1
    assert result.created == 1
    assert candidates[0].type == "belief"
    assert candidates[0].source_refs == ("thread:default:0-1",)


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
    get_default_backend(tmp_path).collection(
        "memory_curator_cursors"
    ).put(
        "default",
        {
            "thread_id": "default",
            "processed_message_count": 4,
        },
    )
    agent = _curator_agent(
        '{"actions":[{"action":"create","type":"episode","title":"Compressed cursor continuity",'
        '"body":"Memory curation should continue after thread compression by using absolute message indexes.",'
        '"tags":["memory"],"confidence":0.8,"reason":"cursor correctness"}]}'
    )
    repo = MemoryEntryRepository(tmp_path)
    curator = MemoryCurator(tmp_path, agent=agent, thread_store=thread_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

    result = curator.run_once()
    second_result = curator.run_once()
    candidates = MemoryCandidateRepository(tmp_path).list()

    assert result.processed_messages == 2
    assert result.created == 1
    assert second_result.processed_messages == 0
    assert candidates[0].source_refs == ("thread:default:4-6",)


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
    agent = _curator_agent(
        '{"actions":[{"action":"create","type":"episode","title":"Raw transcript",'
        '"body":"user: We need conservative memory updates. assistant: I will avoid raw transcript memory.",'
        '"tags":["memory"],"confidence":0.9,"reason":"bad raw transcript"}]}'
    )
    repo = MemoryEntryRepository(tmp_path)
    curator = MemoryCurator(tmp_path, agent=agent, thread_store=thread_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

    result = curator.run_once()

    assert result.processed_messages == 0
    assert repo.list() == []


def test_memory_curator_rejects_create_without_tags(tmp_path: Path) -> None:
    thread_store = ThreadStore(tmp_path)
    thread_store.save(
        ThreadState(
            thread_id="default",
            messages=[
                ThreadMessage(role="user", content="Remember that memory entries need explicit tags."),
                ThreadMessage(role="assistant", content="I will require tags on curated memory candidates."),
            ],
        )
    )
    agent = _curator_agent(
        '{"actions":[{"action":"create","type":"episode","title":"Missing tags",'
        '"body":"Curated memory candidates should include tags.",'
        '"confidence":0.9,"reason":"bad missing tags"}]}'
    )
    repo = MemoryEntryRepository(tmp_path)
    curator = MemoryCurator(tmp_path, agent=agent, thread_store=thread_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

    result = curator.run_once()

    assert result.processed_messages == 0
    assert MemoryCandidateRepository(tmp_path).list() == []
    assert repo.list() == []


def test_memory_curator_rejects_unknown_memory_type(tmp_path: Path) -> None:
    thread_store = ThreadStore(tmp_path)
    thread_store.save(
        ThreadState(
            thread_id="default",
            messages=[
                ThreadMessage(role="user", content="Remember that unknown memory types should not be coerced."),
                ThreadMessage(role="assistant", content="I will reject unsupported memory action types."),
            ],
        )
    )
    agent = _curator_agent(
        '{"actions":[{"action":"create","type":"made_up_type","title":"Unknown type",'
        '"body":"Unknown memory types should not be silently coerced.",'
        '"tags":["memory"],"confidence":0.9,"reason":"bad unknown type"}]}'
    )
    repo = MemoryEntryRepository(tmp_path)
    curator = MemoryCurator(
        tmp_path,
        agent=agent,
        thread_store=thread_store,
        repository=repo,
        settings=MemoryCuratorSettings(auto_accept=False),
    )

    result = curator.run_once()

    assert result.processed_messages == 0
    assert MemoryCandidateRepository(tmp_path).list() == []
    assert repo.list() == []


def test_memory_curator_accepts_typed_structured_output(
    tmp_path: Path,
) -> None:
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
    agent = _curator_agent(
        '{"actions":[{"action":"create","type":"episode","title":"Structured memory decisions",'
        '"body":"The user wants memory updates to be decided by an agent and dispatched as structured actions.",'
        '"tags":["memory"],"confidence":0.82,"reason":"durable memory-system decision"}]}'
    )
    repo = MemoryEntryRepository(tmp_path)
    curator = MemoryCurator(tmp_path, agent=agent, thread_store=thread_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

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
    agent = _curator_agent(
        '{"actions":[{"action":"create","type":"episode","title":"Descriptor validation",'
        '"body":"Curator writes should pass descriptor validation before persistence.",'
        '"tags":["memory"],"confidence":0.8,"reason":"typed memory pipeline"}]}'
    )
    repo = MemoryEntryRepository(tmp_path, registry=MemoryTypeRegistry([RejectingEpisodeDescriptor()]))
    curator = MemoryCurator(tmp_path, agent=agent, thread_store=thread_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

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
    agent = _curator_agent(
        '{"actions":[{"action":"create","type":"episode","title":"Shared working memory",'
        '"body":"The user really likes shared working memory.",'
        '"tags":["memory"],"confidence":0.8,"reason":"duplicate detection test"}]}'
    )
    curator = MemoryCurator(tmp_path, agent=agent, thread_store=thread_store, repository=repo, settings=MemoryCuratorSettings(auto_accept=False))

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
    agent = _curator_agent(
        '{"actions":[{"action":"create","type":"belief","title":"Interest in Rust",'
        '"body":"The user wants to learn Rust for systems programming.",'
        '"tags":["rust"],"confidence":0.85,"reason":"explicit learning goal"}]}'
    )
    repo = MemoryEntryRepository(tmp_path)
    curator = MemoryCurator(tmp_path, agent=agent, thread_store=thread_store, repository=repo)

    result = curator.run_once()

    # Candidate was auto-accepted → it's now an entry
    entries = repo.list()
    assert len(entries) == 1
    assert entries[0].title == "Interest in Rust"
    assert entries[0].tags == ("rust",)
    assert entries[0].review_state == "reviewed"
    assert result.created == 1

    # Candidate exists but is marked accepted
    candidates = MemoryCandidateRepository(tmp_path).list(include_reviewed=True)
    assert len(candidates) == 1
    assert candidates[0].review_state == "accepted"


def test_curator_audit_failure_cannot_replay_committed_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread_store = ThreadStore(tmp_path)
    thread_store.save(
        ThreadState(
            thread_id="default",
            messages=[
                ThreadMessage(
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
        thread_store=thread_store,
        settings=MemoryCuratorSettings(auto_accept=False),
    )

    with pytest.warns(RuntimeWarning) as captured:
        result = curator.run_once()

    assert result.created == 1
    assert len(MemoryCandidateRepository(tmp_path).list()) == 1
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

    thread_store = ThreadStore(tmp_path)
    thread_store.save(
        ThreadState(
            thread_id="default",
            messages=[
                ThreadMessage(
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
    repository = MemoryEntryRepository(tmp_path)
    curator = MemoryCurator(
        tmp_path,
        agent=agent,
        thread_store=thread_store,
        repository=repository,
        trace_recorder=TraceRecorder(tmp_path),
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
    from nuself.trace.service import TraceQueryService, TraceRecorder

    thread_store = ThreadStore(tmp_path)
    thread_store.save(
        ThreadState(
            thread_id="default",
            messages=[
                ThreadMessage(
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
    repository = MemoryEntryRepository(tmp_path)
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
        thread_store=thread_store,
        repository=repository,
        trace_recorder=TraceRecorder(tmp_path),
    )

    result = curator.run_once()

    assert result.updated == 1
    [trace] = TraceQueryService(tmp_path).list_traces(
        kind="memory_update"
    )
    assert trace.metadata["action"] == "update"


def test_memory_curator_reports_recoverable_auto_accept_failure(
    tmp_path: Path,
) -> None:
    thread_store = ThreadStore(tmp_path)
    thread_store.save(
        ThreadState(
            thread_id="default",
            messages=[
                ThreadMessage(
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
    repo = MemoryEntryRepository(
        tmp_path,
        registry=MemoryTypeRegistry([RejectingEpisodeDescriptor()]),
    )
    curator = MemoryCurator(
        tmp_path,
        agent=agent,
        thread_store=thread_store,
        repository=repo,
    )

    result = curator.run_once()
    second = curator.run_once()

    assert result.created == 1
    assert second.processed_messages == 0
    assert len(agent.calls) == 1
    assert repo.list() == []
    candidates = MemoryCandidateRepository(tmp_path).list()
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
    thread_store = ThreadStore(tmp_path)
    thread_store.save(
        ThreadState(
            thread_id="default",
            messages=[
                ThreadMessage(
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
    candidate_repo = MemoryCandidateRepository(tmp_path)

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
        thread_store=thread_store,
        candidate_repository=candidate_repo,
    )

    result = curator.run_once()
    second = curator.run_once()

    assert result.created == 1
    assert second.processed_messages == 0
    assert len(agent.calls) == 1
    [candidate] = candidate_repo.list()
    assert candidate.review_state == "pending"
    assert _stored_record(
        tmp_path, "memory_curator_cursors", "default"
    ) == {
        "id": "default",
        "thread_id": "default",
        "processed_message_count": 1,
    }
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
