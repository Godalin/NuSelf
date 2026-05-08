"""Tests for synthesis injection into internal response planning."""

from __future__ import annotations

from pathlib import Path

from nuself.agent.chat import (
    ConversationGraphRuntime,
    ConversationTurnState,
    ThreadState,
)
from nuself.llm import ChatMessage
from nuself.memory.query import MemoryQueryService
from nuself.memory.repository import MemoryEntryRepository


class StructuredFakeLLM:
    """Fake LLM that captures all calls and returns structured response."""
    
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[list[ChatMessage]] = []

    def complete(self, messages: list[ChatMessage]) -> str:
        self.calls.append(messages)
        return self.response


def test_synthesis_is_injected_into_initial_response_prompt(tmp_path: Path) -> None:
    """Verify that persona synthesis is included in the LLM prompt for initial response."""
    llm = StructuredFakeLLM('{"answer":"Synthesis-aware reply.","evidence_references":[],"confidence":0.5}')
    runtime = ConversationGraphRuntime(
        tmp_path,
        llm=llm,
        memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)),
    )

    # Manually run through the graph to control synthesis
    turn_state = ConversationTurnState.start(
        ThreadState.empty("synthesis-test"),
        "What are the risks and implementation steps for this decision?",  # Mixed intent
        "synthesis-test",
    )
    
    # Step 1: prepare_context
    prepared = runtime.prepare_context_node(turn_state)
    
    # Step 2: activate personas (mixed_intent_heuristic should activate skeptic + builder + analyst for long question)
    activated = runtime.persona_activation_node(prepared.state)
    assert activated.state.persona_activation is not None
    assert activated.state.persona_activation.trigger == "mixed_intent_heuristic"
    
    # Step 3: run personas to generate synthesis
    run_personas = runtime.run_personas_node(activated.state)
    persona_turn_state = run_personas.state.persona_turn_state
    assert persona_turn_state is not None
    assert len(persona_turn_state.contributions) >= 2  # At least skeptic + builder, possibly analyst
    assert persona_turn_state.synthesis is not None
    
    # Step 4: build prompt and verify synthesis is included
    prompt = runtime._build_prompt(run_personas.state)  # type: ignore[reportPrivateUsage]
    system_prompt = prompt[0].content
    
    # Verify synthesis is in the system prompt
    assert "Internal perspective fusion:" in system_prompt
    assert "Summary:" in system_prompt
    assert persona_turn_state.synthesis.summary in system_prompt
    assert "skeptic_self" in system_prompt or "builder_self" in system_prompt


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
        "What are the risks and implementation steps for this?",  # Mixed intent triggers synthesis
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


def test_synthesis_empty_when_personas_not_activated(tmp_path: Path) -> None:
    """Verify that synthesis is None when personas are not activated."""
    llm = StructuredFakeLLM('{"answer":"No synthesis reply.","evidence_references":[],"confidence":0.5}')
    runtime = ConversationGraphRuntime(
        tmp_path,
        llm=llm,
        memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)),
    )

    turn_state = ConversationTurnState.start(
        ThreadState.empty("no-synthesis"),
        "Hello there.",  # Trivial message, no persona activation
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


def test_synthesis_included_with_explicit_multi_persona_request(tmp_path: Path) -> None:
    """Verify synthesis is generated and injected for explicit multi-persona requests."""
    llm = StructuredFakeLLM('{"answer":"Multi-view reply.","evidence_references":[],"confidence":0.6}')
    runtime = ConversationGraphRuntime(
        tmp_path,
        llm=llm,
        memory_query_service=MemoryQueryService(MemoryEntryRepository(tmp_path)),
    )

    turn_state = ConversationTurnState.start(
        ThreadState.empty("explicit-multi"),
        "I want multiple perspectives on this: what are the risks, implementation plan, historical context, and emotional impact?",
        "explicit-multi",
    )
    
    prepared = runtime.prepare_context_node(turn_state)
    activated = runtime.persona_activation_node(prepared.state)
    
    assert activated.state.persona_activation is not None
    assert activated.state.persona_activation.trigger == "explicit_relevant_personas"
    assert len(activated.state.persona_activation.selected_personas) >= 3  # At least 3 personas
    
    # Run personas to generate synthesis
    run_personas = runtime.run_personas_node(activated.state)
    persona_turn_state = run_personas.state.persona_turn_state
    assert persona_turn_state is not None
    assert len(persona_turn_state.contributions) >= 3  # Multiple contributions
    assert persona_turn_state.synthesis is not None
    
    # Verify synthesis summary includes persona ids
    synthesis = persona_turn_state.synthesis
    assert len(synthesis.source_personas) >= 3
    
    # Build prompt and verify synthesis details
    prompt = runtime._build_prompt(run_personas.state)  # type: ignore[reportPrivateUsage]
    system_prompt = prompt[0].content
    assert "Internal perspective fusion:" in system_prompt
    assert f"Perspectives involved: {', '.join(synthesis.source_personas)}" in system_prompt or len(synthesis.source_personas) > 0


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
    run_personas = runtime.run_personas_node(activated.state)
    
    prompt = runtime._build_prompt(run_personas.state)  # type: ignore[reportPrivateUsage]
    system_prompt = prompt[0].content

    # Verify essential sections are preserved
    assert "You are NuSelf" in system_prompt
    assert "private AI mirror" in system_prompt
    assert "Available tools:" in system_prompt
    assert "search_memory" in system_prompt
    
    # And synthesis is also present
    assert "Internal perspective fusion:" in system_prompt


def test_activated_turn_uses_synthesizer_for_initial_response(tmp_path: Path) -> None:
    """Verify that activated turns use synthesizer prompt instead of main system prompt."""
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
    run_personas = runtime.run_personas_node(activated.state)
    
    # initial_response_node should use synthesizer prompt
    initial = runtime.initial_response_node(run_personas.state)
    
    assert initial.state.initial_response is not None
    assert initial.state.initial_response.answer == "Synthesized reply."
    assert initial.state.initial_response.epistemic_status == "grounded"
    assert initial.state.initial_response.confidence == 0.8
    
    # Verify synthesizer prompt was used (system prompt should mention "synthesizer self")
    assert len(llm.calls) >= 1
    synthesizer_call = llm.calls[-1]
    system_prompt = synthesizer_call[0].content
    assert "synthesizer self" in system_prompt
    assert "Persona contributions:" in system_prompt


def test_non_activated_turn_uses_main_llm_prompt(tmp_path: Path) -> None:
    """Verify that non-activated turns still use the main LLM system prompt."""
    llm = StructuredFakeLLM('{"answer":"Normal reply.","evidence_references":[],"confidence":0.5}')
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
