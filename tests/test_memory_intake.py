# pyright: reportPrivateUsage=false
from __future__ import annotations

from pathlib import Path

from nuself.domain.profile import ProfileItem
from nuself.llm import ChatMessage
from nuself.memory.intake import MemoryIntakeAgent, _extract_json_object
from nuself.profile.repository import ProfileItemRepository


def test_memory_intake_locally_infers_goal() -> None:
    llm = FakeIntakeLLM('{"type":"goal","title":"Finish memory system planning","tags":["planning"],"confidence":0.8}')
    result = MemoryIntakeAgent(llm=llm).infer(body="My goal is to finish the memory system planning.")

    assert result.type == "goal"


def test_memory_intake_locally_infers_concept() -> None:
    llm = FakeIntakeLLM('{"type":"concept","title":"Temporal memory preserves change","tags":["memory"],"confidence":0.7}')
    result = MemoryIntakeAgent(llm=llm).infer(body="Temporal memory means preserving when a thought changed.")

    assert result.type == "concept"


def test_memory_intake_empty_body_raises() -> None:
    agent = MemoryIntakeAgent()
    try:
        agent.infer(body="")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "must not be empty" in str(exc)


def test_memory_intake_raises_on_invalid_llm_response() -> None:
    class BrokenLLM:
        def complete(self, messages: list[ChatMessage]) -> str:
            return "not valid json"

    agent = MemoryIntakeAgent(llm=BrokenLLM())
    try:
        agent.infer(body="I prefer dark mode.")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "invalid JSON" in str(exc)


def test_memory_intake_requires_llm_tags() -> None:
    llm = FakeIntakeLLM('{"type":"preference","title":"Concise CLI output","tags":[],"confidence":0.8}')
    agent = MemoryIntakeAgent(llm=llm)

    try:
        agent.infer(body="I prefer concise CLI output.")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "invalid JSON" in str(exc)


def test_extract_json_object_strips_markdown_fences() -> None:
    raw = '```json\n{"type":"belief","title":"Test"}\n```'
    assert _extract_json_object(raw) == '{"type":"belief","title":"Test"}'


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
