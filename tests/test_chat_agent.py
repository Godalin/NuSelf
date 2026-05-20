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
    ChatResult,
    ConversationGraphRuntime,
    ConversationTurnState,
    ConversationRuntimeResult,
    ParsedChatResponse,
    PresentationAgent,
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
from nuself.trace.repository import TraceRepository


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


def test_chat_agent_parses_markdown_structured_response(tmp_path: Path) -> None:
    llm = SequencedStructuredFakeLLM(
        [
            "(synthesizer_self keeps context)\n\n"
            "**answer**: Use the profile context.\n\n"
            "**evidence_references**: [mem_123]\n"
            "**epistemic_status**: grounded\n",
            '{"answer":"Use the profile context.","evidence_references":["mem_123"],"epistemic_status":"grounded"}',
        ]
    )
    agent = ChatAgent(tmp_path, llm=llm, memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)))

    result = agent.respond("profile context")

    assert result.answer == "Use the profile context."
    assert result.evidence_references == ("mem_123",)
    assert result.epistemic_status == "grounded"
    assert "evidence_references" not in result.reply


def test_chat_agent_retries_when_protocol_leaks_into_answer(tmp_path: Path) -> None:
    leaked_answer = (
        '{"answer":"好的，我简单一点。","evidence_references":[],'
        '"confidence":0.8,"epistemic_status":"inferred"}'
    )
    llm = SequencedStructuredFakeLLM(
        [
            json.dumps(
                {
                    "answer": "先给一个内部草稿。",
                    "evidence_references": [],
                    "confidence": 0.4,
                    "epistemic_status": "inferred",
                }
            ),
            json.dumps(
                {
                    "answer": leaked_answer,
                    "evidence_references": [],
                    "confidence": 0.4,
                    "epistemic_status": "inferred",
                }
            ),
            json.dumps(
                {
                    "answer": "好的，我简单一点。",
                    "evidence_references": [],
                    "confidence": 0.8,
                    "epistemic_status": "inferred",
                }
            ),
        ]
    )
    agent = ChatAgent(tmp_path, llm=llm, memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)))

    result = agent.respond("可以简单一点吗")

    assert result.answer == "好的，我简单一点。"
    assert len(llm.calls) == 3
    assert "previous response leaked the internal response protocol" in llm.calls[2][-1].content


def test_chat_agent_retries_when_pretty_protocol_leaks_into_answer(tmp_path: Path) -> None:
    leaked_answer = "\n".join(
        [
            "{",
            '  "answer": "有的。这里是正常回复内容。",',
            '  "evidence_references": [],',
            '  "confidence": null,',
            '  "epistemic_status": "inferred"',
            "}",
        ]
    )
    llm = SequencedStructuredFakeLLM(
        [
            json.dumps(
                {
                    "answer": "内部草稿。",
                    "evidence_references": [],
                    "confidence": 0.4,
                    "epistemic_status": "inferred",
                }
            ),
            json.dumps(
                {
                    "answer": leaked_answer,
                    "evidence_references": [],
                    "confidence": None,
                    "epistemic_status": "inferred",
                }
            ),
            json.dumps(
                {
                    "answer": "有的。这里是正常回复内容。",
                    "evidence_references": [],
                    "confidence": 0.8,
                    "epistemic_status": "inferred",
                }
            ),
        ]
    )
    agent = ChatAgent(tmp_path, llm=llm, memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)))

    result = agent.respond("你有什么新想法吗")

    assert result.answer == "有的。这里是正常回复内容。"
    assert "evidence_references" not in result.reply
    assert len(llm.calls) == 3


def test_chat_agent_parses_fenced_json_protocol_response(tmp_path: Path) -> None:
    llm = StructuredFakeLLM(
        '```json\n'
        '{"answer":"Use the profile context.","evidence_references":["mem_123"],"epistemic_status":"grounded"}\n'
        '```'
    )
    agent = ChatAgent(tmp_path, llm=llm, memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)))

    result = agent.respond("profile context")

    assert result.answer == "Use the profile context."
    assert result.evidence_references == ("mem_123",)
    assert "```" not in result.reply
    assert "evidence_references" not in result.reply


def test_chat_agent_does_not_fallback_to_protocol_leaking_draft(tmp_path: Path) -> None:
    leaked_answer = (
        '{"answer":"好的，我简单一点。","evidence_references":[],'
        '"confidence":0.8,"epistemic_status":"inferred"}'
    )
    llm = SequencedStructuredFakeLLM(
        [
            json.dumps(
                {
                    "answer": leaked_answer,
                    "evidence_references": [],
                    "confidence": 0.4,
                    "epistemic_status": "inferred",
                }
            ),
            json.dumps(
                {
                    "answer": leaked_answer,
                    "evidence_references": [],
                    "confidence": 0.4,
                    "epistemic_status": "inferred",
                }
            ),
            json.dumps(
                {
                    "answer": leaked_answer,
                    "evidence_references": [],
                    "confidence": 0.4,
                    "epistemic_status": "inferred",
                }
            ),
        ]
    )
    agent = ChatAgent(tmp_path, llm=llm, memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)))

    result = agent.respond("可以简单一点吗")

    assert "evidence_references" not in result.answer
    assert '"answer"' not in result.answer
    assert result.epistemic_status == "unsupported"


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


def test_chat_agent_delegates_turns_to_conversation_runtime(tmp_path: Path) -> None:
    class FakeRuntime:
        def __init__(self) -> None:
            self.seen: list[tuple[ThreadState, str, str]] = []

        def run_turn(
            self,
            state: ThreadState,
            message: str,
            thread_id: str,
            *,
            turn_id: str | None = None,
        ) -> ConversationRuntimeResult:
            self.seen.append((state, message, thread_id))
            updated = ThreadState(
                thread_id=thread_id,
                summary=state.summary,
                messages=[
                    *state.messages,
                    ThreadMessage(role="user", content=message, turn_id=turn_id),
                    ThreadMessage(role="assistant", content="runtime reply", turn_id=turn_id),
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


def test_chat_agent_reuses_completed_turn_id_without_rerunning_runtime(tmp_path: Path) -> None:
    class FakeRuntime:
        def __init__(self) -> None:
            self.calls = 0

        def run_turn(
            self,
            state: ThreadState,
            message: str,
            thread_id: str,
            *,
            turn_id: str | None = None,
        ) -> ConversationRuntimeResult:
            self.calls += 1
            updated = ThreadState(
                thread_id=thread_id,
                summary=state.summary,
                messages=[
                    *state.messages,
                    ThreadMessage(role="user", content=message, turn_id=turn_id),
                    ThreadMessage(role="assistant", content=f"reply {self.calls}", turn_id=turn_id),
                ],
                next_message_index=state.next_message_index + 2,
            )
            return ConversationRuntimeResult(state=updated, result=ChatResult(answer=f"reply {self.calls}", thread_id=thread_id))

    runtime = FakeRuntime()
    agent = ChatAgent(tmp_path, runtime=runtime)

    first = agent.respond("retry me", turn_id="turn-retry")
    second = agent.respond("retry me", turn_id="turn-retry")

    assert first.answer == "reply 1"
    assert second.answer == "reply 1"
    assert runtime.calls == 1
    state = ThreadStore(tmp_path).load("default")
    assert state.messages == [
        ThreadMessage(role="user", content="retry me", turn_id="turn-retry"),
        ThreadMessage(role="assistant", content="reply 1", turn_id="turn-retry"),
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
    assert TraceRepository(tmp_path).list_traces(kind="chat_turn") == []


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
    traces = TraceRepository(tmp_path).list_traces(kind="chat_turn")
    assert len(traces) == 1
    trace = traces[0]
    assert trace.thread_id == "graph"
    assert trace.evidence_refs == ["mem_graph"]
    assert trace.inputs == ["graph runtime"]
    assert trace.outputs == ["Graph driver reply."]
    assert trace.participants == ["chat_agent", "presentation_agent"]
    assert trace.metadata["node_trace"] == list(result.node_trace)


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
    assert result.state.messages == [
        ThreadMessage(role="user", content="what about clarity?"),
        ThreadMessage(role="assistant", content="You value clarity."),
    ]
    assert all("[Tool call:" not in message.content for message in result.state.messages)
    assert llm.call_count == 3


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
    assert len(llm.calls) == 2
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
    assert "[Tool call:" not in result.reply
    stored = ThreadStore(tmp_path).load("default")
    assert all("[Tool call:" not in message.content for message in stored.messages)
    assert result.evidence_references == ("mem_123",)
    assert llm.call_count == 3
    # First call: initial prompt with tool documentation
    assert "Available tools:" in llm.calls[0][0].content
    assert "search_memory" in llm.calls[0][0].content
    # Second call: follow-up with tool result
    assert len(llm.calls[1]) > 0
    logs = [
        event
        for event in read_log_events(project_root=tmp_path, component="chat")
        if event.event == "service_tool_called"
    ]
    assert len(logs) == 1
    assert logs[0].status == "completed"
    assert logs[0].message.startswith('args: {"query": "clarity"}\nresult: ')
    assert "Clarity matters" in logs[0].metadata["message_body"]
    assert logs[0].metadata["service_component"] == "memory"
    assert logs[0].metadata["tool"] == "search_memory"


def test_chat_agent_recovers_raw_tool_marker_without_leaking(tmp_path: Path) -> None:
    llm = SequencedStructuredFakeLLM([
        "[Tool call: search_memory] Query: 反思 Limit: 10\n\nMemory context not found in search results.",
        '{"answer":"请你再说一遍，我会用正常回复格式回答。","epistemic_status":"unsupported"}',
    ])
    agent = ChatAgent(tmp_path, llm=llm)

    result = agent.respond("帮我查一下反思")

    assert "[Tool call:" not in result.reply
    assert result.answer == "请你再说一遍，我会用正常回复格式回答。"


def test_conversation_runtime_uses_langchain_native_tool_calls(tmp_path: Path) -> None:
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage, BaseMessage

    from nuself.llm import LLMSettings, LangChainLLMEndpoint

    repo = MemoryEntryRepository(tmp_path)
    repo.save(MemoryEntry(type="belief", title="Clarity matters", body="Prefer explicit assumptions."))

    class NativeToolModel:
        def __init__(self) -> None:
            self.calls: list[list[BaseMessage]] = []

        def bind_tools(self, tools: list[BaseTool]) -> "NativeToolModel":
            return self

        def with_structured_output(self, schema: type[ChatStructuredOutput]) -> "NativeToolModel":
            return self

        def invoke(self, messages: list[BaseMessage]) -> AIMessage:
            self.calls.append(messages)
            if len(self.calls) == 1:
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "search_memory",
                            "args": {"query": "clarity", "limit": 5},
                            "id": "call_search_memory",
                            "type": "tool_call",
                        }
                    ],
                )
            assert messages[-1].type == "tool"
            return AIMessage(content='{"answer":"You value clarity.","evidence_references":["mem_native"],"epistemic_status":"grounded"}')

    class NativeStructuredToolModel(NativeToolModel):
        def invoke(self, messages: list[BaseMessage]) -> AIMessage | ChatStructuredOutput:  # type: ignore[override]
            self.calls.append(messages)
            if len(self.calls) == 1:
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "search_memory",
                            "args": {"query": "clarity", "limit": 5},
                            "id": "call_search_memory",
                            "type": "tool_call",
                        }
                    ],
                )
            if len(self.calls) == 2:
                assert messages[-1].type == "tool"
                return AIMessage(content="This unstructured final text should not be parsed.")
            return ChatStructuredOutput(
                answer="You value clarity.",
                evidence_references=["mem_native"],
                epistemic_status="grounded",
            )

    native_model = NativeStructuredToolModel()
    runtime = ConversationGraphRuntime(
        tmp_path,
        llm=StructuredFakeLLM('{"answer":"You value clarity."}'),
        langchain_models=(
            LangChainLLMEndpoint(
                index=0,
                settings=LLMSettings(base_url="https://example.test/v1", api_key="key", model="native-test"),
                model=cast(BaseChatModel, native_model),
            ),
        ),
        memory_query_service=MemoryQueryService(repo),
    )

    result = runtime.run_turn(ThreadState.empty("native"), "what about clarity?", "native")

    assert result.result.answer == "You value clarity."
    assert result.node_trace == (
        "prepare_context",
        "persona_activation",
        "initial_response",
        "detect_tool_request",
        "finalize_response",
        "state_update",
        "compression",
    )
    assert len(native_model.calls) == 4
    logs = [
        event
        for event in read_log_events(project_root=tmp_path, component="chat")
        if event.event == "service_tool_called"
    ]
    assert len(logs) == 1
    assert logs[0].metadata["service_component"] == "memory"
    assert logs[0].metadata["tool"] == "search_memory"
    assert logs[0].message.startswith('args: {"limit": 5, "query": "clarity"}\nresult: ')


def test_chat_agent_rejects_raw_tool_marker_from_presentation(tmp_path: Path) -> None:
    class RawToolMarkerPresentationLLM:
        def __init__(self) -> None:
            self.call_count = 0

        def complete(self, messages: list[ChatMessage]) -> str:
            content = messages[0].content
            if "Persona Activation Gate" in content:
                return '{"activated": false, "selected_persona_ids": [], "trigger": "test", "should_escalate": false, "escalation_reason": ""}'
            self.call_count += 1
            if self.call_count == 1:
                return '{"answer":"这是安全的草稿。","epistemic_status":"grounded"}'
            return "[Tool call: search_memory] Query: 反思 Limit: 10"

    agent = ChatAgent(tmp_path, llm=RawToolMarkerPresentationLLM())

    result = agent.respond("简单回答")

    assert result.answer == "这是安全的草稿。"
    assert "[Tool call:" not in result.reply


def test_presentation_agent_uses_langchain_structured_output(tmp_path: Path) -> None:
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import BaseMessage

    from nuself.llm import LLMSettings, LangChainLLMEndpoint

    class NativePresentationModel:
        def __init__(self) -> None:
            self.calls: list[list[BaseMessage]] = []

        def with_structured_output(self, schema: type[ChatStructuredOutput]) -> "NativePresentationModel":
            return self

        def invoke(self, messages: list[BaseMessage]) -> ChatStructuredOutput:
            self.calls.append(messages)
            return ChatStructuredOutput(answer="整理后的回复。", epistemic_status="grounded")

    class FailingTextLLM:
        def complete(self, messages: list[ChatMessage]) -> str:
            raise AssertionError("presentation should use LangChain structured output")

    native_model = NativePresentationModel()
    agent = PresentationAgent(
        FailingTextLLM(),
        language_preference="zh-CN",
        langchain_models=(
            LangChainLLMEndpoint(
                index=0,
                settings=LLMSettings(base_url="https://example.test/v1", api_key="key", model="presentation-test"),
                model=cast(BaseChatModel, native_model),
            ),
        ),
        project_root=tmp_path,
    )

    result = agent.present(
        ParsedChatResponse(answer="raw draft", epistemic_status="grounded"),
        context_messages=(),
        current_user_message="帮我整理一下",
        conversation_summary="",
        thread_id="presentation",
    )

    assert result.answer == "整理后的回复。"
    assert native_model.calls
    logs = [
        event
        for event in read_log_events(project_root=tmp_path, component="chat")
        if event.event == "presentation_completed"
    ]
    assert logs[-1].metadata == {"epistemic_status": "grounded", "structured_output": True}


def test_chat_agent_tool_invocation_with_reflection_logs_service_call(tmp_path: Path) -> None:
    from nuself.reflection.repository import ReflectionEntry, ReflectionRepository

    repo = ReflectionRepository(tmp_path)
    repo.add(
        ReflectionEntry(
            id="reflection-test",
            title="Try a smaller next step",
            body="A pending idea.",
            candidate_type="question",
            confidence=0.8,
            novelty=0.7,
            urgency=0.4,
            interruption_cost=0.2,
            composite_score=0.65,
            status="pending",
            discussion_approved=None,
            discussion_trace=(),
            deep_link="nuself://thread/reflections",
            created_at="2026-05-19T00:00:00Z",
            reviewed_at=None,
        )
    )

    class ReflectionToolRequestLLM:
        def __init__(self) -> None:
            self.call_count = 0

        def complete(self, messages: list[ChatMessage]) -> str:
            content = messages[0].content
            if "Persona Activation Gate" in content:
                return '{"activated": false, "selected_persona_ids": [], "trigger": "test", "should_escalate": false, "escalation_reason": ""}'
            self.call_count += 1
            if self.call_count == 1:
                return '{"answer":"I will check pending reflections.","tool":"list_pending_reflections","tool_args":{"limit":3}}'
            return '{"answer":"There is a pending idea about taking a smaller next step."}'

    agent = ChatAgent(tmp_path, llm=ReflectionToolRequestLLM())

    result = agent.respond("do you have any reflections?")

    assert result.answer == "There is a pending idea about taking a smaller next step."
    logs = [
        event
        for event in read_log_events(project_root=tmp_path, component="chat")
        if event.event == "service_tool_called"
    ]
    assert len(logs) == 1
    assert logs[0].status == "completed"
    assert logs[0].message.startswith('args: {"limit": 3}\nresult: ')
    assert "Try a smaller next step" in logs[0].metadata["message_body"]
    assert logs[0].metadata["service_component"] == "reflection"
    assert logs[0].metadata["tool"] == "list_pending_reflections"


def test_chat_agent_includes_tool_descriptions_in_system_prompt(tmp_path: Path) -> None:
    llm = FakeLLM()
    agent = ChatAgent(tmp_path, llm=llm)

    agent.respond("test")

    system_prompt = llm.calls[0][0].content
    assert "Available tools:" in system_prompt
    assert "search_memory" in system_prompt
    assert "Search durable memory" in system_prompt


def test_chat_agent_includes_service_skills_in_system_prompt(tmp_path: Path) -> None:
    llm = FakeLLM()
    agent = ChatAgent(tmp_path, llm=llm)

    agent.respond("do you remember my earlier preferences?")

    system_prompt = llm.calls[0][0].content
    assert "Service skills:" in system_prompt
    assert "The following service skills are loaded from Agent Skills SKILL.md files." in system_prompt
    assert "- memory:" in system_prompt
    assert "Durable memory is not ambient context" in system_prompt
    assert "Use `search_memory` before answering" in system_prompt
    assert "- reflection:" in system_prompt


def test_conversation_runtime_registers_langchain_tools(tmp_path: Path) -> None:
    from langchain_core.tools import BaseTool

    runtime = ConversationGraphRuntime(
        tmp_path,
        llm=FakeLLM(),
        memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)),
    )
    tools = getattr(runtime, "_tools")

    assert "search_memory" in tools
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

    tool = _chat_tool(tmp_path, "search_memory", query_service=MemoryQueryService(repo))

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
    tool = _chat_tool(tmp_path, "search_memory", query_service=MemoryQueryService(repo))

    result = _invoke_chat_tool(tool, {"query": "current goal", "types": ["goal"], "tags": ["runtime"]})

    assert "Runtime migration" in result
    assert "Direct style" not in result


def test_memory_search_tool_with_invalid_inputs(tmp_path: Path) -> None:
    repo = MemoryEntryRepository(tmp_path)
    tool = _chat_tool(tmp_path, "search_memory", query_service=MemoryQueryService(repo))

    # Empty query
    result = _invoke_chat_tool(tool, {"query": "", "limit": 8})
    assert "Error" in result or "No matches" in result

    # Invalid limit
    result = _invoke_chat_tool(tool, {"query": "test", "limit": 0})
    assert "Error" in result


# --- Reflection consumption tools ---

def test_list_pending_reflections_empty(tmp_path: Path) -> None:
    from nuself.reflection.repository import ReflectionRepository

    repo = ReflectionRepository(tmp_path)
    tool = _chat_tool(tmp_path, "list_pending_reflections", reflection_repository=repo)
    result = _invoke_chat_tool(tool)
    assert "No pending reflection ideas" in result


def test_list_pending_reflections_with_entries(tmp_path: Path) -> None:
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
    tool = _chat_tool(tmp_path, "list_pending_reflections", reflection_repository=repo)
    result = _invoke_chat_tool(tool)
    assert "Pending reflection ideas:" in result
    assert "[1] Explore recursion in habits" in result
    assert "[2] Sleep and creativity link" in result


def test_list_pending_reflections_respects_limit(tmp_path: Path) -> None:
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
    tool = _chat_tool(tmp_path, "list_pending_reflections", reflection_repository=repo)
    result = _invoke_chat_tool(tool, {"limit": 2})
    assert result.count("[") == 2  # only two numbered items


def test_dismiss_reflection_success(tmp_path: Path) -> None:
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
    tool = _chat_tool(tmp_path, "dismiss_reflection", reflection_repository=repo)
    result = _invoke_chat_tool(tool, {"index": 1})
    assert "Dismissed" in result
    assert "Explore recursion in habits" in result
    assert repo.list(status="pending") == []


def test_dismiss_reflection_out_of_range(tmp_path: Path) -> None:
    from nuself.reflection.repository import ReflectionRepository

    repo = ReflectionRepository(tmp_path)
    tool = _chat_tool(tmp_path, "dismiss_reflection", reflection_repository=repo)
    result = _invoke_chat_tool(tool, {"index": 1})
    assert "out of range" in result


def test_dismiss_reflection_invalid_index(tmp_path: Path) -> None:
    from nuself.reflection.repository import ReflectionRepository

    repo = ReflectionRepository(tmp_path)
    tool = _chat_tool(tmp_path, "dismiss_reflection", reflection_repository=repo)
    assert "Error" in _invoke_chat_tool(tool, {"index": 0})
    assert "Error" in _invoke_chat_tool(tool, {"index": -1})


def test_archive_reflection_success(tmp_path: Path) -> None:
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
    tool = _chat_tool(tmp_path, "archive_reflection", reflection_repository=repo)
    result = _invoke_chat_tool(tool, {"index": 1})
    assert "Archived" in result
    assert "Explore recursion in habits" in result
    assert repo.list(status="pending") == []
    archived = repo.list(status="archived")
    assert len(archived) == 1


def test_archive_reflection_out_of_range(tmp_path: Path) -> None:
    from nuself.reflection.repository import ReflectionRepository

    repo = ReflectionRepository(tmp_path)
    tool = _chat_tool(tmp_path, "archive_reflection", reflection_repository=repo)
    result = _invoke_chat_tool(tool, {"index": 1})
    assert "out of range" in result


def test_archive_reflection_invalid_index(tmp_path: Path) -> None:
    from nuself.reflection.repository import ReflectionRepository

    repo = ReflectionRepository(tmp_path)
    tool = _chat_tool(tmp_path, "archive_reflection", reflection_repository=repo)
    assert "Error" in _invoke_chat_tool(tool, {"index": 0})
    assert "Error" in _invoke_chat_tool(tool, {"index": -1})


def test_chat_agent_includes_reflection_tools_in_system_prompt(tmp_path: Path) -> None:
    from nuself.agent.chat import ChatAgent

    llm = FakeLLM()
    agent = ChatAgent(tmp_path, llm=llm)
    agent.respond("test")

    system_prompt = llm.calls[0][0].content
    assert "list_pending_reflections" in system_prompt
    assert "archive_reflection" in system_prompt
    assert "dismiss_reflection" in system_prompt


def test_chat_agent_includes_reason_and_trace_tools_and_skills(tmp_path: Path) -> None:
    llm = FakeLLM()
    agent = ChatAgent(tmp_path, llm=llm)

    agent.respond("what are you still thinking about?")

    system_prompt = llm.calls[0][0].content
    assert "list_active_reasoning_threads" in system_prompt
    assert "show_reasoning_thread" in system_prompt
    assert "search_trace" in system_prompt
    assert "show_trace" in system_prompt
    assert "- reason:" in system_prompt
    assert "Reason is NuSelf's durable long-run thinking space." in system_prompt
    assert "- trace:" in system_prompt
    assert "Trace is NuSelf's thought provenance database." in system_prompt


# --- Memory management tools ---

def test_archive_memory_tool_success(tmp_path: Path) -> None:
    from nuself.memory.repository import MemoryEntryRepository
    from nuself.domain.memory import MemoryEntry

    repo = MemoryEntryRepository(tmp_path)
    repo.save(MemoryEntry(id="m1", type="belief", title="Old belief", body="..."))
    tool = _chat_tool(tmp_path, "archive_memory")
    result = _invoke_chat_tool(tool, {"entry_id": "m1"})
    assert "Archived" in result
    assert "Old belief" in result
    entry = repo.get("m1")
    assert entry.review_state == "archived"


def test_archive_memory_tool_not_found(tmp_path: Path) -> None:
    tool = _chat_tool(tmp_path, "archive_memory")
    result = _invoke_chat_tool(tool, {"entry_id": "nonexistent"})
    assert "Error" in result


def test_update_memory_importance_tool_success(tmp_path: Path) -> None:
    from nuself.memory.repository import MemoryEntryRepository
    from nuself.domain.memory import MemoryEntry

    repo = MemoryEntryRepository(tmp_path)
    repo.save(MemoryEntry(id="m1", type="belief", title="Key belief", body="...", importance=0.3))
    tool = _chat_tool(tmp_path, "update_memory_importance")
    result = _invoke_chat_tool(tool, {"entry_id": "m1", "importance": 0.9})
    assert "Updated importance" in result
    assert "0.90" in result
    entry = repo.get("m1")
    assert entry.importance == 0.9


def test_update_memory_importance_tool_out_of_range(tmp_path: Path) -> None:
    tool = _chat_tool(tmp_path, "update_memory_importance")
    assert "Error" in _invoke_chat_tool(tool, {"entry_id": "m1", "importance": 1.5})
    assert "Error" in _invoke_chat_tool(tool, {"entry_id": "m1", "importance": -0.1})


def test_update_memory_importance_tool_not_found(tmp_path: Path) -> None:
    tool = _chat_tool(tmp_path, "update_memory_importance")
    result = _invoke_chat_tool(tool, {"entry_id": "nonexistent", "importance": 0.5})
    assert "Error" in result


def test_count_memory_tool_empty(tmp_path: Path) -> None:
    tool = _chat_tool(tmp_path, "count_memory")
    result = _invoke_chat_tool(tool)
    assert "Memory entries: 0 total" in result


def test_count_memory_tool_with_entries(tmp_path: Path) -> None:
    from nuself.memory.repository import MemoryEntryRepository
    from nuself.domain.memory import MemoryEntry

    repo = MemoryEntryRepository(tmp_path)
    repo.save(MemoryEntry(type="belief", title="A", body="...", tags=["tag1"]))
    repo.save(MemoryEntry(type="goal", title="B", body="...", tags=["tag2"]))
    repo.save(MemoryEntry(type="belief", title="C", body="...", tags=["tag1", "tag2"]))
    tool = _chat_tool(tmp_path, "count_memory")
    result = _invoke_chat_tool(tool)
    assert "Memory entries: 3 total" in result


def test_count_memory_tool_with_type_filter(tmp_path: Path) -> None:
    from nuself.memory.repository import MemoryEntryRepository
    from nuself.domain.memory import MemoryEntry

    repo = MemoryEntryRepository(tmp_path)
    repo.save(MemoryEntry(type="belief", title="A", body="..."))
    repo.save(MemoryEntry(type="goal", title="B", body="..."))
    repo.save(MemoryEntry(type="belief", title="C", body="..."))
    tool = _chat_tool(tmp_path, "count_memory")
    result = _invoke_chat_tool(tool, {"types": ["belief"]})
    assert "Memory entries: 2 total" in result
    assert "filtered" in result
    assert "belief" in result


def test_count_memory_tool_with_tag_filter(tmp_path: Path) -> None:
    from nuself.memory.repository import MemoryEntryRepository
    from nuself.domain.memory import MemoryEntry

    repo = MemoryEntryRepository(tmp_path)
    repo.save(MemoryEntry(type="belief", title="A", body="...", tags=["important"]))
    repo.save(MemoryEntry(type="goal", title="B", body="...", tags=["archived"]))
    repo.save(MemoryEntry(type="belief", title="C", body="...", tags=["important"]))
    tool = _chat_tool(tmp_path, "count_memory")
    result = _invoke_chat_tool(tool, {"tags": ["important"]})
    assert "Memory entries: 2 total" in result
    assert "filtered" in result
    assert "important" in result


def test_list_active_reasoning_threads_tool(tmp_path: Path) -> None:
    from nuself.reason.service import ReasonService

    service = ReasonService(tmp_path)
    service.start_thread("How should this be remembered?")
    tool = _chat_tool(tmp_path, "list_active_reasoning_threads")

    result = _invoke_chat_tool(tool)

    assert "Active and paused reasoning threads:" in result
    assert "How should this be remembered?" in result
    assert "steps=0" in result


def test_show_reasoning_thread_tool(tmp_path: Path) -> None:
    from nuself.reason.service import ReasonService

    thread = ReasonService(tmp_path).start_thread("Inspect this reason thread")
    tool = _chat_tool(tmp_path, "show_reasoning_thread")

    result = _invoke_chat_tool(tool, {"thread_id": thread.id})

    assert "[reason] Inspect this reason thread" in result
    assert thread.id in result


def test_search_trace_tool(tmp_path: Path) -> None:
    from nuself.trace.service import TraceRecorder

    trace = TraceRecorder(tmp_path).record(
        kind="decision",
        title="Trace search target",
        summary="A searchable provenance item.",
    )
    tool = _chat_tool(tmp_path, "search_trace")

    result = _invoke_chat_tool(tool, {"query": "searchable"})

    assert "Matching trace records:" in result
    assert trace.title in result


def test_show_trace_tool(tmp_path: Path) -> None:
    from nuself.trace.service import TraceRecorder

    trace = TraceRecorder(tmp_path).record(
        kind="decision",
        title="Trace detail target",
        summary="A detailed provenance item.",
    )
    tool = _chat_tool(tmp_path, "show_trace")

    result = _invoke_chat_tool(tool, {"trace_id": trace.id})

    assert "[trace] Trace detail target" in result
    assert "A detailed provenance item." in result


def test_chat_agent_includes_memory_tools_in_system_prompt(tmp_path: Path) -> None:
    from nuself.agent.chat import ChatAgent

    llm = FakeLLM()
    agent = ChatAgent(tmp_path, llm=llm)
    agent.respond("test")

    system_prompt = llm.calls[0][0].content
    assert "archive_memory" in system_prompt
    assert "update_memory_importance" in system_prompt
    assert "count_memory" in system_prompt


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
    assert llm.call_count == 3
    entry = repo.get("m1")
    assert entry.review_state == "archived"
