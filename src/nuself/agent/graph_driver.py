"""LangGraph driver for conversation runtime nodes."""

from __future__ import annotations

from typing import Any, Protocol, TypedDict, cast

from langgraph.graph import END, START, StateGraph  # type: ignore[reportMissingTypeStubs]

from nuself.agent.chat import ConversationNodeResult, ConversationTurnState


class ConversationGraphRuntimeError(RuntimeError):
    """Raised when the conversation graph cannot complete a turn."""


class ConversationGraphState(TypedDict):
    """LangGraph state wrapper for one conversation turn."""

    turn_state: ConversationTurnState


class ConversationGraphNodeRuntime(Protocol):
    """Runtime methods exposed to the LangGraph driver."""

    def prepare_context_node(self, state: ConversationTurnState) -> ConversationNodeResult: ...

    def initial_response_node(self, state: ConversationTurnState) -> ConversationNodeResult: ...

    def tool_resolution_node(self, state: ConversationTurnState) -> ConversationNodeResult: ...

    def state_update_node(self, state: ConversationTurnState) -> ConversationNodeResult: ...

    def compression_node(self, state: ConversationTurnState) -> ConversationNodeResult: ...


class ConversationGraphDriver:
    """LangGraph driver that wires the conversation runtime nodes."""

    def __init__(self, runtime: ConversationGraphNodeRuntime) -> None:
        self._runtime = runtime
        graph: Any = StateGraph(ConversationGraphState)
        graph.add_node("prepare_context", self._prepare_context)
        graph.add_node("initial_response", self._initial_response)
        graph.add_node("tool_resolution", self._tool_resolution)
        graph.add_node("state_update", self._state_update)
        graph.add_node("compression", self._compression)
        graph.add_edge(START, "prepare_context")
        graph.add_edge("prepare_context", "initial_response")
        graph.add_edge("initial_response", "tool_resolution")
        graph.add_edge("tool_resolution", "state_update")
        graph.add_edge("state_update", "compression")
        graph.add_edge("compression", END)
        self._graph = graph.compile()

    def run(self, state: ConversationTurnState) -> ConversationTurnState:
        try:
            output: object = self._graph.invoke({"turn_state": state})
        except Exception as exc:
            raise ConversationGraphRuntimeError(f"conversation graph failed while handling thread '{state.thread_id}'") from exc
        if not isinstance(output, dict):
            raise ConversationGraphRuntimeError("conversation graph returned invalid state")
        graph_state = cast(ConversationGraphState, output)
        return graph_state["turn_state"]

    def _prepare_context(self, state: ConversationGraphState) -> ConversationGraphState:
        return {"turn_state": self._runtime.prepare_context_node(state["turn_state"]).state}

    def _initial_response(self, state: ConversationGraphState) -> ConversationGraphState:
        return {"turn_state": self._runtime.initial_response_node(state["turn_state"]).state}

    def _tool_resolution(self, state: ConversationGraphState) -> ConversationGraphState:
        return {"turn_state": self._runtime.tool_resolution_node(state["turn_state"]).state}

    def _state_update(self, state: ConversationGraphState) -> ConversationGraphState:
        return {"turn_state": self._runtime.state_update_node(state["turn_state"]).state}

    def _compression(self, state: ConversationGraphState) -> ConversationGraphState:
        return {"turn_state": self._runtime.compression_node(state["turn_state"]).state}
