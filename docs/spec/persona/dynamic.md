# Dynamic Persona Prompt Spec

Status: implemented current contract.

## Purpose

Dynamic persona prompts are custom thinking personas authored during conversation
and stored in a private repo. Unlike built-in static personas (`analyst_self`,
`skeptic_self`, …) which are hardcoded with fixed `id` + `description`, dynamic
personas are free-form prompt fragments that any subsystem (chat, reason,
reflection) can **call as tools**.

For the static persona system, see [static.md](static.md).
For competitive persona discussion, see [discussion.md](discussion.md).

## Core Principle

Dynamic personas are not injected into system prompts. They are **called as tools**.

```
persona_list()        → discover available personas
persona_think(persona, question) → load prompt, call LLM, return answer
```

This follows the same consumption pattern as skills (`load_skill`). The persona
prompt is loaded, used as LLM context for one call, and the result is returned
to the calling agent. The caller (reason advancer, chat supervisor,
`selves_consult`) decides when and whether to invoke a persona.

## Storage — Private Repo

```
private/
  persona_prompts/
    <id>.json           # one file per prompt
    name_index.json     # {name: id} lookup
```

### PersonaPrompt Model

```python
@dataclass(frozen=True)
class PersonaPrompt:
    id: str             # uuid4 hex
    name: str           # human-readable label (max 40 chars, alphanumeric + hyphens)
    prompt: str         # the prompt text
    created_at: str     # ISO timestamp
    updated_at: str     # ISO timestamp
```

### PersonaPromptRepository

```python
class PersonaPromptRepository:
    def save(self, prompt: PersonaPrompt) -> None: ...
    def get(self, prompt_id: str) -> PersonaPrompt | None: ...
    def get_by_name(self, name: str) -> PersonaPrompt | None: ...
    def list(self) -> tuple[PersonaPrompt, ...]: ...
    def delete(self, prompt_id: str) -> None: ...
    def resolve(self, name_or_id: str) -> PersonaPrompt | None: ...
```

- `save()` writes `<id>.json` and updates `name_index.json`.
- `resolve()` tries id first, then name lookup.
- All writes are atomic (write a unique temp file, rename).
- Writes for the same local process are serialized per repository root, so
  concurrent tool calls cannot race on `name_index.json` or leave stale temp
  file state.
- Deletion removes both the file and the index entry.

## Trace Recording

When a persona prompt is created via `persona_craft`, a `persona_prompt_created`
trace is recorded. The trace includes `prompt_id` and `name` but not the full
prompt text.

## Chat Tool

### `persona_craft`

```text
persona_craft(name: str, prompt: str) -> str
```

Creates or updates a thinking persona with the given name and prompt.

- If a persona with the same name already exists, **updates** the prompt and
  `updated_at` timestamp.
- Returns the persona prompt id on success.
- Writes a `persona_prompt_created` trace.

**Agent documentation:**

> `persona_craft(name, prompt)`: Create or update a reusable thinking persona.
> Use this when a specific thinking style or domain expertise would help — for
> example, a "systems-architect" that focuses on tradeoffs, or a
> "socratic-tutor" that questions assumptions. Other tools like
> `persona_list` and `persona_think` can then discover and invoke
> this persona.

## Persona Tools

Two tools registered in the shared tool pool (available to chat agent and reason
advancer):

### `persona_list`

```text
persona_list() -> str
```

Returns a formatted list of available persona prompts with id, name, and
created_at. Returns empty message if none exist.

### `persona_think`

```text
persona_think(persona: str, question: str) -> str
```

Loads the persona prompt identified by `persona` (name or id), calls the LLM
with the prompt as system message and `question` as user message, and returns
the response.

- If `persona` is not found, returns an error message.
- The underlying LLM call uses the same model as the calling agent.
- The tool call is visible in the caller's log and trace (via existing
  `service_tool_called` mechanism).

## Subsystem Integration

### Reason

The reason advancer's tool set includes `persona_list` and
`persona_think`. During a reasoning step, the advancer may choose to consult
a persona — for example, when a topic benefits from a specific thinking
style. The `persona_think` call appears in the step's `tool_logs` snapshots
and is rendered identically to other tool calls in step display and logs.

Example reasoning step trace:

```
persona_think persona=rust-expert question=How should we handle...
  → "Given Rust's ownership model, the safest approach is to use an Arc..."
[step: progress] persona_think gave a strong architectural direction
```

No `persona_prompt_id` field on ReasoningThread. No `--persona` flag on
`reason start`. The advancer uses the tools when it decides they are needed.

### Chat Agent

The chat agent's tool set also includes `persona_list` and
`persona_think`. This allows the user or agent to consult a persona during
conversation without starting a reason thread.

Example:

```
user: ask rust-expert about this code
agent: → persona_think("rust-expert", "review this: fn foo(...)")
agent: the persona suggests using non_null instead...
```

### `selves_consult`

The `selves_consult` subagent can call `persona_list` to discover
available dynamic personas and include them alongside static personas. Since
`selves_consult` runs as a tool with its own LLM context, it has full access
to the persona tool set.

Selection flow:

1. `selves_consult` detects the user's request is relevant to known personas
2. Calls `persona_list()` to check available dynamic personas
3. For each relevant persona, calls `persona_think(name, question)` to get
   its perspective
4. Includes the response alongside static persona contributions in synthesis

### Reflection

The reflection scheduler's discussion path (via
`SharedPersonaDiscussionService`) does **not** use `persona_think` in V1.
Reflection's competitive discussion uses only static built-in personas.
Post-V1, the moderator could optionally discover and invite dynamic personas.

## Persona CLI

```text
nuself persona list
nuself persona show <name_or_id>
nuself persona delete <name_or_id>
```

- `list` prints all prompts with id, name, created_at.
- `show` prints the full prompt text.
- `delete` removes the prompt file and index entry.

## Origin Rule

| Created by | Storage | Available to |
|---|---|---|
| Chat tool `persona_craft` | `private/persona_prompts/` | Reason, Chat, selves_consult (via tools) |
| Reason internal | Thread workspace | Only that thread |

## Non-Goals For V1

- No system-prompt injection. Personas are consumed via tools, not injected.
- No `persona_prompt_id` on ReasoningThread.
- No `--persona` flag on `reason start` or `reason advance`.
- No reflection competitive discussion integration.
- No global Reason-internal prompt creation. Thread-scoped persona prompts and scratch state belong in the reason workspace.
- No persona chaining or composition.

## Post-V1

### Tool-Enabled Personas

Allow `persona_craft` to optionally specify a list of tools the persona may
invoke during `persona_think`. When tools are attached, `persona_think` runs
as a lightweight agent loop instead of a single LLM call.

```text
persona_craft("researcher",
  prompt="You are a researcher. Gather evidence and form a hypothesis.",
  tools=["memory_search", "source_read", "reflection_list_pending"]
)
```

**Open design questions (deferred):**

1. **Tool scope** — Which tools are available to persona agents? A curated
   read-only subset (memory, source, reflection) or full access including
   mutation?
2. **Execution model** — `persona_think` is currently synchronous. If the
   persona runs multiple tool rounds, the caller (chat supervisor, reason
   advancer) may block for many LLM turns. Need timeout or streaming.
3. **Nesting** — A persona agent that can call `persona_think` is recursive.
   Need a depth limit or explicit guard.
4. **Result packaging** — The caller needs the persona's conclusion, not its
   intermediate tool call logs. The tool result should summarize, not dump.
5. **Permission inheritance** — Does a persona inherit the caller's tool
   permissions? Or does `persona_craft` define a fixed scope at creation time?
