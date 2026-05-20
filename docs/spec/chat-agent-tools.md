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

Chat tool invocation must follow LangChain's current tool-calling contract:

```text
model.bind_tools(tools) → AIMessage.tool_calls → BaseTool.invoke(tool_call) → ToolMessage → final model response
```

NuSelf must not ask the model to print a private tool protocol in the assistant message body. In particular:

- no visible `[Tool call: ...]` markers;
- no NuSelf-only `"tool"` / `"tool_args"` JSON envelope as the primary path;
- no hidden parallel registry outside LangChain `BaseTool` objects.

`ConversationGraphRuntime` may keep its larger LangGraph workflow for NuSelf-specific stages such as context preparation, persona activation, presentation, state update, and compression. Inside the response-generation stage, tool calling is delegated to LangChain chat model tool-calling APIs.

Fallback LLMs that do not implement native tool calling may produce a plain answer, but they must not emulate tools by printing tool markers to the user.

If a non-native model still emits a recoverable tool marker such as `[Tool call: ...]` or `[TOOL_CALL] ... [/TOOL_CALL]`, the runtime should convert it into an internal tool request, normalize any legacy pre-prefix tool name to the current subsystem-prefixed name, execute the tool, and log the call through `chat/service_tool_called`. The marker must never be shown as a NuSelf reply.

Fallback tool execution must support short sequential tool loops. If a follow-up response after one tool result requests another available tool, the runtime should execute it, append the new result to the tool-result context, and ask again until the model returns a real final answer or the loop limit is reached.

Direct service-status queries, such as asking how many memory/reflection/reason/trace records exist, should skip persona activation. These are operational tool queries; persona discussion before tool results tends to invent capability limits and adds noise.

After any tool loop completes, the chat runtime must request the final answer through LangChain structured output (`with_structured_output(...)` or `create_agent(..., response_format=...)`) when the active model supports it. Prompted JSON parsing is a compatibility fallback for deterministic local test doubles and non-agent subsystems, not the primary chat-agent response protocol.

## Tool Catalog

### Current

| Tool | Purpose |
|---|---|
| `memory_search` | Query durable memory, profiles, and source chunks. |
| `memory_count` | Count durable memory entries with optional type/tag filters. |

Tool names must start with the owning subsystem name. This keeps agent-visible tool calls readable in logs and avoids generic names such as `search_*`, `list_*`, or `show_*` becoming ambiguous as more subsystems are exposed.

#### `memory_count`

- **Args**: `types: list[str] | str | None = None`, `tags: list[str] | str | None = None`
- **Behavior**: Counts memory entries from `MemoryEntryRepository.list()`, optionally filtered by memory `type` or `tags`.
- **Returns**: A simple count string like `"Memory entries: 12 total"` or `"Memory entries: 3 total (filtered by type=['goal'], tags=['runtime'])"`.
- **When to use**: When the user asks how many memories exist, wants a quick overview, or asks about specific types/tags.

### New: Reflection Consumption Tools

| Tool | Purpose |
|---|---|
| `reflection_list_pending` | Return pending reflection ideas from the reflection repository. |
| `reflection_count` | Count pending reflection ideas. |
| `reflection_dismiss` | Mark a reflection idea as dismissed. |
| `reflection_archive` | Archive a reflection idea after the discussion is complete. |

#### `reflection_list_pending`

- **Args**: `limit: int = 5`
- **Behavior**: Reads `ReflectionRepository.list(status="pending")` and formats entries for the LLM.
- **Returns**: A numbered list of pending ideas with title, type, and score. Empty message if none.
- **When to use**: The agent may call this when the conversation naturally pauses or when the user asks about "ideas", "thoughts", or "reflections".

#### `reflection_count`

- **Args**: none
- **Behavior**: Counts `ReflectionRepository.list(status="pending")`.
- **Returns**: A simple count string.
- **When to use**: When the user asks how many pending reflections or ideas exist.

#### `reflection_dismiss`

- **Args**: `index: int` (1-based index from `reflection_list_pending` output)
- **Behavior**: Looks up the pending entry at the given index, calls `ReflectionRepository.dismiss(entry.id)`, and returns confirmation.
- **Returns**: Confirmation or error message.
- **When to use**: After the user explicitly declines interest in a suggested reflection topic.

#### `reflection_archive`

- **Args**: `index: int` (1-based index from `reflection_list_pending` output)
- **Behavior**: Looks up the pending entry at the given index, calls `ReflectionRepository.archive(entry.id)`, and returns confirmation.
- **Returns**: Confirmation with entry title, or error if not found.
- **When to use**: After the user has engaged with a reflection idea and the discussion feels complete.

### New: Memory Management Tools

| Tool | Purpose |
|---|---|
| `memory_archive` | Change a memory entry's review state to `archived`. Archived entries are excluded from default search. |
| `memory_update_importance` | Adjust the importance score (0.0-1.0) of a memory entry. |

#### `memory_archive`

- **Args**: `entry_id: str`
- **Behavior**: Loads the memory entry, sets `review_state="archived"`, and saves it back.
- **Returns**: Confirmation with entry title, or error if not found.
- **When to use**: When the user indicates a memory is outdated, no longer relevant, or should be hidden from active context.

#### `memory_update_importance`

- **Args**: `entry_id: str`, `importance: float`
- **Behavior**: Updates the entry's importance score and saves it back.
- **Returns**: Confirmation with new importance value, or error if not found.
- **When to use**: When the user emphasizes or downplays the significance of a memory during conversation.

### New: Reason Awareness Tools (Read-Only)

| Tool | Purpose |
|---|---|
| `reason_list_active` | Return active/paused reasoning threads. |
| `reason_count` | Count active/paused reasoning threads. |
| `reason_show` | Show details of a specific reasoning thread. |

#### `reason_list_active`

- **Args**: none
- **Behavior**: Reads `ReasonService.list_threads(status="active")` and formats active/paused threads for the LLM.
- **Returns**: Numbered list of threads with question, status, step count, and last-advanced time. Empty message if none.
- **When to use**: The agent may call this when the user asks about "what I'm thinking about", "open questions", "reasoning threads", or when contextually relevant.

#### `reason_count`

- **Args**: none
- **Behavior**: Counts active/paused reasoning threads from `ReasonService.list_threads()`.
- **Returns**: A simple count string.
- **When to use**: When the user asks how many active reasoning threads or open long-running questions exist.

#### `reason_show`

- **Args**: `thread_id: str`
- **Behavior**: Reads the full thread via `ReasonService.show_thread(thread_id)` including hypotheses, open questions, and recent steps.
- **Returns**: Formatted thread details, or error if not found.
- **When to use**: When the user asks about a specific reasoning thread in detail.

### New: Trace Awareness Tools (Read-Only)

Trace tools let the chat agent inspect thought provenance without mutating it.

| Tool | Purpose |
|---|---|
| `trace_search` | Query thought provenance records. |
| `trace_count` | Count thought provenance records matched by an optional query. |
| `trace_show` | Show a specific trace record with its links. |

#### `trace_count`

- **Args**: `query: str | None = None`
- **Behavior**: Counts default-visible trace records, optionally using the same text query as `trace_search`.
- **Returns**: A simple count string.
- **When to use**: When the user asks how many provenance records exist or how many match a topic.

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

Skill files must not hard-code globally registered tool names in their instruction body. They should reference local action placeholders such as `{tool:search}`, `{tool:list_pending}`, or `{tool:show}`. At prompt-render time, `render_agent_skill_sections(...)` replaces those placeholders with the actual tool names generated from the current tool registry, such as `memory_search` or `reflection_list_pending`.

Example additions:

```
- reflection_list_pending(limit: int = 5): View pending proactive ideas.
  Use when the user seems open to exploring new connections or questions,
  or when the conversation naturally pauses.
- reflection_dismiss(index: int): Remove an idea from the active pool.
  Use when the user explicitly says they are not interested in a topic.
- reason_list_active(): View active reasoning threads.
  Use when the user asks about open questions or what they are
  thinking about.
- reason_show(thread_id: str): Show details of a specific
  reasoning thread. Use when the user asks about a particular thread.
```

## Behavioral Guidelines (Prompt-Level)

The system prompt should include:

> "You have access to pending reflection ideas—proactive questions and connections generated from the user's memory and conversations. If the user seems curious or the conversation naturally touches on related topics, you may introduce one idea in your own words. Do not dump the raw list. If the user shows no interest, dismiss it. If the user engages, the conversation itself will naturally capture the outcome into memory."

### Memory Skill

The memory skill lives in `src/nuself/agent/skills/memory/SKILL.md` and must include this behavioral contract:

> "Durable memory is not ambient context. If the user asks about past preferences, decisions, recurring patterns, previous discussions, stored memories, or what NuSelf remembers, use `{tool:search}` before answering unless the answer is fully present in the current visible conversation or already provided in `Relevant memory context`. Do not say you lack memory tools when `{tool:search}` is listed. If you do not call `{tool:search}`, do not claim that no memory exists."

### Reflection Skill

The reflection skill lives in `src/nuself/agent/skills/reflection/SKILL.md` and must include this behavioral contract:

> "Reflection ideas are proactive suggestions, not facts about the user. Use `{tool:list_pending}` only when the user asks for ideas/thoughts/reflections, the conversation naturally pauses, or a topic strongly matches proactive exploration. Introduce at most one idea in natural language. Use `{tool:dismiss}` when the user declines a topic, and `{tool:archive}` when the user engages and the discussion feels complete."

### Reason Skill

The reason skill lives in `src/nuself/agent/skills/reason/SKILL.md` and must include this behavioral contract:

> "Reason is NuSelf's durable long-run thinking space. If the user asks about active long-running questions, open threads, or what NuSelf is continuing to think about, use `{tool:list_active}` or `{tool:show}` before answering unless the answer is fully present in visible context. You may suggest creating or advancing a thread, but must not create, advance, resolve, or archive one without explicit user confirmation."

### Trace Skill

The trace skill lives in `src/nuself/agent/skills/trace/SKILL.md` and must include this behavioral contract:

> "Trace is NuSelf's thought provenance database. If the user asks where an idea came from, how a memory/belief/answer formed, or what prior records support a conclusion, use `{tool:search}` or `{tool:show}` before answering unless the provenance is fully visible in the current conversation."

## Dismissed Reflection Lifecycle

1. `reflection_dismiss` calls `ReflectionRepository.dismiss(entry_id)`.
2. Entry status becomes `dismissed`.
3. `reflection_list_pending` only queries `status="pending"`, so dismissed entries disappear from the agent's view.

## Testing Strategy

- Unit test each new tool in isolation.
- Integration test: verify the agent can invoke `reflection_list_pending` and `reflection_dismiss` through the graph runtime.
- Integration test: verify the agent can invoke `reason_list_active` and `reason_show` through the graph runtime.
- Test edge cases: empty repository, invalid index, duplicate dismiss, empty reason repository.
