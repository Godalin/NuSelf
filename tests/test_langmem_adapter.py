"""Tests for the optional LangMem curator adapter."""

from __future__ import annotations

from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

from nuself.llm import LLMSettings
from nuself.memory.langmem_adapter import LangMemCurator, _memory_type_from_content, _title_from_body  # type: ignore[reportPrivateUsage]


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
        curator.extract([HumanMessage(content="hello")])
    except RuntimeError as exc:
        assert "LLM API key is not configured" in str(exc)
        return
    raise AssertionError("expected RuntimeError")


class FakeExtractedMemory:
    def __init__(self, content: str) -> None:
        self.content = FakeMemoryContent(content)


class FakeMemoryContent:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeManager:
    def __init__(self) -> None:
        self.payload: dict[str, object] | None = None

    def invoke(self, state: dict[str, object]) -> list[object]:
        self.payload = state
        return [FakeExtractedMemory("User prefers concise output.")]


def test_langmem_curator_extracts_candidates_with_fake_manager(tmp_path: Path) -> None:
    curator = LangMemCurator(tmp_path, settings=LLMSettings(base_url="http://x", api_key="k", model="m"))
    manager = FakeManager()
    setattr(curator, "_manager", manager)

    messages = [
        HumanMessage(content="hello"),
        AIMessage(content="hi"),
    ]
    candidates = curator.extract(messages)
    assert manager.payload == {"messages": messages}

    assert len(candidates) == 1
    assert candidates[0].type == "preference"
    assert candidates[0].body == "User prefers concise output."
    assert candidates[0].action == "create"
    assert candidates[0].source_refs == ("langmem",)
