# pyright: reportPrivateUsage=false
from __future__ import annotations

from pathlib import Path

from nuself.domain.profile import ProfileItem
from nuself.llm import ChatMessage
from nuself.memory.intake import MemoryIntakeAgent, _extract_json_object, _local_title
from nuself.profile.repository import ProfileItemRepository


def test_memory_intake_locally_infers_goal() -> None:
    result = MemoryIntakeAgent().infer(body="My goal is to finish the memory system planning.")

    assert result.type == "goal"


def test_memory_intake_locally_infers_concept() -> None:
    result = MemoryIntakeAgent().infer(body="Temporal memory means preserving when a thought changed.")

    assert result.type == "concept"


def test_memory_intake_empty_body_raises() -> None:
    agent = MemoryIntakeAgent()
    try:
        agent.infer(body="")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "must not be empty" in str(exc)


def test_memory_intake_falls_back_on_invalid_llm_response() -> None:
    class BrokenLLM:
        def complete(self, messages: list[ChatMessage]) -> str:
            return "not valid json"

    agent = MemoryIntakeAgent(llm=BrokenLLM())
    result = agent.infer(body="I prefer dark mode.")

    assert result.type == "preference"
    assert result.confidence == 0.55


def test_memory_intake_local_inference_preference() -> None:
    result = MemoryIntakeAgent().infer(body="I like quiet mornings.")

    assert result.type == "preference"


def test_memory_intake_local_inference_belief() -> None:
    result = MemoryIntakeAgent().infer(body="I believe testing is essential.")

    assert result.type == "belief"


def test_memory_intake_local_inference_open_question() -> None:
    result = MemoryIntakeAgent().infer(body="What is the best way to organize memory?")

    assert result.type == "open_question"


def test_local_title_truncates_long_body() -> None:
    long_body = "A" * 100
    title = _local_title(long_body)
    assert title.endswith("...")
    assert len(title) == 48


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
