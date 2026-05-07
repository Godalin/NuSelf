from __future__ import annotations

from pathlib import Path

from nuself.agent.chat import ChatAgent, ChatAgentSettings, ThreadMessage, ThreadState, ThreadStore
from nuself.domain.memory import MemoryEntry
from nuself.domain.profile import ProfileItem
from nuself.llm import ChatMessage
from nuself.memory.query import MemoryQueryService
from nuself.memory.repository import MemoryEntryRepository
from nuself.memory.source_repository import SourceRepository
from nuself.profile.repository import ProfileItemRepository


class FakeLLM:
    def __init__(self) -> None:
        self.calls: list[list[ChatMessage]] = []

    def complete(self, messages: list[ChatMessage]) -> str:
        self.calls.append(messages)
        if "Compress a private NuSelf conversation" in messages[0].content:
            return "compressed context"
        return "agent reply"


class StructuredFakeLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[list[ChatMessage]] = []

    def complete(self, messages: list[ChatMessage]) -> str:
        self.calls.append(messages)
        return self.response


def test_chat_agent_includes_memory_entries(tmp_path: Path) -> None:
    repo = MemoryEntryRepository(tmp_path)
    repo.save(
        MemoryEntry(
            type="belief",
            title="Clarity matters",
            body="Prefer explicit assumptions.",
            tags=["style"],
        )
    )
    llm = FakeLLM()
    agent = ChatAgent(tmp_path, llm=llm, memory_query_service=MemoryQueryService(repo))

    result = agent.respond("clarity assumptions")

    assert result.reply == "agent reply"
    system_prompt = llm.calls[0][0].content
    assert "Clarity matters" in system_prompt
    assert "Prefer explicit assumptions." in system_prompt


def test_chat_agent_omits_irrelevant_memory_entries(tmp_path: Path) -> None:
    repo = MemoryEntryRepository(tmp_path)
    repo.save(
        MemoryEntry(
            type="belief",
            title="Clarity matters",
            body="Prefer explicit assumptions.",
            tags=["style"],
        )
    )
    llm = FakeLLM()
    agent = ChatAgent(tmp_path, llm=llm, memory_query_service=MemoryQueryService(repo))

    agent.respond("weather forecast")

    system_prompt = llm.calls[0][0].content
    assert "Relevant memory context:" not in system_prompt
    assert "Clarity matters" not in system_prompt


def test_chat_agent_includes_source_chunks_by_default(tmp_path: Path) -> None:
    source_path = tmp_path / "source.md"
    source_path.write_text(
        "\n".join(
            [
                "---",
                "title: Source Evidence",
                "tags: [evidence]",
                "---",
                "Source chunks can support durable answers.",
            ]
        ),
        encoding="utf-8",
    )
    SourceRepository(tmp_path).ingest_path(source_path)
    llm = FakeLLM()
    agent = ChatAgent(tmp_path, llm=llm)

    agent.respond("durable source evidence")

    system_prompt = llm.calls[0][0].content
    assert "Relevant memory context:" in system_prompt
    assert "Source chunks:" in system_prompt
    assert "Source Evidence" in system_prompt
    assert "ref=source:" in system_prompt


def test_chat_agent_includes_profile_items_by_default(tmp_path: Path) -> None:
    profile_repo = ProfileItemRepository(tmp_path)
    profile_repo.save(
        ProfileItem(
            type="profile_fact",
            title="Direct style",
            body="Prefer direct answers.",
            tags=["style"],
            source_refs=["source:profile:0"],
        )
    )
    llm = FakeLLM()
    agent = ChatAgent(tmp_path, llm=llm, memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path), profile_repository=profile_repo))

    agent.respond("direct answers")

    system_prompt = llm.calls[0][0].content
    assert "Profile items:" in system_prompt
    assert "Direct style" in system_prompt
    assert "source:profile:0" in system_prompt


def test_chat_agent_parses_structured_response(tmp_path: Path) -> None:
    llm = StructuredFakeLLM(
        '{"answer":"Use the profile context.","evidence_references":["mem_123","source:note:0"],'
        '"confidence":0.92,"epistemic_status":"grounded"}'
    )
    agent = ChatAgent(tmp_path, llm=llm, memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)))

    result = agent.respond("profile context")

    assert result.answer == "Use the profile context."
    assert result.reply == "Use the profile context."
    assert result.evidence_references == ("mem_123", "source:note:0")
    assert result.confidence == 0.92
    assert result.epistemic_status == "grounded"
    assert llm.calls[0][0].content.startswith("You are NuSelf")
    thread_path = tmp_path / "private" / "threads" / "default.json"
    text = thread_path.read_text(encoding="utf-8")
    assert "Use the profile context." in text


def test_chat_agent_flags_unsupported_personal_claims_without_evidence(tmp_path: Path) -> None:
    llm = StructuredFakeLLM(
        '{"answer":"You prefer concise output.","evidence_references":[],"confidence":0.81,"epistemic_status":"grounded"}'
    )
    agent = ChatAgent(tmp_path, llm=llm, memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)))

    result = agent.respond("what do I prefer?")

    assert result.epistemic_status == "unsupported"
    assert result.confidence == 0.25
    assert result.evidence_references == ()
    assert result.reply == "You prefer concise output."


def test_chat_agent_compresses_old_context(tmp_path: Path) -> None:
    llm = FakeLLM()
    settings = ChatAgentSettings(recent_messages=2, summary_trigger_messages=4, summary_target_chars=200)
    agent = ChatAgent(tmp_path, llm=llm, settings=settings)

    agent.respond("one")
    agent.respond("two")
    agent.respond("three")

    thread_path = tmp_path / "private" / "threads" / "default.json"
    text = thread_path.read_text(encoding="utf-8")

    assert "compressed context" in text
    assert text.count('"role"') == 2


def test_chat_agent_uses_local_summary_without_api_key(tmp_path: Path) -> None:
    settings = ChatAgentSettings(recent_messages=2, summary_trigger_messages=4, summary_target_chars=800)
    agent = ChatAgent(tmp_path, settings=settings)

    agent.respond("one")
    agent.respond("two")
    agent.respond("three")

    thread_path = tmp_path / "private" / "threads" / "default.json"
    text = thread_path.read_text(encoding="utf-8")

    assert "OPENAI_API_KEY is not configured" not in text
    assert '"content": "three"' in text
    assert '"summary":' in text


def test_chat_agent_drops_old_local_fallback_replies(tmp_path: Path) -> None:
    thread_store = ThreadStore(tmp_path)
    thread_store.save(
        ThreadState(
            thread_id="default",
            messages=[
                ThreadMessage(role="user", content="old question"),
                ThreadMessage(
                    role="assistant",
                    content=(
                        "LLM API is not configured yet. I saved the message and can use local memory/context, "
                        "but real reasoning needs NUSELF_LLM_API_KEY. Last message: old question"
                    ),
                ),
            ],
        )
    )
    llm = FakeLLM()
    agent = ChatAgent(tmp_path, llm=llm, thread_store=thread_store)

    agent.respond("new question")

    prompt_text = "\n".join(message.content for message in llm.calls[0])
    saved_text = (tmp_path / "private" / "threads" / "default.json").read_text(encoding="utf-8")
    assert "LLM API is not configured yet" not in prompt_text
    assert "LLM API is not configured yet" not in saved_text
    assert "old question" in prompt_text


def test_thread_store_update_writes_under_transaction(tmp_path: Path) -> None:
    thread_store = ThreadStore(tmp_path)

    def add_message(state: ThreadState) -> tuple[ThreadState, str]:
        return (
            ThreadState(
                thread_id=state.thread_id,
                summary=state.summary,
                messages=[*state.messages, ThreadMessage(role="user", content="locked write")],
            ),
            "done",
        )

    result = thread_store.update("default", add_message)
    state = thread_store.load("default")

    assert result == "done"
    assert state.messages == [ThreadMessage(role="user", content="locked write")]


def test_chat_agent_tool_invocation_with_search_memory(tmp_path: Path) -> None:
    repo = MemoryEntryRepository(tmp_path)
    repo.save(
        MemoryEntry(
            type="belief",
            title="Clarity matters",
            body="Prefer explicit assumptions.",
            tags=["style"],
        )
    )

    class ToolRequestLLM:
        def __init__(self) -> None:
            self.call_count = 0
            self.calls: list[list[ChatMessage]] = []

        def complete(self, messages: list[ChatMessage]) -> str:
            self.calls.append(messages)
            self.call_count += 1
            if self.call_count == 1:
                # First call: agent requests tool
                return '{"answer":"Let me search for that.","tool":"search_memory","tool_args":{"query":"clarity"}}'
            else:
                # Second call: agent generates final answer with tool results
                return '{"answer":"You value clarity and explicit assumptions.","evidence_references":["mem_123"]}'

    llm = ToolRequestLLM()
    agent = ChatAgent(tmp_path, llm=llm, memory_query_service=MemoryQueryService(repo))

    result = agent.respond("tell me about clarity")

    assert result.answer == "You value clarity and explicit assumptions."
    assert result.evidence_references == ("mem_123",)
    assert llm.call_count == 2
    # First call: initial prompt with tool documentation
    assert "Available tools:" in llm.calls[0][0].content
    assert "search_memory" in llm.calls[0][0].content
    # Second call: follow-up with tool result
    assert len(llm.calls[1]) > 0


def test_chat_agent_includes_tool_descriptions_in_system_prompt(tmp_path: Path) -> None:
    llm = FakeLLM()
    agent = ChatAgent(tmp_path, llm=llm)

    agent.respond("test")

    system_prompt = llm.calls[0][0].content
    assert "Available tools:" in system_prompt
    assert "search_memory" in system_prompt
    assert "Search durable memory" in system_prompt


def test_memory_search_tool_invocation_with_limit(tmp_path: Path) -> None:
    from nuself.agent.tools import MemorySearchTool

    repo = MemoryEntryRepository(tmp_path)
    for i in range(5):
        repo.save(
            MemoryEntry(
                type="belief",
                title=f"Belief {i}",
                body=f"Test belief {i}",
                tags=["test"],
            )
        )

    tool = MemorySearchTool(query_service=MemoryQueryService(repo))

    result = tool.invoke(query="belief", limit=2)

    assert "Belief" in result
    assert "matches found" not in result.lower() or result.count("belief") >= 2


def test_memory_search_tool_with_invalid_inputs(tmp_path: Path) -> None:
    from nuself.agent.tools import MemorySearchTool

    repo = MemoryEntryRepository(tmp_path)
    tool = MemorySearchTool(query_service=MemoryQueryService(repo))

    # Empty query
    result = tool.invoke(query="", limit=8)
    assert "Error" in result or "No matches" in result

    # Invalid limit
    result = tool.invoke(query="test", limit=0)
    assert "Error" in result

