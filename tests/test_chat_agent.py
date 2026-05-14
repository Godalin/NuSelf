from __future__ import annotations

import json
from pathlib import Path

import pytest

from nuself.agent.chat import (
    ChatAgent,
    ChatAgentSettings,
    ChatResult,
    ConversationGraphRuntime,
    ConversationTurnState,
    ConversationRuntimeResult,
    ParsedChatResponse,
    ThreadMessage,
    ThreadState,
    ThreadStore,
)
from nuself.agent.persona import PersonaContribution
from nuself.agent.graph_driver import ConversationGraphRuntimeError
from nuself.domain.memory import MemoryEntry
from nuself.domain.profile import ProfileItem
from nuself.llm import ChatMessage
from nuself.logs import read_log_events
from nuself.memory.query import MemoryQueryService
from nuself.memory.repository import MemoryEntryRepository
from nuself.memory.source_repository import SourceRepository
from nuself.profile.repository import ProfileItemRepository


class FakeLLM:
    def __init__(self, activation_response: dict[str, object] | None = None) -> None:
        self.calls: list[list[ChatMessage]] = []
        self._activation_response = activation_response or {
            "activated": False,
            "selected_persona_ids": [],
            "trigger": "test",
            "should_escalate": False,
            "escalation_reason": "",
        }

    def complete(self, messages: list[ChatMessage]) -> str:
        content = messages[0].content
        if "Persona Activation Gate" in content:
            return json.dumps(self._activation_response)
        if "private reflection council" in content:
            return "analyst_self gives a concrete LLM-backed perspective."
        if "You are the synthesizer. Distill" in content:
            return "LLM-backed synthesis of internal perspectives."
        self.calls.append(messages)
        if "Compress a private NuSelf conversation" in content:
            return "compressed context"
        return "agent reply"


class StructuredFakeLLM:
    def __init__(self, response: str, activation_response: dict[str, object] | None = None) -> None:
        self.response = response
        self.calls: list[list[ChatMessage]] = []
        self._activation_response = activation_response or {
            "activated": False,
            "selected_persona_ids": [],
            "trigger": "test",
            "should_escalate": False,
            "escalation_reason": "",
        }

    def complete(self, messages: list[ChatMessage]) -> str:
        content = messages[0].content
        if "Persona Activation Gate" in content:
            return json.dumps(self._activation_response)
        if "private reflection council" in content:
            return "analyst_self gives a concrete LLM-backed perspective."
        if "You are the synthesizer. Distill" in content:
            return "LLM-backed synthesis of internal perspectives."
        self.calls.append(messages)
        return self.response


class FailingLLM:
    def complete(self, messages: list[ChatMessage]) -> str:
        raise RuntimeError("llm unavailable")


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


def test_chat_agent_parses_markdown_structured_response(tmp_path: Path) -> None:
    llm = StructuredFakeLLM(
        "(synthesizer_self keeps context)\n\n"
        "**answer**: Use the profile context.\n\n"
        "**evidence_references**: [mem_123]\n"
        "**epistemic_status**: grounded\n"
    )
    agent = ChatAgent(tmp_path, llm=llm, memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)))

    result = agent.respond("profile context")

    assert result.answer == "(synthesizer_self keeps context)\n\nUse the profile context."
    assert result.evidence_references == ("mem_123",)
    assert result.epistemic_status == "grounded"
    assert "evidence_references" not in result.reply


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

    assert "LLM API key is not configured" not in text
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
                        "but real reasoning needs an API key. Last message: old question"
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


def test_chat_agent_writes_host_discussion_decision_log(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    llm = FakeLLM(activation_response={
        "activated": True,
        "selected_persona_ids": ["analyst_self"],
        "trigger": "debate request",
        "should_escalate": True,
        "escalation_reason": "user asked for debate",
    })
    agent = ChatAgent(tmp_path, llm=llm)

    agent.respond("compare the tradeoffs and debate the options")

    events = [event for event in read_log_events(project_root=tmp_path, component="persona") if event.event == "host_discussion_decision"]
    assert events
    assert events[-1].status == "approved"
    assert events[-1].metadata is not None
    assert events[-1].metadata.get("should_escalate") is True
    captured = capsys.readouterr().out
    assert "[host decision]" in captured


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


def test_chat_agent_delegates_turns_to_conversation_runtime(tmp_path: Path) -> None:
    class FakeRuntime:
        def __init__(self) -> None:
            self.seen: list[tuple[ThreadState, str, str]] = []

        def run_turn(self, state: ThreadState, message: str, thread_id: str) -> ConversationRuntimeResult:
            self.seen.append((state, message, thread_id))
            updated = ThreadState(
                thread_id=thread_id,
                summary=state.summary,
                messages=[
                    *state.messages,
                    ThreadMessage(role="user", content=message),
                    ThreadMessage(role="assistant", content="runtime reply"),
                ],
                next_message_index=state.next_message_index + 2,
            )
            return ConversationRuntimeResult(
                state=updated,
                result=ChatResult(
                    answer="runtime reply",
                    thread_id=thread_id,
                    evidence_references=("mem_runtime",),
                    confidence=0.7,
                    epistemic_status="grounded",
                ),
            )

    runtime = FakeRuntime()
    agent = ChatAgent(tmp_path, runtime=runtime)

    result = agent.respond("hello runtime", thread_id="graph")

    assert result.reply == "runtime reply"
    assert result.evidence_references == ("mem_runtime",)
    assert runtime.seen[0][1:] == ("hello runtime", "graph")
    state = ThreadStore(tmp_path).load("graph")
    assert state.messages == [
        ThreadMessage(role="user", content="hello runtime"),
        ThreadMessage(role="assistant", content="runtime reply"),
    ]


def test_conversation_runtime_nodes_pass_typed_turn_state(tmp_path: Path) -> None:
    llm = StructuredFakeLLM('{"answer":"Runtime node reply.","evidence_references":["mem_node"],"confidence":0.8}')
    runtime = ConversationGraphRuntime(
        tmp_path,
        llm=llm,
        memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)),
    )
    turn_state = ConversationTurnState.start(ThreadState.empty("default"), "node contracts", "default")

    prepared = runtime.prepare_context_node(turn_state)
    assert prepared.node == "prepare_context"
    assert prepared.state.active_messages == (ThreadMessage(role="user", content="node contracts"),)

    initial = runtime.initial_response_node(prepared.state)
    assert initial.node == "initial_response"
    assert initial.state.initial_response is not None
    assert initial.state.initial_response.answer == "Runtime node reply."

    detected = runtime.detect_tool_request_node(initial.state)
    assert detected.node == "detect_tool_request"
    assert detected.state.tool_call is None

    finalized = runtime.finalize_response_node(detected.state)
    assert finalized.node == "finalize_response"
    assert finalized.state.final_response is not None
    assert finalized.state.final_response.evidence_references == ("mem_node",)
    assert finalized.state.saved_messages[-1] == ThreadMessage(role="assistant", content="Runtime node reply.")

    updated = runtime.state_update_node(finalized.state)
    assert updated.node == "state_update"
    assert updated.state.updated_thread_state is not None
    assert updated.state.updated_thread_state.next_message_index == 2

    compressed = runtime.compression_node(updated.state)
    assert compressed.node == "compression"
    assert compressed.state.updated_thread_state == updated.state.updated_thread_state


def test_conversation_runtime_skips_persona_work_for_trivial_turn(tmp_path: Path) -> None:
    llm = StructuredFakeLLM('{"answer":"Trivial reply.","evidence_references":[],"confidence":0.4}')
    runtime = ConversationGraphRuntime(
        tmp_path,
        llm=llm,
        memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)),
    )

    result = runtime.run_turn(ThreadState.empty("trivial"), "hello", "trivial")

    assert result.result.answer == "Trivial reply."
    assert result.node_trace == (
        "prepare_context",
        "persona_activation",
        "initial_response",
        "detect_tool_request",
        "finalize_response",
        "state_update",
        "compression",
    )


def test_conversation_runtime_runs_llm_backed_personas_when_activated(tmp_path: Path) -> None:
    llm = StructuredFakeLLM(
        '{"answer":"Persona reply.","evidence_references":[],"confidence":0.4}',
        activation_response={
            "activated": True,
            "selected_persona_ids": ["analyst_self"],
            "trigger": "analytical question",
            "should_escalate": False,
            "escalation_reason": "",
        },
    )
    runtime = ConversationGraphRuntime(
        tmp_path,
        llm=llm,
        memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)),
    )

    turn_state = ConversationTurnState.start(ThreadState.empty("persona"), "Should I split this project?", "persona")
    prepared = runtime.prepare_context_node(turn_state)
    activated = runtime.persona_activation_node(prepared.state)

    assert activated.state.persona_activation is not None
    assert activated.state.persona_activation.activated is True
    assert activated.state.persona_turn_state is not None

    run_personas = runtime.run_personas_node(activated.state)
    assert run_personas.node == "run_personas"
    assert run_personas.state.persona_turn_state is not None
    assert run_personas.state.persona_turn_state.contributions == (
        PersonaContribution(
            persona_id="analyst_self",
            notes=("analyst_self gives a concrete LLM-backed perspective.",),
            confidence=0.5,
        ),
    )
    assert run_personas.state.persona_turn_state.synthesis is not None
    assert run_personas.state.persona_turn_state.node_trace == ("run_personas", "run_synthesizer")

    persona_events = [event for event in read_log_events(project_root=tmp_path, component="persona") if event.event == "persona_summary"]
    assert len(persona_events) >= 1
    assert "analyst_self gives a concrete LLM-backed perspective." in persona_events[-1].message
    assert " | " not in persona_events[-1].message
    assert persona_events[-1].metadata == {"persona_count": 1, "has_synthesis": True}

    graph_turn = runtime.run_turn(ThreadState.empty("persona-graph"), "Should I split this project?", "persona-graph")
    assert graph_turn.result.answer == "Persona reply."
    assert graph_turn.node_trace == (
        "prepare_context",
        "persona_activation",
        "run_personas",
        "initial_response",
        "detect_tool_request",
        "finalize_response",
        "state_update",
        "compression",
    )



def test_conversation_graph_runtime_executes_turn_through_graph_driver(tmp_path: Path) -> None:
    llm = StructuredFakeLLM(
        '{"answer":"Graph driver reply.","evidence_references":["mem_graph"],'
        '"confidence":0.9,"epistemic_status":"grounded"}'
    )
    runtime = ConversationGraphRuntime(
        tmp_path,
        llm=llm,
        memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)),
    )

    result = runtime.run_turn(ThreadState.empty("graph"), "graph runtime", "graph")

    assert result.result.answer == "Graph driver reply."
    assert result.result.evidence_references == ("mem_graph",)
    assert result.result.confidence == 0.9
    assert result.node_trace == (
        "prepare_context",
        "persona_activation",
        "initial_response",
        "detect_tool_request",
        "finalize_response",
        "state_update",
        "compression",
    )
    assert result.state.messages == [
        ThreadMessage(role="user", content="graph runtime"),
        ThreadMessage(role="assistant", content="Graph driver reply."),
    ]


def test_conversation_graph_runtime_routes_tool_calls_through_tool_node(tmp_path: Path) -> None:
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

        def complete(self, messages: list[ChatMessage]) -> str:
            content = messages[0].content
            if "Persona Activation Gate" in content:
                return '{"activated": false, "selected_persona_ids": [], "trigger": "test", "should_escalate": false, "escalation_reason": ""}'
            self.call_count += 1
            if self.call_count == 1:
                return '{"answer":"Searching memory.","tool":"search_memory","tool_args":{"query":"clarity"}}'
            return '{"answer":"You value clarity.","evidence_references":["mem_tool"],"epistemic_status":"grounded"}'

    llm = ToolRequestLLM()
    runtime = ConversationGraphRuntime(tmp_path, llm=llm, memory_query_service=MemoryQueryService(repo))

    result = runtime.run_turn(ThreadState.empty("tool"), "what about clarity?", "tool")

    assert result.result.answer == "You value clarity."
    assert result.result.evidence_references == ("mem_tool",)
    assert result.node_trace == (
        "prepare_context",
        "persona_activation",
        "initial_response",
        "detect_tool_request",
        "execute_tool",
        "finalize_response",
        "state_update",
        "compression",
    )
    assert result.state.messages[1].content.startswith("[Tool call: search_memory]")
    assert llm.call_count == 2


def test_conversation_graph_runtime_keeps_unsupported_tools_on_no_tool_route(tmp_path: Path) -> None:
    llm = StructuredFakeLLM(
        '{"answer":"I cannot run that tool.","tool":"unknown_tool","tool_args":{"query":"clarity"},'
        '"epistemic_status":"uncertain"}'
    )
    runtime = ConversationGraphRuntime(
        tmp_path,
        llm=llm,
        memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)),
    )

    result = runtime.run_turn(ThreadState.empty("unsupported"), "try an unknown tool", "unsupported")

    assert result.result.answer == "I cannot run that tool."
    assert result.node_trace == (
        "prepare_context",
        "persona_activation",
        "initial_response",
        "detect_tool_request",
        "finalize_response",
        "state_update",
        "compression",
    )
    assert len(llm.calls) == 1
    detected = runtime.detect_tool_request_node(
        ConversationTurnState(
            thread_id="unsupported",
            persisted_state=ThreadState.empty("unsupported"),
            user_message="try an unknown tool",
            initial_response=ParsedChatResponse(
                answer="I cannot run that tool.",
                tool="unknown_tool",
                tool_args={"query": "clarity"},
            ),
        )
    )
    assert detected.state.tool_call is not None
    assert detected.state.tool_call.name == "unknown_tool"
    assert detected.state.tool_call.args == {"query": "clarity"}
    assert detected.state.tool_call.supported is False
    assert detected.state.tool_call.diagnostic == "unsupported tool request: unknown_tool"


def test_chat_agent_preserves_thread_state_when_graph_driver_fails(tmp_path: Path) -> None:
    thread_store = ThreadStore(tmp_path)
    thread_store.save(
        ThreadState(
            thread_id="default",
            messages=[ThreadMessage(role="user", content="existing message")],
            next_message_index=1,
        )
    )
    agent = ChatAgent(
        tmp_path,
        llm=FailingLLM(),
        thread_store=thread_store,
        memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)),
    )

    with pytest.raises(ConversationGraphRuntimeError, match="conversation graph node 'initial_response' failed") as exc_info:
        agent.respond("new message")

    assert exc_info.value.node == "initial_response"
    assert exc_info.value.node_trace == ("prepare_context", "persona_activation", "initial_response")
    state = thread_store.load("default")
    assert state.messages == [ThreadMessage(role="user", content="existing message")]
    assert state.next_message_index == 1


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
            content = messages[0].content
            if "Persona Activation Gate" in content:
                return '{"activated": false, "selected_persona_ids": [], "trigger": "test", "should_escalate": false, "escalation_reason": ""}'
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


def test_chat_agent_injects_language_instruction(tmp_path: Path) -> None:
    private_dir = tmp_path / "private"
    private_dir.mkdir(parents=True)
    (private_dir / "config.yaml").write_text(
        "chat:\n  language_preference: zh-CN\n",
        encoding="utf-8",
    )
    llm = FakeLLM()
    agent = ChatAgent(tmp_path, llm=llm)

    agent.respond("hello")

    system_prompt = llm.calls[0][0].content
    assert "Respond to the user in zh-CN" in system_prompt


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


def test_memory_search_tool_accepts_type_and_tag_filters(tmp_path: Path) -> None:
    from nuself.agent.tools import MemorySearchTool

    repo = MemoryEntryRepository(tmp_path)
    repo.save(
        MemoryEntry(
            type="belief",
            title="Direct style",
            body="Prefer direct answers.",
            tags=["style"],
        )
    )
    repo.save(
        MemoryEntry(
            type="goal",
            title="Runtime migration",
            body="Prepare graph migration.",
            tags=["runtime"],
        )
    )
    tool = MemorySearchTool(query_service=MemoryQueryService(repo))

    result = tool.invoke(query="current goal", types=["goal"], tags=["runtime"])

    assert "Runtime migration" in result
    assert "Direct style" not in result


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


# --- Reflection consumption tools ---

def test_list_pending_reflections_empty(tmp_path: Path) -> None:
    from nuself.agent.tools import ListPendingReflectionsTool
    from nuself.reflection.repository import ReflectionRepository

    repo = ReflectionRepository(tmp_path)
    tool = ListPendingReflectionsTool(repository=repo)
    result = tool.invoke()
    assert "No pending reflection ideas" in result


def test_list_pending_reflections_with_entries(tmp_path: Path) -> None:
    from nuself.agent.tools import ListPendingReflectionsTool
    from nuself.reflection.repository import ReflectionEntry, ReflectionRepository

    repo = ReflectionRepository(tmp_path)
    repo.add(
        ReflectionEntry(
            id="r1",
            title="Explore recursion in habits",
            body="Your memory suggests...",
            candidate_type="connection",
            confidence=0.8,
            novelty=0.9,
            urgency=0.3,
            interruption_cost=0.1,
            composite_score=0.7,
            status="pending",
            discussion_approved=None,
            discussion_trace=(),
            deep_link="nuself://thread/reflections",
            created_at="2024-01-01T00:00:00+00:00",
            reviewed_at=None,
        )
    )
    repo.add(
        ReflectionEntry(
            id="r2",
            title="Sleep and creativity link",
            body="Underdeveloped...",
            candidate_type="question",
            confidence=0.7,
            novelty=0.8,
            urgency=0.3,
            interruption_cost=0.1,
            composite_score=0.6,
            status="pending",
            discussion_approved=None,
            discussion_trace=(),
            deep_link="nuself://thread/reflections",
            created_at="2024-01-01T00:00:00+00:00",
            reviewed_at=None,
        )
    )
    tool = ListPendingReflectionsTool(repository=repo)
    result = tool.invoke()
    assert "Pending reflection ideas:" in result
    assert "[1] Explore recursion in habits" in result
    assert "[2] Sleep and creativity link" in result


def test_list_pending_reflections_respects_limit(tmp_path: Path) -> None:
    from nuself.agent.tools import ListPendingReflectionsTool
    from nuself.reflection.repository import ReflectionEntry, ReflectionRepository

    repo = ReflectionRepository(tmp_path)
    for i in range(5):
        repo.add(
            ReflectionEntry(
                id=f"r{i}",
                title=f"Idea {i}",
                body="...",
                candidate_type="question",
                confidence=0.8,
                novelty=0.9,
                urgency=0.3,
                interruption_cost=0.1,
                composite_score=0.7,
                status="pending",
                discussion_approved=None,
                discussion_trace=(),
                deep_link="nuself://thread/reflections",
                created_at="2024-01-01T00:00:00+00:00",
                reviewed_at=None,
            )
        )
    tool = ListPendingReflectionsTool(repository=repo)
    result = tool.invoke(limit=2)
    assert result.count("[") == 2  # only two numbered items


def test_dismiss_reflection_success(tmp_path: Path) -> None:
    from nuself.agent.tools import DismissReflectionTool
    from nuself.reflection.repository import ReflectionEntry, ReflectionRepository

    repo = ReflectionRepository(tmp_path)
    repo.add(
        ReflectionEntry(
            id="r1",
            title="Explore recursion in habits",
            body="...",
            candidate_type="connection",
            confidence=0.8,
            novelty=0.9,
            urgency=0.3,
            interruption_cost=0.1,
            composite_score=0.7,
            status="pending",
            discussion_approved=None,
            discussion_trace=(),
            deep_link="nuself://thread/reflections",
            created_at="2024-01-01T00:00:00+00:00",
            reviewed_at=None,
        )
    )
    tool = DismissReflectionTool(repository=repo)
    result = tool.invoke(index=1)
    assert "Dismissed" in result
    assert "Explore recursion in habits" in result
    assert repo.list(status="pending") == []


def test_dismiss_reflection_out_of_range(tmp_path: Path) -> None:
    from nuself.agent.tools import DismissReflectionTool
    from nuself.reflection.repository import ReflectionRepository

    repo = ReflectionRepository(tmp_path)
    tool = DismissReflectionTool(repository=repo)
    result = tool.invoke(index=1)
    assert "out of range" in result


def test_dismiss_reflection_invalid_index(tmp_path: Path) -> None:
    from nuself.agent.tools import DismissReflectionTool
    from nuself.reflection.repository import ReflectionRepository

    repo = ReflectionRepository(tmp_path)
    tool = DismissReflectionTool(repository=repo)
    assert "Error" in tool.invoke(index=0)
    assert "Error" in tool.invoke(index=-1)


def test_archive_reflection_success(tmp_path: Path) -> None:
    from nuself.agent.tools import ArchiveReflectionTool
    from nuself.reflection.repository import ReflectionEntry, ReflectionRepository

    repo = ReflectionRepository(tmp_path)
    repo.add(
        ReflectionEntry(
            id="r1",
            title="Explore recursion in habits",
            body="...",
            candidate_type="connection",
            confidence=0.8,
            novelty=0.9,
            urgency=0.3,
            interruption_cost=0.1,
            composite_score=0.7,
            status="pending",
            discussion_approved=None,
            discussion_trace=(),
            deep_link="nuself://thread/reflections",
            created_at="2024-01-01T00:00:00+00:00",
            reviewed_at=None,
        )
    )
    tool = ArchiveReflectionTool(repository=repo)
    result = tool.invoke(index=1)
    assert "Archived" in result
    assert "Explore recursion in habits" in result
    assert repo.list(status="pending") == []
    archived = repo.list(status="archived")
    assert len(archived) == 1


def test_archive_reflection_out_of_range(tmp_path: Path) -> None:
    from nuself.agent.tools import ArchiveReflectionTool
    from nuself.reflection.repository import ReflectionRepository

    repo = ReflectionRepository(tmp_path)
    tool = ArchiveReflectionTool(repository=repo)
    result = tool.invoke(index=1)
    assert "out of range" in result


def test_archive_reflection_invalid_index(tmp_path: Path) -> None:
    from nuself.agent.tools import ArchiveReflectionTool
    from nuself.reflection.repository import ReflectionRepository

    repo = ReflectionRepository(tmp_path)
    tool = ArchiveReflectionTool(repository=repo)
    assert "Error" in tool.invoke(index=0)
    assert "Error" in tool.invoke(index=-1)


def test_chat_agent_includes_reflection_tools_in_system_prompt(tmp_path: Path) -> None:
    from nuself.agent.chat import ChatAgent

    llm = FakeLLM()
    agent = ChatAgent(tmp_path, llm=llm)
    agent.respond("test")

    system_prompt = llm.calls[0][0].content
    assert "list_pending_reflections" in system_prompt
    assert "archive_reflection" in system_prompt
    assert "dismiss_reflection" in system_prompt


# --- Memory management tools ---

def test_archive_memory_tool_success(tmp_path: Path) -> None:
    from nuself.agent.tools import ArchiveMemoryTool
    from nuself.memory.repository import MemoryEntryRepository
    from nuself.domain.memory import MemoryEntry

    repo = MemoryEntryRepository(tmp_path)
    repo.save(MemoryEntry(id="m1", type="belief", title="Old belief", body="..."))
    tool = ArchiveMemoryTool(project_root=tmp_path)
    result = tool.invoke(entry_id="m1")
    assert "Archived" in result
    assert "Old belief" in result
    entry = repo.get("m1")
    assert entry.review_state == "archived"


def test_archive_memory_tool_not_found(tmp_path: Path) -> None:
    from nuself.agent.tools import ArchiveMemoryTool

    tool = ArchiveMemoryTool(project_root=tmp_path)
    result = tool.invoke(entry_id="nonexistent")
    assert "Error" in result


def test_update_memory_importance_tool_success(tmp_path: Path) -> None:
    from nuself.agent.tools import UpdateMemoryImportanceTool
    from nuself.memory.repository import MemoryEntryRepository
    from nuself.domain.memory import MemoryEntry

    repo = MemoryEntryRepository(tmp_path)
    repo.save(MemoryEntry(id="m1", type="belief", title="Key belief", body="...", importance=0.3))
    tool = UpdateMemoryImportanceTool(project_root=tmp_path)
    result = tool.invoke(entry_id="m1", importance=0.9)
    assert "Updated importance" in result
    assert "0.90" in result
    entry = repo.get("m1")
    assert entry.importance == 0.9


def test_update_memory_importance_tool_out_of_range(tmp_path: Path) -> None:
    from nuself.agent.tools import UpdateMemoryImportanceTool

    tool = UpdateMemoryImportanceTool(project_root=tmp_path)
    assert "Error" in tool.invoke(entry_id="m1", importance=1.5)
    assert "Error" in tool.invoke(entry_id="m1", importance=-0.1)


def test_update_memory_importance_tool_not_found(tmp_path: Path) -> None:
    from nuself.agent.tools import UpdateMemoryImportanceTool

    tool = UpdateMemoryImportanceTool(project_root=tmp_path)
    result = tool.invoke(entry_id="nonexistent", importance=0.5)
    assert "Error" in result


def test_chat_agent_includes_memory_tools_in_system_prompt(tmp_path: Path) -> None:
    from nuself.agent.chat import ChatAgent

    llm = FakeLLM()
    agent = ChatAgent(tmp_path, llm=llm)
    agent.respond("test")

    system_prompt = llm.calls[0][0].content
    assert "archive_memory" in system_prompt
    assert "update_memory_importance" in system_prompt


def test_chat_agent_end_to_end_archive_memory_via_tool(tmp_path: Path) -> None:
    """Full path: chat → tool request → archive_memory → verify entry archived."""
    from nuself.memory.repository import MemoryEntryRepository
    from nuself.domain.memory import MemoryEntry

    repo = MemoryEntryRepository(tmp_path)
    repo.save(MemoryEntry(type="belief", id="m1", title="Old belief", body="..."))

    class ArchiveToolLLM:
        def __init__(self) -> None:
            self.call_count = 0

        def complete(self, messages: list[ChatMessage]) -> str:
            content = messages[0].content
            if "Persona Activation Gate" in content:
                return '{"activated": false, "selected_persona_ids": [], "trigger": "test", "should_escalate": false, "escalation_reason": ""}'
            self.call_count += 1
            if self.call_count == 1:
                return '{"answer":"Let me archive that for you.","tool":"archive_memory","tool_args":{"entry_id":"m1"}}'
            return '{"answer":"Done. The entry has been archived.","evidence_references":[]}'

    llm = ArchiveToolLLM()
    agent = ChatAgent(tmp_path, llm=llm, memory_query_service=MemoryQueryService(repo))

    result = agent.respond("archive that old belief")

    assert "archived" in result.answer.lower() or "Done" in result.answer
    assert llm.call_count == 2
    entry = repo.get("m1")
    assert entry.review_state == "archived"
