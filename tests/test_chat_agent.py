from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from langchain_core.tools import BaseTool

from nuself.agent.chat import (
    ChatAgent,
    ChatAgentSettings,
    ChatStructuredOutput,
    ConversationGraphRuntime,
    ConversationTurnState,
    ThreadMessage,
    ThreadState,
    ThreadStore,
)
from nuself.agent.chat import ConversationGraphRuntimeError
from nuself.domain.memory import MemoryEntry
from nuself.domain.profile import ProfileItem
from nuself.llm import ChatMessage
from nuself.logs import read_log_events, runtime_event_log_sink
from nuself.memory.query import MemoryQueryService
from nuself.memory.repository import MemoryEntryRepository
from nuself.memory.source_repository import SourceRepository
from nuself.profile.repository import ProfileItemRepository
from nuself.runtime.events import EventPublisher
from nuself.runtime.messages import RuntimeEnvelope
from nuself.trace.repository import TraceRepository
from nuself.trace.service import TraceRecorder


def _chat_tool(
    tmp_path: Path,
    name: str,
    *,
    query_service: MemoryQueryService | None = None,
    reflection_repository: object | None = None,
) -> BaseTool:
    from nuself.agent.tools import build_langchain_chat_tools
    from nuself.reflection.repository import ReflectionRepository

    repo = reflection_repository if reflection_repository is not None else ReflectionRepository(tmp_path)
    if not isinstance(repo, ReflectionRepository):
        raise TypeError("reflection_repository must be a ReflectionRepository")
    tools = build_langchain_chat_tools(
        query_service=query_service or MemoryQueryService(MemoryEntryRepository(tmp_path)),
        reflection_repository=repo,
        project_root=tmp_path,
    )
    return {tool.name: tool for tool in tools}[name]


def _invoke_chat_tool(tool: BaseTool, args: dict[str, object] | None = None) -> str:
    invoke = cast(Callable[[dict[str, object]], object], getattr(tool, "invoke"))
    return str(invoke(args or {}))


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


class SequencedStructuredFakeLLM(StructuredFakeLLM):
    def __init__(self, responses: list[str], activation_response: dict[str, object] | None = None) -> None:
        super().__init__(responses[-1] if responses else "", activation_response=activation_response)
        self._responses = list(responses)

    def complete(self, messages: list[ChatMessage]) -> str:
        content = messages[0].content
        if "Persona Activation Gate" in content:
            return json.dumps(self._activation_response)
        if "private reflection council" in content:
            return "analyst_self gives a concrete LLM-backed perspective."
        if "You are the synthesizer. Distill" in content:
            return "LLM-backed synthesis of internal perspectives."
        self.calls.append(messages)
        if self._responses:
            return self._responses.pop(0)
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

    prompt_text = "\n".join(message.content for message in llm.calls[0][1:])
    saved_text = (tmp_path / "private" / "threads" / "default.json").read_text(encoding="utf-8")
    assert "LLM API is not configured yet" not in prompt_text
    assert "LLM API is not configured yet" not in saved_text
    assert "old question" in prompt_text


def test_selves_consult_writes_host_discussion_decision_log(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    llm = FakeLLM(activation_response={
        "activated": True,
        "selected_persona_ids": ["analyst_self"],
        "trigger": "debate request",
        "should_escalate": True,
        "escalation_reason": "user asked for debate",
    })
    runtime = ConversationGraphRuntime(
        tmp_path,
        llm=llm,
        memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)),
    )

    runtime._consult_selves_tool("compare the tradeoffs and debate the options", mode="discussion")  # type: ignore[reportPrivateUsage]

    events = [event for event in read_log_events(project_root=tmp_path, component="persona") if event.event == "host_discussion_decision"]
    assert events
    assert events[-1].status == "approved"
    assert events[-1].metadata is not None
    assert events[-1].metadata.get("should_escalate") is True
    step_events = [event for event in read_log_events(project_root=tmp_path, component="persona") if event.event == "persona_discussion_step"]
    assert step_events
    assert step_events[0].metadata is not None
    assert "discussion_trace" in step_events[0].metadata
    outcome_events = [event for event in read_log_events(project_root=tmp_path, component="persona") if event.event == "persona_discussion"]
    assert outcome_events
    assert outcome_events[-1].metadata is not None
    assert "discussion_steps" in outcome_events[-1].metadata
    assert "discussion_trace" not in outcome_events[-1].metadata
    captured = capsys.readouterr().out
    assert "[host decision]" not in captured
    assert "Persona Trigger" not in captured


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


def test_conversation_runtime_nodes_pass_typed_turn_state(tmp_path: Path) -> None:
    llm = StructuredFakeLLM('{"answer":"Runtime node reply.","evidence_references":["mem_node"],"confidence":0.8}')
    runtime = ConversationGraphRuntime(
        tmp_path,
        llm=llm,
        memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)),
    )
    turn_state = ConversationTurnState.start(ThreadState.empty("default"), "node contracts", "default")

    prepared = runtime.prepare_context_node(turn_state)
    assert prepared.state.active_messages == (ThreadMessage(role="user", content="node contracts"),)

    responded = runtime.respond_node(prepared.state)
    assert responded.state.final_response is not None
    assert responded.state.final_response.answer == "Runtime node reply."
    assert responded.state.final_response.evidence_references == ["mem_node"]
    assert responded.state.saved_messages[-1] == ThreadMessage(role="assistant", content="Runtime node reply.")

    updated = runtime.state_update_node(responded.state)
    assert updated.state.updated_thread_state is not None
    assert updated.state.updated_thread_state.next_message_index == 2

    compressed = runtime.compression_node(updated.state)
    assert compressed.state.updated_thread_state == updated.state.updated_thread_state


def test_conversation_runtime_skips_persona_work_for_trivial_turn(tmp_path: Path) -> None:
    llm = StructuredFakeLLM('{"answer":"Trivial reply.","evidence_references":[],"confidence":0.4}')
    runtime = ConversationGraphRuntime(
        tmp_path,
        llm=llm,
        memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)),
    )

    _, result, node_trace = runtime.run_turn(ThreadState.empty("trivial"), "hello", "trivial")

    assert result.answer == "Trivial reply."
    assert node_trace == (
        "prepare_context",
        "respond",
        "state_update",
        "compression",
    )
    assert TraceRepository(tmp_path).list_traces(kind="chat_turn") == []


def test_conversation_runtime_runs_llm_backed_personas_through_selves_subagent(tmp_path: Path) -> None:
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

    result = runtime._consult_selves_tool("Should I split this project?")  # type: ignore[reportPrivateUsage]
    assert "analyst_self gives a concrete LLM-backed perspective." in result
    assert "LLM-backed synthesis of internal perspectives." in result

    persona_events = [event for event in read_log_events(project_root=tmp_path, component="persona") if event.event == "persona_summary"]
    assert len(persona_events) >= 1
    assert "analyst_self gives a concrete LLM-backed perspective." in persona_events[-1].message
    assert " | " not in persona_events[-1].message
    assert persona_events[-1].metadata == {"persona_count": 1, "has_synthesis": True}

    _, graph_result, graph_node_trace = runtime.run_turn(ThreadState.empty("persona-graph"), "Should I split this project?", "persona-graph")
    assert graph_result.answer == "Persona reply."
    assert graph_node_trace == (
        "prepare_context",
        "respond",
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

    state, chat_result, node_trace = runtime.run_turn(ThreadState.empty("graph"), "graph runtime", "graph")

    assert chat_result.answer == "Graph driver reply."
    assert chat_result.evidence_references == ("mem_graph",)
    assert chat_result.confidence == 0.9
    assert node_trace == (
        "prepare_context",
        "respond",
        "state_update",
        "compression",
    )
    assert state.messages == [
        ThreadMessage(role="user", content="graph runtime"),
        ThreadMessage(role="assistant", content="Graph driver reply."),
    ]
    traces = TraceRepository(tmp_path).list_traces(kind="chat_turn")
    assert len(traces) == 1
    trace = traces[0]
    assert trace.thread_id == "graph"
    assert trace.evidence_refs == ("mem_graph",)
    assert trace.inputs == ("graph runtime",)
    assert trace.outputs == ("Graph driver reply.",)
    assert trace.participants == ("chat_agent",)
    assert trace.metadata["node_trace"] == tuple(node_trace)








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

    with pytest.raises(ConversationGraphRuntimeError, match="conversation graph node 'respond' failed") as exc_info:
        agent.respond("new message")

    assert exc_info.value.node == "respond"
    assert exc_info.value.node_trace == ("prepare_context", "respond")
    state = thread_store.load("default")
    assert state.messages == [ThreadMessage(role="user", content="existing message")]
    assert state.next_message_index == 1
    lifecycle = [
        event
        for event in read_log_events(
            project_root=tmp_path,
            component="chat",
        )
        if event.event.startswith("turn.")
    ]
    assert [event.event for event in lifecycle] == [
        "turn.started",
        "turn.failed",
    ]
    assert lifecycle[-1].error is not None
    assert "conversation graph node 'respond' failed" in lifecycle[-1].error
    assert lifecycle[-1].thread_id == "default"
    assert lifecycle[-1].source == "chat_runtime"


def test_chat_completed_event_is_published_after_thread_persistence(
    tmp_path: Path,
) -> None:
    thread_store = ThreadStore(tmp_path)
    publisher = EventPublisher()
    publisher.subscribe(runtime_event_log_sink(tmp_path))
    observed: list[RuntimeEnvelope] = []

    def inspect_persisted_state(event: RuntimeEnvelope) -> None:
        if event.name == "turn.completed":
            state = thread_store.load("thread-a")
            assert state.messages[-1] == ThreadMessage(
                role="assistant",
                content="agent reply",
                turn_id="turn-1",
            )
        observed.append(event)

    publisher.subscribe(inspect_persisted_state)
    agent = ChatAgent(
        tmp_path,
        llm=FakeLLM(),
        thread_store=thread_store,
        event_publisher=publisher,
    )

    result = agent.respond(
        "persist this",
        thread_id="thread-a",
        turn_id="turn-1",
    )

    assert result.reply == "agent reply"
    assert [event.name for event in observed] == [
        "turn.started",
        "turn.completed",
    ]
    audit = [
        event
        for event in read_log_events(
            project_root=tmp_path,
            component="chat",
        )
        if event.event.startswith("turn.")
    ]
    assert [event.event_id for event in audit] == [
        event.message_id for event in observed
    ]
    assert all(event.thread_id == "thread-a" for event in audit)
    assert all(event.turn_id == "turn-1" for event in audit)


def test_chat_persistence_failure_publishes_failed_not_completed(
    tmp_path: Path,
) -> None:
    class FailingSaveThreadStore(ThreadStore):
        def _save_unlocked(self, state: ThreadState) -> None:
            del state
            raise OSError("thread storage unavailable")

    agent = ChatAgent(
        tmp_path,
        llm=FakeLLM(),
        thread_store=FailingSaveThreadStore(tmp_path),
    )

    with pytest.raises(OSError, match="thread storage unavailable"):
        agent.respond("cannot persist", turn_id="turn-1")

    lifecycle = [
        event
        for event in read_log_events(
            project_root=tmp_path,
            component="chat",
        )
        if event.event.startswith("turn.")
    ]
    assert [event.event for event in lifecycle] == [
        "turn.started",
        "turn.failed",
    ]
    assert lifecycle[-1].error == "thread storage unavailable"


def test_chat_reused_event_does_not_rerun_graph(
    tmp_path: Path,
) -> None:
    llm = FakeLLM()
    publisher = EventPublisher()
    observed: list[RuntimeEnvelope] = []
    publisher.subscribe(observed.append)
    agent = ChatAgent(
        tmp_path,
        llm=llm,
        event_publisher=publisher,
    )
    agent.respond("same turn", turn_id="turn-1")
    observed.clear()

    result = agent.respond("same turn", turn_id="turn-1")

    assert result.reply == "agent reply"
    assert len(llm.calls) == 1
    assert [event.name for event in observed] == ["turn.reused"]


def test_chat_event_subscriber_failure_does_not_replace_original_failure(
    tmp_path: Path,
) -> None:
    publisher = EventPublisher()
    publisher.subscribe(runtime_event_log_sink(tmp_path))

    def fail_subscriber(_event: RuntimeEnvelope) -> None:
        raise RuntimeError("subscriber unavailable")

    publisher.subscribe(fail_subscriber)
    agent = ChatAgent(
        tmp_path,
        llm=FailingLLM(),
        event_publisher=publisher,
    )

    with pytest.raises(
        ConversationGraphRuntimeError,
        match="conversation graph node 'respond' failed",
    ):
        agent.respond("fail without masking")

    lifecycle = [
        event.event
        for event in read_log_events(
            project_root=tmp_path,
            component="chat",
        )
        if event.event.startswith("turn.")
    ]
    assert lifecycle == ["turn.started", "turn.failed"]


def test_chat_event_subscriber_failure_does_not_replace_completed_turn(
    tmp_path: Path,
) -> None:
    publisher = EventPublisher()
    publisher.subscribe(runtime_event_log_sink(tmp_path))

    def fail_subscriber(_event: RuntimeEnvelope) -> None:
        raise RuntimeError("subscriber unavailable")

    publisher.subscribe(fail_subscriber)
    agent = ChatAgent(
        tmp_path,
        llm=FakeLLM(),
        event_publisher=publisher,
    )

    result = agent.respond("complete despite subscriber")

    assert result.reply == "agent reply"
    assert ThreadStore(tmp_path).load("default").messages[-1].content == (
        "agent reply"
    )
    lifecycle = [
        event.event
        for event in read_log_events(
            project_root=tmp_path,
            component="chat",
        )
        if event.event.startswith("turn.")
    ]
    assert lifecycle == ["turn.started", "turn.completed"]


def test_chat_agent_includes_tool_descriptions_in_system_prompt(tmp_path: Path) -> None:
    llm = FakeLLM()
    agent = ChatAgent(tmp_path, llm=llm)

    agent.respond("test")

    system_prompt = llm.calls[0][0].content
    assert "Available tools:" in system_prompt
    assert "memory_search" in system_prompt
    assert "Search durable memory" in system_prompt


def test_chat_agent_includes_service_skills_in_system_prompt(tmp_path: Path) -> None:
    llm = FakeLLM()
    agent = ChatAgent(tmp_path, llm=llm)

    agent.respond("do you remember my earlier preferences?")

    system_prompt = llm.calls[0][0].content
    assert "load_skill" in system_prompt
    assert "memory" in system_prompt
    assert "reflection" in system_prompt


def test_conversation_runtime_registers_langchain_tools(tmp_path: Path) -> None:
    from langchain_core.tools import BaseTool

    runtime = ConversationGraphRuntime(
        tmp_path,
        llm=FakeLLM(),
        memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)),
    )
    tools = getattr(runtime, "_tools")

    assert "memory_search" in tools
    assert all(isinstance(tool, BaseTool) for tool in tools.values())


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

    tool = _chat_tool(tmp_path, "memory_search", query_service=MemoryQueryService(repo))

    result = _invoke_chat_tool(tool, {"query": "belief", "limit": 2})

    assert "Belief" in result
    assert "matches found" not in result.lower() or result.count("belief") >= 2


def test_memory_search_tool_accepts_type_and_tag_filters(tmp_path: Path) -> None:
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
    tool = _chat_tool(tmp_path, "memory_search", query_service=MemoryQueryService(repo))

    result = _invoke_chat_tool(tool, {"query": "current goal", "types": ["goal"], "tags": ["runtime"]})

    assert "Runtime migration" in result
    assert "Direct style" not in result


def test_memory_search_tool_with_invalid_inputs(tmp_path: Path) -> None:
    repo = MemoryEntryRepository(tmp_path)
    tool = _chat_tool(tmp_path, "memory_search", query_service=MemoryQueryService(repo))

    # Empty query
    result = _invoke_chat_tool(tool, {"query": "", "limit": 8})
    assert "Error" in result or "No matches" in result

    # Invalid limit
    result = _invoke_chat_tool(tool, {"query": "test", "limit": 0})
    assert "Error" in result


# --- Reflection consumption tools ---

def test_reflection_list_pending_empty(tmp_path: Path) -> None:
    from nuself.reflection.repository import ReflectionRepository

    repo = ReflectionRepository(tmp_path)
    tool = _chat_tool(tmp_path, "reflection_list_pending", reflection_repository=repo)
    result = _invoke_chat_tool(tool)
    assert "No pending reflection ideas" in result


def test_reflection_list_pending_with_entries(tmp_path: Path) -> None:
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
    tool = _chat_tool(tmp_path, "reflection_list_pending", reflection_repository=repo)
    result = _invoke_chat_tool(tool)
    assert "Pending reflection ideas:" in result
    assert "[0] Explore recursion in habits" in result
    assert "[1] Sleep and creativity link" in result


def test_reflection_list_pending_respects_limit(tmp_path: Path) -> None:
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
    tool = _chat_tool(tmp_path, "reflection_list_pending", reflection_repository=repo)
    result = _invoke_chat_tool(tool, {"limit": 2})
    assert result.count("[") == 2  # only two numbered items


def test_reflection_count_tool(tmp_path: Path) -> None:
    from nuself.reflection.repository import ReflectionEntry, ReflectionRepository

    repo = ReflectionRepository(tmp_path)
    repo.add(
        ReflectionEntry(
            id="r1",
            title="Count this reflection",
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
    tool = _chat_tool(tmp_path, "reflection_count", reflection_repository=repo)

    result = _invoke_chat_tool(tool)

    assert "Pending reflection ideas: 1 total" in result


def test_reflection_dismiss_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    tool = _chat_tool(tmp_path, "reflection_dismiss", reflection_repository=repo)
    result = _invoke_chat_tool(tool, {"index": 0})
    assert "Dismissed" in result
    assert "Explore recursion in habits" in result
    assert repo.list(status="pending") == []


def test_reflection_dismiss_out_of_range(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nuself.reflection.repository import ReflectionRepository

    repo = ReflectionRepository(tmp_path)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    tool = _chat_tool(tmp_path, "reflection_dismiss", reflection_repository=repo)
    result = _invoke_chat_tool(tool, {"index": 0})
    assert "Invalid reflection index" in result


def test_reflection_dismiss_invalid_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nuself.reflection.repository import ReflectionRepository

    repo = ReflectionRepository(tmp_path)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    tool = _chat_tool(tmp_path, "reflection_dismiss", reflection_repository=repo)
    assert "Error" in _invoke_chat_tool(tool, {"index": -1})


def test_reflection_archive_success(tmp_path: Path) -> None:
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
    tool = _chat_tool(tmp_path, "reflection_archive", reflection_repository=repo)
    result = _invoke_chat_tool(tool, {"index": 0})
    assert "Archived" in result
    assert "Explore recursion in habits" in result
    assert repo.list(status="pending") == []
    archived = repo.list(status="archived")
    assert len(archived) == 1


def test_reflection_archive_out_of_range(tmp_path: Path) -> None:
    from nuself.reflection.repository import ReflectionRepository

    repo = ReflectionRepository(tmp_path)
    tool = _chat_tool(tmp_path, "reflection_archive", reflection_repository=repo)
    result = _invoke_chat_tool(tool, {"index": 0})
    assert "Invalid reflection index" in result


def test_reflection_archive_invalid_index(tmp_path: Path) -> None:
    from nuself.reflection.repository import ReflectionRepository

    repo = ReflectionRepository(tmp_path)
    tool = _chat_tool(tmp_path, "reflection_archive", reflection_repository=repo)
    assert "Error" in _invoke_chat_tool(tool, {"index": -1})


def test_chat_agent_includes_reflection_tools_in_system_prompt(tmp_path: Path) -> None:
    from nuself.agent.chat import ChatAgent

    llm = FakeLLM()
    agent = ChatAgent(tmp_path, llm=llm)
    agent.respond("test")

    system_prompt = llm.calls[0][0].content
    assert "reflection_list_pending" in system_prompt
    assert "reflection_count" in system_prompt
    assert "reflection_archive" in system_prompt
    assert "reflection_dismiss" in system_prompt


def test_chat_agent_includes_reason_and_trace_tools_and_skills(tmp_path: Path) -> None:
    llm = FakeLLM()
    agent = ChatAgent(tmp_path, llm=llm)

    agent.respond("what are you still thinking about?")

    system_prompt = llm.calls[0][0].content
    assert "reason_list_active" in system_prompt
    assert "reason_count" in system_prompt
    assert "reason_context" in system_prompt
    assert "reason_step" in system_prompt
    assert "reason_show" in system_prompt
    assert "trace_search" in system_prompt
    assert "trace_count" in system_prompt
    assert "trace_show" in system_prompt
    assert "load_skill" in system_prompt


def test_load_reason_skills_have_separate_read_and_proposal_tools(tmp_path: Path) -> None:
    runtime = ConversationGraphRuntime(
        tmp_path,
        llm=FakeLLM(),
        memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)),
    )
    tools = cast(dict[str, BaseTool], getattr(runtime, "_tools"))

    reason = _invoke_chat_tool(tools["load_skill"], {"skill_name": "reason"})
    proposal = _invoke_chat_tool(tools["load_skill"], {"skill_name": "reason_proposal"})

    assert "Allowed tools: reason_list_active, reason_count, reason_context, reason_step, reason_show" in reason
    assert "Reason read tools omit tool logs" in reason
    assert "reason_propose" not in reason
    assert "Allowed tools: reason_propose" in proposal
    assert "decorated tool wrapper will prompt for confirmation" in proposal.replace("\n", " ")


def test_reason_propose_creates_thread_after_confirmation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins
    import sys

    def _isatty() -> bool:
        return True

    def _input(prompt: str = "") -> str:
        return "y"

    def _generate_reasoning_prompt(*args: object, **kwargs: object) -> str:
        return "Test-generated reasoning prompt."

    monkeypatch.setattr(sys.stdin, "isatty", _isatty)
    monkeypatch.setattr(builtins, "input", _input)
    monkeypatch.setattr("nuself.reason.service.generate_reasoning_prompt", _generate_reasoning_prompt)

    tool = _chat_tool(tmp_path, "reason_propose")
    result = _invoke_chat_tool(
        tool,
        {
            "topic": "What should I think about next?",
            "working_summary": "We should keep the thread short.",
            "active_items": [{"label": "next step", "kind": "decision"}],
            "mandates": ["advance at most one complete round per step"],
        },
    )

    events = read_log_events(project_root=tmp_path, component="reasoning")
    # The composed approval wrapper now returns a structured JSON string.
    parsed = json.loads(result)
    assert parsed.get("approved") is True
    assert parsed.get("component") == "reasoning"
    assert parsed.get("result") is not None
    assert any(event.event == "proposal_created" for event in events)
    assert events[-1].event == "thread_started"


def test_reason_export_tool_requires_confirmation_before_queueing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nuself.reason.output import ReasonOutputService
    from nuself.reason.repository import ReasonRepository
    from nuself.reason.service import ReasonService
    from nuself.reason.domain import ReasoningStep

    def _should_not_compose(*args: object, **kwargs: object) -> str:
        raise AssertionError("reason_export should not compose synchronously")

    def _input(prompt: str = "") -> str:
        return "y"

    monkeypatch.setattr(
        ReasonOutputService,
        "compose_with_runner",
        _should_not_compose,
    )

    service = ReasonService(repository=ReasonRepository(tmp_path), project_root=tmp_path, prompt_generator=lambda *args, **kwargs: "Test-generated reasoning prompt.")
    thread = service.start_thread("Queued export")
    service.advance_thread(
        thread.id,
        step=ReasoningStep(thread_id=thread.id, summary="Step 1", output="Out 1", delta="Delta 1"),
    )

    monkeypatch.setattr("builtins.input", _input)
    tool = _chat_tool(tmp_path, "reason_export")
    result = _invoke_chat_tool(tool, {"thread_id": thread.id, "segment_size": 1})
    parsed = json.loads(result)
    inner = json.loads(parsed["result"])

    assert parsed.get("approved") is True
    assert parsed.get("component") == "reasoning"
    assert inner.get("queued") is True
    assert inner.get("job", {}).get("thread_id") == thread.id
    # No file-based queue — the event went to the in-memory callback.
    assert not (Path(inner["paths"]["root"]) / "queue").exists()
    assert not Path(inner["paths"]["combined"]).exists()


# --- Memory management tools ---

def test_memory_archive_tool_success(tmp_path: Path) -> None:
    from nuself.memory.repository import MemoryEntryRepository
    from nuself.domain.memory import MemoryEntry

    repo = MemoryEntryRepository(tmp_path)
    repo.save(MemoryEntry(id="m1", type="belief", title="Old belief", body="..."))
    tool = _chat_tool(tmp_path, "memory_archive")
    result = _invoke_chat_tool(tool, {"entry_id": "m1"})
    assert "Archived" in result
    assert "Old belief" in result
    entry = repo.get("m1")
    assert entry.review_state == "archived"


def test_memory_archive_tool_not_found(tmp_path: Path) -> None:
    tool = _chat_tool(tmp_path, "memory_archive")
    result = _invoke_chat_tool(tool, {"entry_id": "nonexistent"})
    assert "Error" in result


def test_memory_update_importance_tool_success(tmp_path: Path) -> None:
    from nuself.memory.repository import MemoryEntryRepository
    from nuself.domain.memory import MemoryEntry

    repo = MemoryEntryRepository(tmp_path)
    repo.save(MemoryEntry(id="m1", type="belief", title="Key belief", body="...", importance=0.3))
    tool = _chat_tool(tmp_path, "memory_update_importance")
    result = _invoke_chat_tool(tool, {"entry_id": "m1", "importance": 0.9})
    assert "Updated importance" in result
    assert "0.90" in result
    entry = repo.get("m1")
    assert entry.importance == 0.9


def test_memory_update_importance_tool_out_of_range(tmp_path: Path) -> None:
    tool = _chat_tool(tmp_path, "memory_update_importance")
    assert "Error" in _invoke_chat_tool(tool, {"entry_id": "m1", "importance": 1.5})
    assert "Error" in _invoke_chat_tool(tool, {"entry_id": "m1", "importance": -0.1})


def test_memory_update_importance_tool_not_found(tmp_path: Path) -> None:
    tool = _chat_tool(tmp_path, "memory_update_importance")
    result = _invoke_chat_tool(tool, {"entry_id": "nonexistent", "importance": 0.5})
    assert "Error" in result


def test_memory_count_tool_empty(tmp_path: Path) -> None:
    tool = _chat_tool(tmp_path, "memory_count")
    result = _invoke_chat_tool(tool)
    assert "Memory entries: 0 total" in result


def test_memory_count_tool_with_entries(tmp_path: Path) -> None:
    from nuself.memory.repository import MemoryEntryRepository
    from nuself.domain.memory import MemoryEntry

    repo = MemoryEntryRepository(tmp_path)
    repo.save(MemoryEntry(type="belief", title="A", body="...", tags=["tag1"]))
    repo.save(MemoryEntry(type="goal", title="B", body="...", tags=["tag2"]))
    repo.save(MemoryEntry(type="belief", title="C", body="...", tags=["tag1", "tag2"]))
    tool = _chat_tool(tmp_path, "memory_count")
    result = _invoke_chat_tool(tool)
    assert "Memory entries: 3 total" in result


def test_memory_count_tool_with_type_filter(tmp_path: Path) -> None:
    from nuself.memory.repository import MemoryEntryRepository
    from nuself.domain.memory import MemoryEntry

    repo = MemoryEntryRepository(tmp_path)
    repo.save(MemoryEntry(type="belief", title="A", body="..."))
    repo.save(MemoryEntry(type="goal", title="B", body="..."))
    repo.save(MemoryEntry(type="belief", title="C", body="..."))
    tool = _chat_tool(tmp_path, "memory_count")
    result = _invoke_chat_tool(tool, {"types": ["belief"]})
    assert "Memory entries: 2 total" in result
    assert "filtered" in result
    assert "belief" in result


def test_memory_count_tool_with_tag_filter(tmp_path: Path) -> None:
    from nuself.memory.repository import MemoryEntryRepository
    from nuself.domain.memory import MemoryEntry

    repo = MemoryEntryRepository(tmp_path)
    repo.save(MemoryEntry(type="belief", title="A", body="...", tags=["important"]))
    repo.save(MemoryEntry(type="goal", title="B", body="...", tags=["archived"]))
    repo.save(MemoryEntry(type="belief", title="C", body="...", tags=["important"]))
    tool = _chat_tool(tmp_path, "memory_count")
    result = _invoke_chat_tool(tool, {"tags": ["important"]})
    assert "Memory entries: 2 total" in result
    assert "filtered" in result
    assert "important" in result


def test_reason_list_active_tool(tmp_path: Path) -> None:
    from nuself.reason.service import ReasonService

    service = ReasonService(tmp_path, prompt_generator=_test_reason_prompt_generator)
    service.start_thread("How should this be remembered?")
    tool = _chat_tool(tmp_path, "reason_list_active")

    result = _invoke_chat_tool(tool)

    data = json.loads(result)
    assert data["count"] == 1
    assert data["threads"][0]["index"] == 0
    assert data["threads"][0]["topic"] == "How should this be remembered?"
    assert data["threads"][0]["step_count"] == 0


def test_reason_count_tool(tmp_path: Path) -> None:
    from nuself.reason.service import ReasonService

    service = ReasonService(tmp_path, prompt_generator=_test_reason_prompt_generator)
    service.start_thread("Count this reason thread")
    tool = _chat_tool(tmp_path, "reason_count")

    result = _invoke_chat_tool(tool)

    assert json.loads(result) == {"by_status": {"active": 1}, "count": 1}


def test_reason_show_tool(tmp_path: Path) -> None:
    from nuself.reason.service import ReasonService

    thread = ReasonService(tmp_path, prompt_generator=_test_reason_prompt_generator).start_thread("Inspect this reason thread")
    tool = _chat_tool(tmp_path, "reason_show")

    result = _invoke_chat_tool(tool, {"thread_id": thread.id})

    data = json.loads(result)
    assert data["thread"]["topic"] == "Inspect this reason thread"
    assert data["thread"]["id"] == thread.id
    assert data["steps"] == []
    assert data["tool_logs"] == "omitted"


def test_reason_context_tool_shows_global_state_without_steps(tmp_path: Path) -> None:
    from nuself.reason.service import ReasonService

    thread = ReasonService(tmp_path, prompt_generator=_test_reason_prompt_generator).start_thread(
        "Context-only reason thread",
        working_summary="Current state summary",
        active_items=({"label": "Tracked premise", "kind": "premise"},),
        mandates=("Keep it bounded.",),
    )
    tool = _chat_tool(tmp_path, "reason_context")

    result = _invoke_chat_tool(tool, {"thread_id": thread.id})

    data = json.loads(result)
    assert data["thread"]["topic"] == "Context-only reason thread"
    assert data["thread"]["working_summary"] == "Current state summary"
    assert data["thread"]["active_items"][0]["label"] == "Tracked premise"
    assert data["thread"]["mandates"] == ["Keep it bounded."]
    assert data["step_count"] == 0
    assert "steps" not in data
    assert data["tool_logs"] == "omitted"


def test_reason_step_tool_shows_specific_step_without_tool_logs(tmp_path: Path) -> None:
    from nuself.reason.domain import ReasoningStep
    from nuself.reason.service import ReasonService

    service = ReasonService(tmp_path, prompt_generator=_test_reason_prompt_generator)
    thread = service.start_thread("Step reason thread")
    step = ReasoningStep(
        thread_id=thread.id,
        summary="Step summary",
        delta="Step delta",
        output="Visible step output",
        tool_logs=(
            {
                "component": "reasoning",
                "event": "service_tool_called",
                "message": "workspace_put completed",
                "status": "completed",
                "metadata": {"service_component": "workspace", "tool": "workspace_put", "args": {"key": "x"}},
            },
        ),
    )
    service.advance_thread(thread.id, step=step)
    tool = _chat_tool(tmp_path, "reason_step")

    result = _invoke_chat_tool(tool, {"thread_id": thread.id, "step": "0"})

    data = json.loads(result)
    assert data["thread"]["topic"] == "Step reason thread"
    assert data["step"]["index"] == 0
    assert data["step"]["kind"] == "progress"
    assert data["step"]["summary"] == "Step summary"
    assert data["step"]["output"] == "Visible step output"
    assert data["step"]["delta"] == "Step delta"
    assert data["step"]["terminal_status"] == "continue"
    assert "workspace_put" not in result
    assert "service_tool_called" not in result
    assert data["tool_logs"] == "omitted"


def test_reason_show_tool_omits_tool_logs(tmp_path: Path) -> None:
    from nuself.reason.domain import ReasoningStep
    from nuself.reason.service import ReasonService

    service = ReasonService(tmp_path, prompt_generator=_test_reason_prompt_generator)
    thread = service.start_thread("Show reason thread")
    service.advance_thread(
        thread.id,
        step=ReasoningStep(
            thread_id=thread.id,
            summary="Shown step summary",
            delta="Shown step delta",
            output="Shown output",
            tool_logs=(
                {
                    "component": "reasoning",
                    "event": "service_tool_called",
                    "message": "persona_think completed",
                    "status": "completed",
                    "metadata": {"service_component": "persona", "tool": "persona_think", "args": {"persona": "critic"}},
                },
            ),
        ),
    )
    tool = _chat_tool(tmp_path, "reason_show")

    result = _invoke_chat_tool(tool, {"thread_id": thread.id})

    data = json.loads(result)
    assert data["thread"]["topic"] == "Show reason thread"
    assert data["steps"][0]["summary"] == "Shown step summary"
    assert data["steps"][0]["output"] == "Shown output"
    assert "persona_think" not in result
    assert "service_tool_called" not in result


def _test_reason_prompt_generator(*args: object, **kwargs: object) -> str:
    return "Test-generated reasoning prompt."


def test_trace_search_tool(tmp_path: Path) -> None:
    from nuself.trace.service import TraceRecorder

    trace = TraceRecorder(tmp_path).record(
        kind="decision",
        title="Trace search target",
        summary="A searchable provenance item.",
    )
    tool = _chat_tool(tmp_path, "trace_search")

    result = _invoke_chat_tool(tool, {"query": "searchable"})

    assert "Matching trace records:" in result
    assert trace.title in result


def test_trace_count_tool(tmp_path: Path) -> None:
    from nuself.trace.service import TraceRecorder

    TraceRecorder(tmp_path).record(
        kind="decision",
        title="Trace count target",
        summary="A countable provenance item.",
    )
    tool = _chat_tool(tmp_path, "trace_count")

    result = _invoke_chat_tool(tool, {"query": "countable"})

    assert 'Trace records matching "countable": 1 total' in result


def test_trace_show_tool(tmp_path: Path) -> None:
    from nuself.trace.service import TraceRecorder

    trace = TraceRecorder(tmp_path).record(
        kind="decision",
        title="Trace detail target",
        summary="A detailed provenance item.",
    )
    tool = _chat_tool(tmp_path, "trace_show")

    result = _invoke_chat_tool(tool, {"trace_id": trace.id})

    assert "[trace] Trace detail target" in result
    assert "A detailed provenance item." in result


def test_chat_trace_diagnostics_cannot_replace_completed_answer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_trace(*args: object, **kwargs: object) -> None:
        raise OSError("trace store unavailable")

    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("audit store unavailable")

    monkeypatch.setattr(
        TraceRecorder,
        "record_chat_turn",
        fail_trace,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    runtime = ConversationGraphRuntime.__new__(
        ConversationGraphRuntime
    )
    runtime._project_root = tmp_path  # pyright: ignore[reportPrivateUsage]
    runtime._trace_recorder = TraceRecorder(  # pyright: ignore[reportPrivateUsage]
        tmp_path
    )
    response = ChatStructuredOutput(
        answer="completed answer",
        evidence_references=["memory-1"],
    )

    with pytest.warns(
        RuntimeWarning,
        match=(
            "memory/trace_write_failed: trace store unavailable; "
            "structured logging failed: audit store unavailable"
        ),
    ):
        trace_id = runtime._record_chat_turn_trace(  # pyright: ignore[reportPrivateUsage]
            user_message="hello",
            final_response=response,
            thread_id="thread-1",
            node_trace=("prepare_context", "respond"),
        )

    assert trace_id is None
    assert response.answer == "completed answer"


def test_chat_agent_includes_memory_tools_in_system_prompt(tmp_path: Path) -> None:
    from nuself.agent.chat import ChatAgent

    llm = FakeLLM()
    agent = ChatAgent(tmp_path, llm=llm)
    agent.respond("test")

    system_prompt = llm.calls[0][0].content
    assert "memory_archive" in system_prompt
    assert "memory_update_importance" in system_prompt
    assert "memory_count" in system_prompt
