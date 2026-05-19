# Chat Agent Tools Spec

## Goal

Enable the chat agent to perform user-facing actions *during conversation*, turning it from a pure Q&A interface into a conversational decision proxy. The agent can search memory, inspect pending reflections, manage memory state, and drive proactive topics—all within the natural flow of chat.

## Architecture

### LangChain Tool Boundary

Chat tools are registered as LangChain tools, following the current LangChain Python tool interface. Tool definitions must be `BaseTool` / `StructuredTool` objects, usually built from typed Python functions via `StructuredTool.from_function(...)` or an equivalent LangChain-supported decorator/factory.

NuSelf must not keep a parallel chat-tool protocol, class hierarchy, or registry. Service modules may expose normal Python APIs, but anything visible to the chat runtime must enter through the LangChain tool boundary.

Tools are **stateless callables** at the LangChain boundary. They receive structured primitive arguments and return a string result that is injected back into the conversation context.

### Tool Registry

`ConversationGraphRuntime` owns a `dict[str, BaseTool]` registry. Adding a tool requires three steps:

1. Implement a small typed Python function that closes over the relevant service.
2. Wrap it as a LangChain `StructuredTool`.
3. Register it in `ConversationGraphRuntime.__init__`.

Prompt text may summarize loaded tools for models that still use NuSelf's JSON response envelope, but prompt text is not the source of truth. The registered LangChain tool objects and their schemas are the source of truth.

### Agent Skills

Every agent-facing service should be described by two prompt layers:

1. **Tool inventory**: the LangChain tools the agent can call.
2. **Service skill**: the behavioral policy for when the agent should call those tools.

Tools alone are not enough. A model may treat tools as optional buttons unless the prompt explains that a service is not ambient context. Skills tell the agent how the subsystem should participate in reasoning.

Skills must follow the Agent Skills `SKILL.md` directory convention used by LangChain Deep Agents:

```text
skills/
  memory/
    SKILL.md
  reflection/
    SKILL.md
  reason/
    SKILL.md
  trace/
    SKILL.md
```

Each `SKILL.md` starts with YAML frontmatter containing at least `name` and `description`, followed by Markdown instructions. NuSelf also uses `allowed-tools` to name the LangChain tools the skill may call.

Current chat runtime loads these `SKILL.md` files and injects their instructions into response-generation prompts. When NuSelf migrates chat to Deep Agents, the same skill directories should be passed to `create_deep_agent(..., skills=[...])` rather than converted back into hard-coded prompt strings.

Rules:

- A skill may require a tool call before answering a class of questions.
- A skill may prohibit claims that would require service data unless a tool result or visible context supports them.
- A skill should name the exact tools it depends on.
- A skill should be reusable across ordinary response generation and persona-synthesized responses.
- Skills must not invent hidden access. If the service data is not in visible context, the agent must call the relevant tool or state uncertainty.
- Skill instructions must live in `SKILL.md`; do not hard-code service skill prose in `chat.py`.

### Tool Invocation Flow

The LangGraph state machine already supports tool execution:

```
initial_response → detect_tool_request → [execute_tool]? → finalize_response
```

The current runtime still accepts NuSelf's JSON response envelope. If the response contains `"tool": "<name>"` and `"tool_args": {...}`, the runtime looks up the registered LangChain tool by name, invokes it with the structured args dict, and appends the result to the turn context before generating the final answer.

When the LLM adapter is migrated to a native LangChain chat model, the same registered tools should be passed to the model with LangChain's tool-calling APIs (for example `bind_tools(...)` or agent creation with `tools=[...]`) rather than re-encoding tool schemas by hand.

## Tool Catalog

### Current

| Tool | Purpose |
|---|---|
| `search_memory` | Query durable memory, profiles, and source chunks. |

### New: Reflection Consumption Tools

| Tool | Purpose |
|---|---|---|
| `list_pending_reflections` | Return pending reflection ideas from the reflection repository. |
| `dismiss_reflection` | Mark a reflection idea as dismissed. |
| `archive_reflection` | Archive a reflection idea after the discussion is complete. |

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

#### `archive_reflection`

- **Args**: `index: int` (1-based index from `list_pending_reflections` output)
- **Behavior**: Looks up the pending entry at the given index, calls `ReflectionRepository.archive(entry.id)`, and returns confirmation.
- **Returns**: Confirmation with entry title, or error if not found.
- **When to use**: After the user has engaged with a reflection idea and the discussion feels complete.

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
- **Behavior**: Reads `ReasonService.list_threads(status="active")` and formats active/paused threads for the LLM.
- **Returns**: Numbered list of threads with question, status, step count, and last-advanced time. Empty message if none.
- **When to use**: The agent may call this when the user asks about "what I'm thinking about", "open questions", "reasoning threads", or when contextually relevant.

#### `show_reasoning_thread`

- **Args**: `thread_id: str`
- **Behavior**: Reads the full thread via `ReasonService.show_thread(thread_id)` including hypotheses, open questions, and recent steps.
- **Returns**: Formatted thread details, or error if not found.
- **When to use**: When the user asks about a specific reasoning thread in detail.

### New: Trace Awareness Tools (Read-Only)

Trace tools let the chat agent inspect thought provenance without mutating it.

| Tool | Purpose |
|---|---|
| `search_trace` | Query thought provenance records. |
| `show_trace` | Show a specific trace record with its links. |

### Behavioral Guidelines for Reason Awareness (Prompt-Level)

> "You can also read active reasoning threads—durable long-run questions the user is working through. If the user asks about their open questions or threads, summarize the active reasoning threads. You may suggest advancing a thread if the conversation relates, but never create a new reasoning thread without asking the user to do it themselves via the `:reason start` command or `nuself reason start`."

### Behavioral Guidelines for Memory Curation (Prompt-Level)

> "You can also help the user curate their memory. If they say something like 'that doesn't matter anymore' or 'this is very important', you may archive the entry or adjust its importance. Always confirm the action with the user before invoking the tool."


## System Prompt Integration

Every chat response-generation prompt in `ConversationGraphRuntime` must include the same `Available tools` section. This includes both the ordinary `_system_prompt` path and the persona-synthesis response path. Persona activation must not hide tool availability from the final response agent.

Each tool is described with:

- Name
- Argument schema
- When the agent should consider using it

The prompt must also state that these tools are loaded in the current NuSelf runtime. If the user asks whether memory tools are available, the agent should answer from this runtime tool list rather than from generic model limitations.

Every chat response-generation prompt must also include a `Service skills` section rendered from loaded Agent Skills. The section is the usage policy for service-backed tools, not a second tool registry.

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

### Memory Skill

The memory skill lives in `src/nuself/agent/skills/memory/SKILL.md` and must include this behavioral contract:

> "Durable memory is not ambient context. If the user asks about past preferences, decisions, recurring patterns, previous discussions, stored memories, or what NuSelf remembers, use `search_memory` before answering unless the answer is fully present in the current visible conversation or already provided in `Relevant memory context`. Do not say you lack memory tools when `search_memory` is listed. If you do not call `search_memory`, do not claim that no memory exists."

### Reflection Skill

The reflection skill lives in `src/nuself/agent/skills/reflection/SKILL.md` and must include this behavioral contract:

> "Reflection ideas are proactive suggestions, not facts about the user. Use `list_pending_reflections` only when the user asks for ideas/thoughts/reflections, the conversation naturally pauses, or a topic strongly matches proactive exploration. Introduce at most one idea in natural language. Use `dismiss_reflection` when the user declines a topic, and `archive_reflection` when the user engages and the discussion feels complete."

### Reason Skill

The reason skill lives in `src/nuself/agent/skills/reason/SKILL.md` and must include this behavioral contract:

> "Reason is NuSelf's durable long-run thinking space. If the user asks about active long-running questions, open threads, or what NuSelf is continuing to think about, use `list_active_reasoning_threads` or `show_reasoning_thread` before answering unless the answer is fully present in visible context. You may suggest creating or advancing a thread, but must not create, advance, resolve, or archive one without explicit user confirmation."

### Trace Skill

The trace skill lives in `src/nuself/agent/skills/trace/SKILL.md` and must include this behavioral contract:

> "Trace is NuSelf's thought provenance database. If the user asks where an idea came from, how a memory/belief/answer formed, or what prior records support a conclusion, use `search_trace` or `show_trace` before answering unless the provenance is fully visible in the current conversation."

## Dismissed Reflection Lifecycle

1. `dismiss_reflection` calls `ReflectionRepository.dismiss(entry_id)`.
2. Entry status becomes `dismissed`.
3. `list_pending_reflections` only queries `status="pending"`, so dismissed entries disappear from the agent's view.

## Testing Strategy

- Unit test each new tool in isolation.
- Integration test: verify the agent can invoke `list_pending_reflections` and `dismiss_reflection` through the graph runtime.
- Integration test: verify the agent can invoke `list_active_reasoning_threads` and `show_reasoning_thread` through the graph runtime.
- Test edge cases: empty repository, invalid index, duplicate dismiss, empty reason repository.
