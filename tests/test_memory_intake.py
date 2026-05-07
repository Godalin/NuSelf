from __future__ import annotations

from pathlib import Path

from nuself.domain.profile import ProfileItem
from nuself.llm import ChatMessage
from nuself.memory.intake import MemoryIntakeAgent
from nuself.profile.repository import ProfileItemRepository


def test_memory_intake_locally_infers_goal() -> None:
    result = MemoryIntakeAgent().infer(body="My goal is to finish the memory system planning.")

    assert result.type == "goal"


def test_memory_intake_locally_infers_concept() -> None:
    result = MemoryIntakeAgent().infer(body="Temporal memory means preserving when a thought changed.")

    assert result.type == "concept"


class FakeIntakeLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[list[ChatMessage]] = []

    def complete(self, messages: list[ChatMessage]) -> str:
        self.calls.append(messages)
        return self.response


def test_memory_intake_includes_profile_context_in_prompt(tmp_path: Path) -> None:
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
    llm = FakeIntakeLLM('{"type":"preference","title":"Concise CLI output","tags":["cli"],"confidence":0.8}')
    agent = MemoryIntakeAgent(tmp_path, llm=llm, profile_repository=profile_repo)

    agent.infer(body="I prefer concise CLI output.")

    system_prompt, user_prompt = llm.calls[0]
    assert "Consider existing profile items" in system_prompt.content
    assert "Existing profile items:" in user_prompt.content
    assert "Concise output" in user_prompt.content
