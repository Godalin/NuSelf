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
| `list_pending_reflections` | Return pending reflection ideas from the reflection repository. |
| `dismiss_reflection` | Mark a reflection idea as dismissed. |

#### `list_pending_reflections`

- **Args**: `limit: int = 5`
- **Behavior**: Reads `ReflectionRepository.list(status="pending")` and formats entries for the LLM.
- **Returns**: A numbered list of pending ideas with title, type, and score. Empty message if none.
- **When to use**: The agent may call this when the conversation naturally pauses or when the user asks about "ideas", "thoughts", or "reflections".

#### `dismiss_reflection`

- **Args**: `index: int` (1-based index from `list_pending_reflections` output)
- **Behavior**: Looks up the pending entry at the given index, calls `ReflectionRepository.dismiss(entry.id)`, and returns confirmation.
- **Returns**: Confirmation or error message.
- **When to use**: After the user explicitly declines interest in a suggested reflection topic.

### New: Memory Management Tools

| Tool | Purpose |
|---|---|
| `archive_memory` | Change a memory entry's review state to `archived`. Archived entries are excluded from default search. |
| `update_memory_importance` | Adjust the importance score (0.0–1.0) of a memory entry. |

#### `archive_memory`

- **Args**: `entry_id: str`
- **Behavior**: Loads the memory entry, sets `review_state="archived"`, and saves it back.
- **Returns**: Confirmation with entry title, or error if not found.
- **When to use**: When the user indicates a memory is outdated, no longer relevant, or should be hidden from active context.

#### `update_memory_importance`

- **Args**: `entry_id: str`, `importance: float`
- **Behavior**: Updates the entry's importance score and saves it back.
- **Returns**: Confirmation with new importance value, or error if not found.
- **When to use**: When the user emphasizes or downplays the significance of a memory during conversation.

### New: Reason Awareness Tools (Read-Only)

| Tool | Purpose |
|---|---|
| `list_active_reasoning_threads` | Return active/paused reasoning threads. |
| `show_reasoning_thread` | Show details of a specific reasoning thread. |

#### `list_active_reasoning_threads`

- **Args**: none
- **Behavior**: Reads `ReasonService.list_threads(status_filter="active")` and formats active/paused threads for the LLM.
- **Returns**: Numbered list of threads with question, status, step count, and last-advanced time. Empty message if none.
- **When to use**: The agent may call this when the user asks about "what I'm thinking about", "open questions", "reasoning threads", or when contextually relevant.

#### `show_reasoning_thread`

- **Args**: `thread_id: str`
- **Behavior**: Reads the full thread via `ReasonService.show_thread(thread_id)` including hypotheses, open questions, and recent steps.
- **Returns**: Formatted thread details, or error if not found.
- **When to use**: When the user asks about a specific reasoning thread in detail.

### Future: Trace Awareness Tools

Trace tools (e.g. `search_trace`, `show_trace`) are deferred until trace has enough real data to be useful for the chat agent. At that point, add:

| Tool | Purpose |
|---|---|
| `search_trace` | Query thought provenance records. |
| `show_trace` | Show a specific trace record with its links. |

### Behavioral Guidelines for Reason Awareness (Prompt-Level)

> "You can also read active reasoning threads—durable long-run questions the user is working through. If the user asks about their open questions or threads, summarize the active reasoning threads. You may suggest advancing a thread if the conversation relates, but never create a new reasoning thread without asking the user to do it themselves via the `:reason start` command or `nuself reason start`."

### Behavioral Guidelines for Memory Curation (Prompt-Level)

> "You can also help the user curate their memory. If they say something like 'that doesn't matter anymore' or 'this is very important', you may archive the entry or adjust its importance. Always confirm the action with the user before invoking the tool."


## System Prompt Integration

The `_system_prompt` method in `ConversationGraphRuntime` must include a dynamic `Available tools` section. Each tool is described with:

- Name
- Argument schema
- When the agent should consider using it

Example additions:

```
- list_pending_reflections(limit: int = 5): View pending proactive ideas.
  Use when the user seems open to exploring new connections or questions,
  or when the conversation naturally pauses.
- dismiss_reflection(index: int): Remove an idea from the active pool.
  Use when the user explicitly says they are not interested in a topic.
- list_active_reasoning_threads(): View active reasoning threads.
  Use when the user asks about open questions or what they are
  thinking about.
- show_reasoning_thread(thread_id: str): Show details of a specific
  reasoning thread. Use when the user asks about a particular thread.
```

## Behavioral Guidelines (Prompt-Level)

The system prompt should include:

> "You have access to pending reflection ideas—proactive questions and connections generated from the user's memory and conversations. If the user seems curious or the conversation naturally touches on related topics, you may introduce one idea in your own words. Do not dump the raw list. If the user shows no interest, dismiss it. If the user engages, the conversation itself will naturally capture the outcome into memory."

## Dismissed Reflection Lifecycle

1. `dismiss_reflection` calls `ReflectionRepository.dismiss(entry_id)`.
2. Entry status becomes `dismissed`.
3. `list_pending_reflections` only queries `status="pending"`, so dismissed entries disappear from the agent's view.

## Testing Strategy

- Unit test each new tool in isolation.
- Integration test: verify the agent can invoke `list_pending_reflections` and `dismiss_reflection` through the graph runtime.
- Integration test: verify the agent can invoke `list_active_reasoning_threads` and `show_reasoning_thread` through the graph runtime.
- Test edge cases: empty repository, invalid index, duplicate dismiss, empty reason repository.
