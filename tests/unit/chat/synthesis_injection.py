"""Tests for synthesis injection into internal response planning."""

from __future__ import annotations

from chat_fixtures import ConversationGraphRuntime

# pyright: reportUnusedImport=false

from memory_fixtures import (
    memory_candidate_repository,
    memory_entry_repository,
    source_repository,
)

from pathlib import Path
from typing import Any, cast

import pytest
from langchain_core.messages import BaseMessage

from nuself.agent.chat.types import (
    ChatStructuredOutput,
    ConversationTurnState,
)
from nuself.conversation import ConversationState
from nuself.llm import LangChainLLMEndpoint
from nuself.memory.query import MemoryService
from nuself.memory.repository import MemoryEntryRepository
from nuself.persona.discussion import PersonaDiscussionAgents
from nuself.persona.graph import PersonaGraphAgents
from nuself.persona.definition import (
    PersonaActivationOutput,
    PersonaContributionOutput,
    PersonaSynthesisOutput,
)


class FakeResponseService:
    """Typed response fixture plus persona activation data."""

    def __init__(self, activation_response: dict[str, object] | None = None) -> None:
        self.calls: list[list[BaseMessage]] = []
        self._activation_response = activation_response or {
            "activated": True,
            "selected_persona_ids": ["skeptic_self", "builder_self", "analyst_self"],
            "trigger": "mixed intent",
            "should_escalate": False,
            "escalation_reason": "consultation only",
        }

    def complete(
        self,
        prompt: list[BaseMessage],
    ) -> ChatStructuredOutput:
        self.calls.append(prompt)
        return ChatStructuredOutput(answer="plain fallback")

    def finalize(
        self,
        state: ConversationTurnState,
        draft: ChatStructuredOutput,
    ) -> ChatStructuredOutput:
        del state
        return draft

    @property
    def activation_response(self) -> dict[str, object]:
        return self._activation_response


class StaticResponseService:
    def __init__(self, response: ChatStructuredOutput) -> None:
        self.response = response
        self.calls: list[list[BaseMessage]] = []

    def complete(self, prompt: list[BaseMessage]) -> ChatStructuredOutput:
        self.calls.append(prompt)
        return self.response

    def finalize(
        self,
        state: ConversationTurnState,
        draft: ChatStructuredOutput,
    ) -> ChatStructuredOutput:
        return draft


def _install_persona_agents(
    monkeypatch: pytest.MonkeyPatch,
    activation_response: dict[str, object],
) -> tuple[object, ...]:
    class _StaticAgent:
        def __init__(self, output: object) -> None:
            self._output = output

        def invoke(self, messages: object) -> object:
            del messages
            return self._output

    graph_agents = PersonaGraphAgents(
        activation=cast(
            Any,
            _StaticAgent(
                PersonaActivationOutput.model_validate(activation_response)
            ),
        ),
        contribution=cast(
            Any,
            _StaticAgent(
                PersonaContributionOutput(
                    note="Agent-backed persona perspective.",
                    questions=[],
                    confidence=0.5,
                )
            ),
        ),
        synthesis=cast(
            Any,
            _StaticAgent(
                PersonaSynthesisOutput(
                    summary="Agent-backed synthesis of internal perspectives.",
                    confidence=0.5,
                )
            ),
        ),
    )

    def fake_persona_graph_agents(
        endpoints: tuple[LangChainLLMEndpoint, ...],
        *,
        project_root: Path | None = None,
    ) -> PersonaGraphAgents:
        del endpoints, project_root
        return graph_agents

    monkeypatch.setattr(
        "nuself.agent.chat.persona.persona_graph_agents",
        fake_persona_graph_agents,
    )

    def fake_discussion_agents(
        project_root: Path | None = None,
        *,
        endpoints: tuple[LangChainLLMEndpoint, ...] | None = None,
    ) -> PersonaDiscussionAgents:
        del project_root, endpoints
        return PersonaDiscussionAgents(
            scoring=cast(Any, graph_agents.synthesis),
            selection=cast(Any, graph_agents.synthesis),
            moderator=cast(Any, graph_agents.synthesis),
        )

    monkeypatch.setattr(
        "nuself.persona.discussion.default_persona_discussion_agents",
        fake_discussion_agents,
    )
    return cast(tuple[object, ...], (object(),))


def test_selves_consult_returns_internal_synthesis(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify that selves synthesis is now exposed through the subagent tool."""
    llm = FakeResponseService()
    models = _install_persona_agents(
        monkeypatch,
        llm.activation_response,
    )
    runtime = ConversationGraphRuntime(
        tmp_path,
        response_service=llm,
        langchain_models=cast(Any, models),
        memory_query_service=MemoryService(memory_entry_repository(tmp_path)),
    )

    result = runtime._consult_selves_tool(  # type: ignore[reportPrivateUsage]
        "What are the risks and implementation steps for this decision?"
    )

    assert "Selves consultation result:" in result
    assert "Agent-backed synthesis of internal perspectives." in result
    assert "skeptic_self" in result or "builder_self" in result


def test_chat_graph_does_not_auto_activate_personas(tmp_path: Path) -> None:
    """Verify that the chat graph does not include synthesis sections in the normal respond path."""
    runtime = ConversationGraphRuntime(
        tmp_path,
        response_service=StaticResponseService(
            ChatStructuredOutput(answer="No synthesis reply.", confidence=0.5)
        ),
        memory_query_service=MemoryService(memory_entry_repository(tmp_path)),
    )

    turn_state = ConversationTurnState.start(
        ConversationState.empty("no-synthesis"),
        "Hello there.",
        "no-synthesis",
    )
    
    prepared = runtime.prepare_context_node(turn_state)
    result = runtime.respond_node(prepared.state)
    
    assert result.state.final_response is not None
    assert result.state.final_response.answer == "No synthesis reply."
    
    # Build prompt should not contain synthesis sections
    prompt = runtime._build_prompt(prepared.state)  # type: ignore[reportPrivateUsage]
    system_prompt = prompt[0].text
    assert "Internal perspective fusion:" not in system_prompt


def test_selves_consult_handles_explicit_multi_persona_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify synthesis is generated for explicit multi-persona requests through the subagent tool."""
    llm = FakeResponseService(
        {
            "activated": True,
            "selected_persona_ids": ["skeptic_self", "builder_self", "historian_self", "care_self"],
            "trigger": "explicit multi-view request",
            "should_escalate": False,
            "escalation_reason": "consultation only",
        },
    )
    models = _install_persona_agents(
        monkeypatch,
        llm.activation_response,
    )
    runtime = ConversationGraphRuntime(
        tmp_path,
        response_service=llm,
        langchain_models=cast(Any, models),
        memory_query_service=MemoryService(memory_entry_repository(tmp_path)),
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
    """Verify that the normal respond path preserves essential system prompt sections."""
    from nuself.memory.model import MemoryEntry
    
    repo = memory_entry_repository(tmp_path)
    repo.save(
        MemoryEntry(
            type="belief",
            title="Clarity matters",
            body="Prefer explicit assumptions.",
            tags=["style"],
        )
    )
    
    llm = FakeResponseService()
    runtime = ConversationGraphRuntime(
        tmp_path,
        response_service=llm,
        memory_query_service=MemoryService(repo),
    )

    turn_state = ConversationTurnState.start(
        ConversationState.empty("preserved-test"),
        "What are the risks in this approach?",  # Triggers skeptic
        "preserved-test",
    )
    
    prepared = runtime.prepare_context_node(turn_state)
    prompt = runtime._build_prompt(prepared.state)  # type: ignore[reportPrivateUsage]
    system_prompt = prompt[0].text

    # Verify essential sections are preserved
    assert "You are NuSelf" in system_prompt
    assert "private AI mirror" in system_prompt
    assert "Available tools:" in system_prompt
    assert "memory_search" in system_prompt
    assert "selves_consult" in system_prompt
    assert "Internal perspective fusion:" not in system_prompt


def test_respond_node_uses_main_prompt(tmp_path: Path) -> None:
    """Verify that respond_node uses the main prompt and selves is available as a tool."""
    response_service = StaticResponseService(
        ChatStructuredOutput(
            answer="Synthesized reply.",
            confidence=0.8,
            epistemic_status="grounded",
        )
    )
    runtime = ConversationGraphRuntime(
        tmp_path,
        response_service=response_service,
        memory_query_service=MemoryService(memory_entry_repository(tmp_path)),
    )

    turn_state = ConversationTurnState.start(
        ConversationState.empty("synth-test"),
        "What are the risks and implementation steps for this decision?",
        "synth-test",
    )
    
    prepared = runtime.prepare_context_node(turn_state)
    result = runtime.respond_node(prepared.state)
    
    assert result.state.final_response is not None
    assert result.state.final_response.answer == "Synthesized reply."
    assert result.state.final_response.epistemic_status == "grounded"
    assert result.state.final_response.confidence == 0.8
    
    # Verify main prompt was used; selves is available as a tool.
    assert len(response_service.calls) >= 1
    system_prompt = response_service.calls[-1][0].text
    assert "You are NuSelf" in system_prompt
    assert "selves_consult" in system_prompt
    assert "synthesizer self" not in system_prompt
    assert "Persona contributions:" not in system_prompt
    assert "Do not narrate internal persona composition" in system_prompt


def test_non_activated_turn_uses_main_llm_prompt(tmp_path: Path) -> None:
    """Verify that respond_node uses the main LLM system prompt."""
    response_service = StaticResponseService(
        ChatStructuredOutput(answer="Normal reply.", confidence=0.5)
    )
    runtime = ConversationGraphRuntime(
        tmp_path,
        response_service=response_service,
        memory_query_service=MemoryService(memory_entry_repository(tmp_path)),
    )

    turn_state = ConversationTurnState.start(
        ConversationState.empty("normal-test"),
        "Hello there.",
        "normal-test",
    )
    
    prepared = runtime.prepare_context_node(turn_state)
    result = runtime.respond_node(prepared.state)
    
    assert result.state.final_response is not None
    assert result.state.final_response.answer == "Normal reply."
    
    # Verify main prompt was used
    assert len(response_service.calls) >= 1
    system_prompt = response_service.calls[0][0].text
    assert "You are NuSelf" in system_prompt
    assert "synthesizer self" not in system_prompt
    assert "Do not narrate internal persona composition" in system_prompt
