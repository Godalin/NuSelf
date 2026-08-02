from __future__ import annotations

# pyright: reportUnusedImport=false

from memory_fixtures import (
    memory_candidate_repository,
    memory_entry_repository,
    source_repository,
)

from collections.abc import Sequence
from pathlib import Path

import pytest
from langchain_core.messages import BaseMessage

import nuself.runtime.observability as observability
from nuself.agent.errors import AgentModelUnavailableError
from nuself.config import runtime_paths
from nuself.memory.model import MemoryEntry
from nuself.profile.model import ProfileItem
from nuself.logs import read_log_events
from nuself.memory.optimizer import (
    MemoryOptimizer,
    MemoryOptimizerSettings,
    OptimizeActionsOutput,
    _optimize_actions_from_output,  # pyright: ignore[reportPrivateUsage]
)
from nuself.memory.repository import MemoryCandidateRepository, MemoryEntryRepository
from nuself.profile.repository import ProfileItemRepository
from tests.backend import owned_backend


class FakeOptimizerAgent:
    def __init__(self, output: OptimizeActionsOutput) -> None:
        self.output = output
        self.calls: list[Sequence[BaseMessage]] = []

    def invoke(
        self,
        messages: Sequence[BaseMessage],
    ) -> OptimizeActionsOutput:
        self.calls.append(messages)
        return self.output


def _optimizer_agent(response: str) -> FakeOptimizerAgent:
    return FakeOptimizerAgent(
        OptimizeActionsOutput.model_validate_json(response)
    )


def _optimizer(
    project_root: Path,
    *,
    agent: object,
    repository: MemoryEntryRepository,
    profile_repository: ProfileItemRepository | None = None,
    settings: MemoryOptimizerSettings | None = None,
) -> MemoryOptimizer:
    profile = profile_repository or ProfileItemRepository(
        runtime_paths(project_root),
        backend=owned_backend(project_root),
    )
    return MemoryOptimizer(
        runtime_paths(project_root),
        agent=agent,  # type: ignore[arg-type]
        settings=settings,
        repository=repository,
        candidate_repository=memory_candidate_repository(
            project_root,
            entry_repository=repository,
            profile_repository=profile,
        ),
        profile_repository=profile,
    )


def test_memory_optimizer_updates_and_deletes_duplicate_entries(tmp_path: Path) -> None:
    repo = memory_entry_repository(tmp_path)
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
    agent = _optimizer_agent(
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
    optimizer = _optimizer(tmp_path, agent=agent, repository=repo)

    result = optimizer.run_once()
    entries = repo.list()
    candidates = memory_candidate_repository(tmp_path).list()

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
    events = read_log_events(project_root=tmp_path, component="memory")
    assert [event.event for event in events] == [
        "optimizer_candidate_staged",
        "optimizer_candidate_staged",
        "optimizer_completed",
    ]
    assert events[-1].metadata == {
        "reviewed": 2,
        "updated": 1,
        "deleted": 1,
        "ignored": 0,
    }
    assert {
        event.metadata["action"]
        for event in events[:-1]
        if event.metadata is not None
    } == {"update", "delete"}
    raw_log = result.log_path.read_text(encoding="utf-8")
    assert "merged overlapping entries" not in raw_log
    assert "fully merged into" not in raw_log


def test_memory_optimizer_includes_profile_context_in_prompt(tmp_path: Path) -> None:
    repo = memory_entry_repository(tmp_path)
    repo.save(MemoryEntry(type="belief", title="Keep memory concise", body="The user wants concise memory entries."))
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
    agent = _optimizer_agent('{"actions":[{"action":"ignore","entry_id":"unused","reason":"no changes"}]}')
    optimizer = _optimizer(
        tmp_path,
        agent=agent,
        repository=repo,
        profile_repository=profile_repo,
    )

    optimizer.run_once()

    system_prompt, user_prompt = agent.calls[0]
    assert "Consider existing profile items" in system_prompt.text
    assert "Existing profile items:" in user_prompt.text
    assert "Concise output" in user_prompt.text


def test_memory_optimizer_defers_without_agent_decision(tmp_path: Path) -> None:
    repo = memory_entry_repository(tmp_path)
    entry = repo.save(
        MemoryEntry(
            type="belief",
            title="Keep memory concise",
            body="The user wants concise memory entries.",
        )
    )
    class FailingOptimizerAgent:
        def invoke(
            self,
            messages: Sequence[BaseMessage],
        ) -> OptimizeActionsOutput:
            raise AgentModelUnavailableError("LLM unavailable")

    optimizer = _optimizer(
        tmp_path,
        agent=FailingOptimizerAgent(),
        repository=repo,
    )

    result = optimizer.run_once()

    assert result.reviewed == 0
    assert result.updated == 0
    assert result.deleted == 0
    assert repo.get(entry.id).body == "The user wants concise memory entries."
    [event] = read_log_events(project_root=tmp_path, component="memory")
    assert event.event == "optimizer_deferred"
    assert event.metadata == {"reviewed": 0}
    assert "LLM unavailable" not in result.log_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "failure",
    [
        RuntimeError("optimizer implementation failed"),
        ValueError("optimizer implementation returned invalid state"),
    ],
)
def test_memory_optimizer_propagates_untyped_agent_errors(
    tmp_path: Path,
    failure: Exception,
) -> None:
    repo = memory_entry_repository(tmp_path)
    repo.save(
        MemoryEntry(
            type="belief",
            title="Keep memory concise",
            body="The user wants concise memory entries.",
        )
    )

    class BrokenOptimizerAgent:
        def invoke(
            self,
            messages: Sequence[BaseMessage],
        ) -> OptimizeActionsOutput:
            del messages
            raise failure

    optimizer = _optimizer(
        tmp_path,
        agent=BrokenOptimizerAgent(),
        repository=repo,
    )

    with pytest.raises(type(failure)) as captured:
        optimizer.run_once()

    assert captured.value is failure


def test_memory_optimizer_audit_failure_cannot_replace_persisted_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = memory_entry_repository(tmp_path)
    entry = repo.save(
        MemoryEntry(
            type="belief",
            title="Original",
            body="Original durable memory.",
        )
    )
    agent = _optimizer_agent(
        '{"actions":[{"action":"update","entry_id":"'
        + entry.id
        + '","title":"Improved","body":"Improved durable memory.",'
        '"reason":"clearer"}]}'
    )
    optimizer = _optimizer(tmp_path, agent=agent, repository=repo)

    def fail_log_write(*args: object, **kwargs: object) -> object:
        raise OSError("log unavailable")

    monkeypatch.setattr(observability, "write_log_event", fail_log_write)
    monkeypatch.setattr(observability, "write_audit_envelope", fail_log_write)

    with pytest.warns(
        RuntimeWarning,
        match="runtime/observability_sink_failed",
    ):
        result = optimizer.run_once()

    assert result.updated == 1
    [candidate] = memory_candidate_repository(tmp_path).list()
    assert candidate.action == "update"
    assert candidate.target_entry_id == entry.id
    assert read_log_events(project_root=tmp_path, component="memory") == []


def test_memory_optimizer_rejects_raw_transcript_body(tmp_path: Path) -> None:
    repo = memory_entry_repository(tmp_path)
    entry = repo.save(
        MemoryEntry(
            type="episode",
            title="Messy transcript",
            body="A messy memory entry.",
        )
    )
    agent = _optimizer_agent(
        '{"actions":[{"action":"update","entry_id":"'
        + entry.id
        + '","title":"Raw transcript","body":"user: hello assistant: hi",'
        '"reason":"bad transcript"}]}'
    )
    optimizer = _optimizer(tmp_path, agent=agent, repository=repo)

    result = optimizer.run_once()

    assert result.reviewed == 0
    assert repo.get(entry.id).title == "Messy transcript"


def test_memory_optimizer_uses_registry_memory_types(tmp_path: Path) -> None:
    repo = memory_entry_repository(tmp_path)
    entry = repo.save(
        MemoryEntry(
            type="instruction",
            title="Old instruction",
            body="Old instruction body.",
        )
    )
    agent = _optimizer_agent(
        '{"actions":[{"action":"update","entry_id":"'
        + entry.id
        + '","type":"persona_instruction","title":"Persona instruction",'
        '"body":"Use persona instructions as durable behavior guidance.",'
        '"tags":["persona"],"confidence":0.8,"reason":"new typed memory type"}]}'
    )
    optimizer = _optimizer(tmp_path, agent=agent, repository=repo)

    result = optimizer.run_once()
    candidates = memory_candidate_repository(tmp_path).list()

    assert result.updated == 1
    assert candidates[0].type == "persona_instruction"


def test_memory_optimizer_rejects_unknown_memory_type(tmp_path: Path) -> None:
    repo = memory_entry_repository(tmp_path)
    entry = repo.save(
        MemoryEntry(
            type="belief",
            title="Known type",
            body="Known type body.",
        )
    )
    agent = _optimizer_agent(
        '{"actions":[{"action":"update","entry_id":"'
        + entry.id
        + '","type":"made_up_type","title":"Bad type",'
        '"body":"Unknown memory types should not be silently accepted.",'
        '"tags":["memory"],"confidence":0.8,"reason":"bad type"}]}'
    )
    optimizer = _optimizer(tmp_path, agent=agent, repository=repo)

    result = optimizer.run_once()

    assert result.reviewed == 0
    assert memory_candidate_repository(tmp_path).list() == []


@pytest.mark.parametrize(
    "response",
    [
        '{"actions":[{"action":"ignore","entry_id":"","reason":"missing id"}]}',
        '{"actions":[{"action":"ignore","entry_id":"mem_1","confidence":1.2}]}',
        '{"actions":[{"action":"ignore","entry_id":"mem_1","confidence":true}]}',
        '{"actions":[{"action":"ignore","entry_id":"mem_1","unknown":"value"}]}',
        '{"actions":[{"action":"update","entry_id":"mem_1","title":" ","body":"Summary"}]}',
        '{"actions":[{"action":"update","entry_id":"mem_1","title":"Summary","body":" "}]}',
        '{"actions":[{"action":"update","entry_id":"mem_1","title":"Summary",'
        '"body":"Summary body","type":"unknown"}]}',
    ],
)
def test_parse_optimizer_actions_rejects_invalid_schema(response: str) -> None:
    with pytest.raises(ValueError):
        output = OptimizeActionsOutput.model_validate_json(response)
        _optimize_actions_from_output(
            output,
            allowed_types=("belief", "episode"),
        )


def test_memory_optimizer_rejects_complete_mixed_valid_invalid_batch(tmp_path: Path) -> None:
    repo = memory_entry_repository(tmp_path)
    entry = repo.save(
        MemoryEntry(
            type="belief",
            title="Keep memory concise",
            body="The user wants concise memory entries.",
        )
    )
    agent = _optimizer_agent(
        '{"actions":[{"action":"update","entry_id":"'
        + entry.id
        + '","title":"Concise memory","body":"Keep durable memories concise.",'
        '"reason":"compress"},{"action":"delete","entry_id":"","reason":"invalid sibling"}]}'
    )
    optimizer = _optimizer(tmp_path, agent=agent, repository=repo)

    result = optimizer.run_once()

    assert result.reviewed == 0
    assert result.updated == 0
    assert result.deleted == 0
    assert memory_candidate_repository(tmp_path).list() == []


def test_memory_optimizer_respects_limit(tmp_path: Path) -> None:
    repo = memory_entry_repository(tmp_path)
    for title in ["First", "Second"]:
        repo.save(MemoryEntry(type="belief", title=title, body=f"{title} body."))
    agent = _optimizer_agent('{"actions":[{"action":"ignore","entry_id":"unused","reason":"no changes"}]}')
    optimizer = _optimizer(
        tmp_path,
        agent=agent,
        repository=repo,
        settings=MemoryOptimizerSettings(memory_limit=1),
    )

    result = optimizer.run_once()

    assert result.reviewed == 1
from nuself.config import runtime_paths
