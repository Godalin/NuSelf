"""Tests for the optional LangMem curator adapter."""

from __future__ import annotations

from pathlib import Path

from nuself.llm import ChatMessage, LLMSettings
from nuself.memory.langmem_adapter import LangMemCurator, _memory_type_from_content, _title_from_body, _to_langmem_messages  # type: ignore[reportPrivateUsage]


def test_to_langmem_messages_converts_chat_messages() -> None:
    messages = [
        ChatMessage(role="user", content="hello"),
        ChatMessage(role="assistant", content="hi"),
    ]
    result = _to_langmem_messages(messages)
    assert result == [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]


def test_memory_type_from_content_detects_preference() -> None:
    assert _memory_type_from_content("I prefer dark mode.") == "preference"


def test_memory_type_from_content_defaults_to_episode() -> None:
    assert _memory_type_from_content("Something happened today.") == "episode"


def test_title_from_body_truncates_long_text() -> None:
    long_body = "A" * 100
    title = _title_from_body(long_body)
    assert title.endswith("...")
    assert len(title) == 48


def test_langmem_curator_raises_when_api_key_missing(tmp_path: Path) -> None:
    curator = LangMemCurator(tmp_path, settings=LLMSettings(base_url="", api_key="", model=""))
    try:
        curator.extract([ChatMessage(role="user", content="hello")])
    except RuntimeError as exc:
        assert "OPENAI_API_KEY is not configured" in str(exc)
        return
    raise AssertionError("expected RuntimeError")


class FakeExtractedMemory:
    def __init__(self, content: str) -> None:
        self.content = FakeMemoryContent(content)


class FakeMemoryContent:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeManager:
    def invoke(self, state: dict[str, object]) -> list[object]:
        return [FakeExtractedMemory("User prefers concise output.")]


def test_langmem_curator_extracts_candidates_with_fake_manager(tmp_path: Path) -> None:
    curator = LangMemCurator(tmp_path, settings=LLMSettings(base_url="http://x", api_key="k", model="m"))
    setattr(curator, "_manager", FakeManager())

    candidates = curator.extract([ChatMessage(role="user", content="hello")])

    assert len(candidates) == 1
    assert candidates[0].type == "preference"
    assert candidates[0].body == "User prefers concise output."
    assert candidates[0].action == "create"
    assert candidates[0].source_refs == ["langmem"]
