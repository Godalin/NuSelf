"""LangGraph driver for conversation runtime nodes."""

from __future__ import annotations

from typing import Any, Protocol, TypedDict, cast

from langgraph.graph import END, START, StateGraph  # type: ignore[reportMissingTypeStubs]

from nuself.agent.chat import ConversationNodeName, ConversationNodeResult, ConversationTurnState


class ConversationGraphRuntimeError(RuntimeError):
    """Raised when the conversation graph cannot complete a turn."""

    def __init__(
        self,
        message: str,
        *,
        node: ConversationNodeName | None = None,
        node_trace: tuple[ConversationNodeName, ...] = (),
    ) -> None:
        super().__init__(message)
        self.node = node
        self.node_trace = node_trace


class ConversationGraphState(TypedDict):
    """LangGraph state wrapper for one conversation turn."""

    turn_state: ConversationTurnState


class ConversationGraphNodeRuntime(Protocol):
    """Runtime methods exposed to the LangGraph driver."""

    def prepare_context_node(self, state: ConversationTurnState) -> ConversationNodeResult: ...

    def persona_activation_node(self, state: ConversationTurnState) -> ConversationNodeResult: ...

    def run_personas_node(self, state: ConversationTurnState) -> ConversationNodeResult: ...

    def initial_response_node(self, state: ConversationTurnState) -> ConversationNodeResult: ...

    def detect_tool_request_node(self, state: ConversationTurnState) -> ConversationNodeResult: ...

    def execute_tool_node(self, state: ConversationTurnState) -> ConversationNodeResult: ...

    def finalize_response_node(self, state: ConversationTurnState) -> ConversationNodeResult: ...

    def state_update_node(self, state: ConversationTurnState) -> ConversationNodeResult: ...

    def compression_node(self, state: ConversationTurnState) -> ConversationNodeResult: ...


class ConversationGraphDriver:
    """LangGraph driver that wires the conversation runtime nodes."""

    def __init__(self, runtime: ConversationGraphNodeRuntime) -> None:
        self._runtime = runtime
        graph: Any = StateGraph(ConversationGraphState)
        graph.add_node("prepare_context", self._prepare_context)
        graph.add_node("persona_activation", self._persona_activation)
        graph.add_node("run_personas", self._run_personas)
        graph.add_node("initial_response", self._initial_response)
        graph.add_node("detect_tool_request", self._detect_tool_request)
        graph.add_node("execute_tool", self._execute_tool)
        graph.add_node("finalize_response", self._finalize_response)
        graph.add_node("state_update", self._state_update)
        graph.add_node("compression", self._compression)
        graph.add_edge(START, "prepare_context")
        graph.add_edge("prepare_context", "persona_activation")
        graph.add_conditional_edges(
            "persona_activation",
            self._route_after_persona_activation,
            {"persona": "run_personas", "no_persona": "initial_response"},
        )
        graph.add_edge("run_personas", "initial_response")
        graph.add_edge("initial_response", "detect_tool_request")
        graph.add_conditional_edges(
            "detect_tool_request",
            self._route_after_tool_detection,
            {"tool": "execute_tool", "no_tool": "finalize_response"},
        )
        graph.add_edge("execute_tool", "finalize_response")
        graph.add_edge("finalize_response", "state_update")
        graph.add_edge("state_update", "compression")
        graph.add_edge("compression", END)
        self._graph = graph.compile()

    def run(self, state: ConversationTurnState) -> ConversationTurnState:
        try:
            output: object = self._graph.invoke({"turn_state": state})
        except ConversationGraphRuntimeError:
            raise
        except Exception as exc:
            raise ConversationGraphRuntimeError(
                f"conversation graph failed while handling thread '{state.thread_id}'",
                node_trace=state.node_trace,
            ) from exc
        if not isinstance(output, dict):
            raise ConversationGraphRuntimeError("conversation graph returned invalid state", node_trace=state.node_trace)
        graph_state = cast(ConversationGraphState, output)
        return graph_state["turn_state"]

    def _prepare_context(self, state: ConversationGraphState) -> ConversationGraphState:
        return self._run_node("prepare_context", state, self._runtime.prepare_context_node)

    def _persona_activation(self, state: ConversationGraphState) -> ConversationGraphState:
        return self._run_node("persona_activation", state, self._runtime.persona_activation_node)

    def _run_personas(self, state: ConversationGraphState) -> ConversationGraphState:
        return self._run_node("run_personas", state, self._runtime.run_personas_node)

    def _initial_response(self, state: ConversationGraphState) -> ConversationGraphState:
        return self._run_node("initial_response", state, self._runtime.initial_response_node)

    def _detect_tool_request(self, state: ConversationGraphState) -> ConversationGraphState:
        return self._run_node("detect_tool_request", state, self._runtime.detect_tool_request_node)

    def _execute_tool(self, state: ConversationGraphState) -> ConversationGraphState:
        return self._run_node("execute_tool", state, self._runtime.execute_tool_node)

    def _finalize_response(self, state: ConversationGraphState) -> ConversationGraphState:
        return self._run_node("finalize_response", state, self._runtime.finalize_response_node)

    def _route_after_tool_detection(self, state: ConversationGraphState) -> str:
        tool_call = state["turn_state"].tool_call
        return "tool" if tool_call is not None and tool_call.supported else "no_tool"

    def _route_after_persona_activation(self, state: ConversationGraphState) -> str:
        activation = state["turn_state"].persona_activation
        return "persona" if activation is not None and activation.activated else "no_persona"

    def _state_update(self, state: ConversationGraphState) -> ConversationGraphState:
        return self._run_node("state_update", state, self._runtime.state_update_node)

    def _compression(self, state: ConversationGraphState) -> ConversationGraphState:
        return self._run_node("compression", state, self._runtime.compression_node)

    def _run_node(
        self,
        node: ConversationNodeName,
        state: ConversationGraphState,
        run: "ConversationGraphNode",
    ) -> ConversationGraphState:
        turn_state = state["turn_state"]
        try:
            return {"turn_state": run(turn_state).state}
        except ConversationGraphRuntimeError:
            raise
        except Exception as exc:
            raise ConversationGraphRuntimeError(
                f"conversation graph node '{node}' failed while handling thread '{turn_state.thread_id}'",
                node=node,
                node_trace=(*turn_state.node_trace, node),
            ) from exc


class ConversationGraphNode(Protocol):
    """Callable shape for one conversation graph node."""

    def __call__(self, state: ConversationTurnState) -> ConversationNodeResult: ...
