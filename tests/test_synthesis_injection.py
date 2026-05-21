"""Tests for synthesis injection into internal response planning."""

from __future__ import annotations

from pathlib import Path

from nuself.agent.chat import ConversationGraphRuntime, ConversationTurnState, ThreadState
from nuself.llm import ChatMessage
from nuself.memory.query import MemoryQueryService
from nuself.memory.repository import MemoryEntryRepository


import json

class StructuredFakeLLM:
    """Fake LLM that captures all calls and returns structured response."""

    def __init__(self, response: str, activation_response: dict[str, object] | None = None) -> None:
        self.response = response
        self.calls: list[list[ChatMessage]] = []
        self._activation_response = activation_response or {
            "activated": True,
            "selected_persona_ids": ["skeptic_self", "builder_self", "analyst_self"],
            "trigger": "mixed intent",
            "should_escalate": False,
            "escalation_reason": "",
        }

    def complete(self, messages: list[ChatMessage]) -> str:
        content = messages[0].content
        if "Persona Activation Gate" in content:
            return json.dumps(self._activation_response)
        if "private reflection council" in content:
            return "LLM-backed persona perspective."
        if "You are the synthesizer. Distill" in content:
            return "LLM-backed synthesis of internal perspectives."
        self.calls.append(messages)
        return self.response


def test_selves_consult_returns_internal_synthesis(tmp_path: Path) -> None:
    """Verify that selves synthesis is now exposed through the subagent tool."""
    llm = StructuredFakeLLM('{"answer":"Synthesis-aware reply.","evidence_references":[],"confidence":0.5}')
    runtime = ConversationGraphRuntime(
        tmp_path,
        llm=llm,
        memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)),
    )

    result = runtime._consult_selves_tool(  # type: ignore[reportPrivateUsage]
        "What are the risks and implementation steps for this decision?"
    )

    assert "Selves consultation result:" in result
    assert "LLM-backed synthesis of internal perspectives." in result
    assert "skeptic_self" in result or "builder_self" in result


def test_synthesis_not_in_chat_result_payload(tmp_path: Path) -> None:
    """Verify that synthesis remains internal and does NOT appear in ChatResult.to_payload()."""
    llm = StructuredFakeLLM('{"answer":"Final answer.","evidence_references":[],"confidence":0.5}')
    runtime = ConversationGraphRuntime(
        tmp_path,
        llm=llm,
        memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)),
    )

    result = runtime.run_turn(
        ThreadState.empty("payload-test"),
        "What are the risks and implementation steps for this?",
        "payload-test",
    )

    # Verify ChatResult payload doesn't include synthesis info
    payload = result.result.to_payload()
    payload_str = str(payload)
    assert "Internal perspective fusion" not in payload_str
    assert "synthesizer_self" not in payload_str
    assert "synthesis" not in payload_str.lower()
    
    # Verify expected fields are present and correct
    assert payload["answer"] == "Final answer."
    assert payload["reply"] == "Final answer."
    assert payload["thread_id"] == "payload-test"
    assert isinstance(payload["evidence_references"], list)
    assert isinstance(payload["epistemic_status"], str)


def test_chat_graph_does_not_auto_activate_personas(tmp_path: Path) -> None:
    """Verify that the chat graph no longer auto-runs selves before tools."""
    llm = StructuredFakeLLM(
        '{"answer":"No synthesis reply.","evidence_references":[],"confidence":0.5}',
        activation_response={
            "activated": False,
            "selected_persona_ids": [],
            "trigger": "not relevant",
            "should_escalate": False,
            "escalation_reason": "",
        },
    )
    runtime = ConversationGraphRuntime(
        tmp_path,
        llm=llm,
        memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)),
    )

    turn_state = ConversationTurnState.start(
        ThreadState.empty("no-synthesis"),
        "Hello there.",
        "no-synthesis",
    )
    
    prepared = runtime.prepare_context_node(turn_state)
    activated = runtime.persona_activation_node(prepared.state)
    
    assert activated.state.persona_activation is not None
    assert not activated.state.persona_activation.activated
    assert activated.state.persona_turn_state is None
    
    # Build prompt should not fail with None synthesis
    prompt = runtime._build_prompt(activated.state)  # type: ignore[reportPrivateUsage]
    system_prompt = prompt[0].content
    
    # Verify synthesis section is not in system prompt when not activated
    assert "Internal perspective fusion:" not in system_prompt


def test_selves_consult_handles_explicit_multi_persona_request(tmp_path: Path) -> None:
    """Verify synthesis is generated for explicit multi-persona requests through the subagent tool."""
    llm = StructuredFakeLLM(
        '{"answer":"Multi-view reply.","evidence_references":[],"confidence":0.6}',
        activation_response={
            "activated": True,
            "selected_persona_ids": ["skeptic_self", "builder_self", "historian_self", "care_self"],
            "trigger": "explicit multi-view request",
            "should_escalate": False,
            "escalation_reason": "",
        },
    )
    runtime = ConversationGraphRuntime(
        tmp_path,
        llm=llm,
        memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)),
    )

    result = runtime._consult_selves_tool(  # type: ignore[reportPrivateUsage]
        "I want multiple perspectives on this: what are the risks, implementation plan, historical context, and emotional impact?",
    )

    assert "skeptic_self" in result
    assert "builder_self" in result
    assert "historian_self" in result
    assert "care_self" in result
    assert "source_personas:" in result


def test_synthesis_injection_preserves_existing_system_prompt_sections(tmp_path: Path) -> None:
    """Verify that synthesis injection doesn't break existing system prompt sections."""
    from nuself.domain.memory import MemoryEntry
    
    repo = MemoryEntryRepository(tmp_path)
    repo.save(
        MemoryEntry(
            type="belief",
            title="Clarity matters",
            body="Prefer explicit assumptions.",
            tags=["style"],
        )
    )
    
    llm = StructuredFakeLLM('{"answer":"Preserved reply.","evidence_references":[],"confidence":0.5}')
    runtime = ConversationGraphRuntime(
        tmp_path,
        llm=llm,
        memory_query_service=MemoryQueryService(repo),
    )

    turn_state = ConversationTurnState.start(
        ThreadState.empty("preserved-test"),
        "What are the risks in this approach?",  # Triggers skeptic
        "preserved-test",
    )
    
    prepared = runtime.prepare_context_node(turn_state)
    activated = runtime.persona_activation_node(prepared.state)
    prompt = runtime._build_prompt(activated.state)  # type: ignore[reportPrivateUsage]
    system_prompt = prompt[0].content

    # Verify essential sections are preserved
    assert "You are NuSelf" in system_prompt
    assert "private AI mirror" in system_prompt
    assert "Available tools:" in system_prompt
    assert "memory_search" in system_prompt
    assert "selves_consult" in system_prompt
    assert "Internal perspective fusion:" not in system_prompt


def test_initial_response_uses_main_prompt_after_noop_persona_node(tmp_path: Path) -> None:
    """Verify that ordinary chat uses the main prompt and can call selves as a tool."""
    llm = StructuredFakeLLM('{"answer":"Synthesized reply.","evidence_references":[],"confidence":0.8,"epistemic_status":"grounded"}')
    runtime = ConversationGraphRuntime(
        tmp_path,
        llm=llm,
        memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)),
    )

    turn_state = ConversationTurnState.start(
        ThreadState.empty("synth-test"),
        "What are the risks and implementation steps for this decision?",
        "synth-test",
    )
    
    prepared = runtime.prepare_context_node(turn_state)
    activated = runtime.persona_activation_node(prepared.state)
    initial = runtime.initial_response_node(activated.state)
    
    assert initial.state.initial_response is not None
    assert initial.state.initial_response.answer == "Synthesized reply."
    assert initial.state.initial_response.epistemic_status == "grounded"
    assert initial.state.initial_response.confidence == 0.8
    
    # Verify main prompt was used; selves is available as a tool.
    assert len(llm.calls) >= 1
    system_prompt = llm.calls[-1][0].content
    assert "You are NuSelf" in system_prompt
    assert "selves_consult" in system_prompt
    assert "synthesizer self" not in system_prompt
    assert "Persona contributions:" not in system_prompt
    assert "Do not narrate internal persona composition" in system_prompt


def test_non_activated_turn_uses_main_llm_prompt(tmp_path: Path) -> None:
    """Verify that non-activated turns still use the main LLM system prompt."""
    llm = StructuredFakeLLM(
        '{"answer":"Normal reply.","evidence_references":[],"confidence":0.5}',
        activation_response={
            "activated": False,
            "selected_persona_ids": [],
            "trigger": "not relevant",
            "should_escalate": False,
            "escalation_reason": "",
        },
    )
    runtime = ConversationGraphRuntime(
        tmp_path,
        llm=llm,
        memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)),
    )

    turn_state = ConversationTurnState.start(
        ThreadState.empty("normal-test"),
        "Hello there.",
        "normal-test",
    )
    
    prepared = runtime.prepare_context_node(turn_state)
    activated = runtime.persona_activation_node(prepared.state)
    
    assert activated.state.persona_turn_state is None
    
    initial = runtime.initial_response_node(activated.state)
    
    assert initial.state.initial_response is not None
    assert initial.state.initial_response.answer == "Normal reply."
    
    # Verify main prompt was used
    assert len(llm.calls) >= 1
    system_prompt = llm.calls[0][0].content
    assert "You are NuSelf" in system_prompt
    assert "synthesizer self" not in system_prompt
    assert "Do not narrate internal persona composition" in system_prompt
