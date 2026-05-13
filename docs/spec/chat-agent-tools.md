# Chat Agent Tools Spec

## Goal

Enable the chat agent to perform user-facing actions *during conversation*, turning it from a pure Q&A interface into a conversational decision proxy. The agent can search memory, inspect pending reflections, manage memory state, and drive proactive topics—all within the natural flow of chat.

## Architecture

### Tool Protocol

Tools implement the existing `Tool` protocol (`src/nuself/agent/tools.py`):

```python
class Tool(Protocol):
    name: str
    description: str
    def invoke(self, **kwargs: object) -> str: ...
```

Tools are **stateless callables**. They receive primitive arguments and return a string result that is injected back into the conversation context.

### Tool Registry

`ConversationGraphRuntime` owns a `dict[str, Tool]` registry. Adding a tool requires three steps:

1. Implement the `Tool` protocol.
2. Register it in `ConversationGraphRuntime.__init__`.
3. Describe it in `_system_prompt` so the LLM knows when to invoke it.

### Tool Invocation Flow

The LangGraph state machine already supports tool execution:

```
initial_response → detect_tool_request → [execute_tool]? → finalize_response
```

The LLM outputs a JSON object. If it contains `"tool": "<name>"` and `"tool_args": {...}`, the runtime looks up the tool by name, invokes it, and appends the result to the turn context before generating the final answer.

## Tool Catalog

### Current

| Tool | Purpose |
|---|---|
| `search_memory` | Query durable memory, profiles, and source chunks. |

### New: Reflection Consumption Tools

| Tool | Purpose |
|---|---|
| `list_pending_reflections` | Return pending reflection ideas from the outbox. |
| `dismiss_reflection` | Mark a reflection idea as dismissed. |

#### `list_pending_reflections`

- **Args**: `limit: int = 5`
- **Behavior**: Reads `NotificationOutbox.list(status="pending")` and formats entries for the LLM.
- **Returns**: A numbered list of pending ideas with title, type, and confidence. Empty message if none.
- **When to use**: The agent may call this when the conversation naturally pauses or when the user asks about "ideas", "thoughts", or "reflections".

#### `dismiss_reflection`

- **Args**: `index: int` (1-based index from `list_pending_reflections` output)
- **Behavior**: Looks up the pending entry at the given index, calls `NotificationOutbox.dismiss(entry.id)`, and returns confirmation.
- **Returns**: Confirmation or error message.
- **When to use**: After the user explicitly declines interest in a suggested reflection topic.

### Future: Memory Management Tools

| Tool | Purpose |
|---|---|
| `archive_memory` | Change a memory entry's review state to `archived` (requires new state). |
| `update_memory_importance` | Adjust importance score of a memory entry. |

These are reserved for a later phase; the current scope is reflection consumption only.

## System Prompt Integration

The `_system_prompt` method in `ConversationGraphRuntime` must include a dynamic `Available tools` section. Each tool is described with:

- Name
- Argument schema
- When the agent should consider using it

Example addition:

```
- list_pending_reflections(limit: int = 5): View pending proactive ideas.
  Use when the user seems open to exploring new connections or questions,
  or when the conversation naturally pauses.
- dismiss_reflection(index: int): Remove an idea from the active pool.
  Use when the user explicitly says they are not interested in a topic.
```

## Behavioral Guidelines (Prompt-Level)

The system prompt should include:

> "You have access to pending reflection ideas—proactive questions and connections generated from the user's memory and conversations. If the user seems curious or the conversation naturally touches on related topics, you may introduce one idea in your own words. Do not dump the raw list. If the user shows no interest, dismiss it. If the user engages, the conversation itself will naturally capture the outcome into memory."

## Dismissed Reflection Lifecycle

1. `dismiss_reflection` calls `NotificationOutbox.dismiss(entry_id)`.
2. Entry status becomes `dismissed`.
3. `list_pending_reflections` only queries `status="pending"`, so dismissed entries disappear from the agent's view.
4. `nuself notify clear` (existing CLI) physically deletes `dismissed` files.

## Testing Strategy

- Unit test each new tool in isolation.
- Integration test: verify the agent can invoke `list_pending_reflections` and `dismiss_reflection` through the graph runtime.
- Test edge cases: empty outbox, invalid index, duplicate dismiss.
