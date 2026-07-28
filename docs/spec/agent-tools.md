# Chat Agent Tools Spec

## Goal

Enable the chat agent to perform user-facing actions *during conversation*, turning it from a pure Q&A interface into a conversational decision proxy. The agent can search memory, inspect pending reflections, manage memory state, and drive proactive topics—all within the natural flow of chat.

## Architecture

### LangChain Tool Boundary

Chat tools are registered as LangChain tools, following the current LangChain Python tool interface. Tool definitions must be `BaseTool` / `StructuredTool` objects, usually built from typed Python functions via `StructuredTool.from_function(...)` or an equivalent LangChain-supported decorator/factory.

NuSelf must not keep a parallel chat-tool protocol, class hierarchy, or registry. Service modules may expose normal Python APIs, but anything visible to the chat runtime must enter through the LangChain tool boundary.

Tools are **stateless callables** at the LangChain boundary. They receive structured primitive arguments and return a string result that is injected back into the conversation context.

Subagents that are visible to the chat supervisor use the same boundary. A subagent is exposed as a tool whose implementation may run an internal LangGraph or LangChain agent and then return a compact result to the supervisor.

### Chat Supervisor Boundary

The primary chat runtime is a LangChain agent:

```text
create_agent(model, tools=tools, system_prompt=..., response_format=ChatStructuredOutput)
```

LangChain owns the model/tool loop. NuSelf must not reimplement the normal
tool-calling cycle by binding tools, reading `AIMessage.tool_calls`, invoking
tools manually, and then making a separate final structured-output call. That
manual loop caused protocol leakage, duplicate turn logs, and tool/result
context drift.

NuSelf owns only the boundaries around the agent:

- prepare durable context from thread state, memory, skills, and current user input;
- construct the system prompt and message list;
- provide LangChain `BaseTool` objects;
- wrap tools for NuSelf logging and per-turn duplicate suppression;
- validate the final structured response before exposing it to the user;
- persist the updated thread state, traces, and logs.

### Shared Structured-Agent Boundary

Agent subsystems that need structured output without tools use the shared
NuSelf structured-agent runner. The runner constructs LangChain agents with
`create_agent(model=..., tools=[], response_format=ToolStrategy(schema))`,
invokes them with framework message objects, and accepts only an actual
instance of the requested schema from `structured_response`.

Strict `structured_response` extraction is one shared infrastructure
operation used by the no-tool structured runner and tool-enabled chat/reason
agents. The decoder requires a dictionary-shaped LangGraph state, a present
`structured_response` key, and an actual instance of the requested schema. It
does not validate dictionaries into models, parse message text, or apply
domain defaults.

Agent construction remains at each capability boundary when tools, system
prompts, or middleware state differ. Shared decoding must not hide tool
outcomes needed to decide whether retry or failover is safe. Domain-specific
checks, such as rejecting visible tool-call text in a chat answer, run after
the shared schema check.

The runner owns ordered configured-endpoint failover and records the successful
endpoint through the common LLM preference state. Only endpoint-availability
failures advance to the next endpoint. Missing state, dictionary-shaped
responses, wrong schema instances, and other protocol failures are surfaced
without parsing final message text or trying another response protocol.

Subsystems own their prompts and domain conversion after this boundary. They
must not wrap the runner with prompted JSON, fenced-text extraction,
`model_validate_json`, or schema-default compatibility behavior.

There is no alternate chat model or parser behind this boundary. When no
LangChain endpoint is available, chat constructs the deterministic local
response described below. Tests that need generated behavior inject the typed
service boundary rather than emulate a model protocol.

### Tool Registry

`ConversationGraphRuntime` owns a `dict[str, BaseTool]` registry. Adding a tool requires three steps:

1. Implement a small typed Python function that closes over the relevant service.
2. Wrap it as a LangChain `StructuredTool`.
3. Register it in `ConversationGraphRuntime.__init__`.

Cross-subsystem reuse does not read this registry or configured endpoints
through private runtime fields. `ConversationGraphRuntime` exposes an
immutable capability snapshot containing the endpoint tuple and only tools
tagged `readonly`. The snapshot copies collection membership at call time, so
later registry mutation cannot alter an already-issued snapshot; endpoint and
tool objects themselves are shared by identity.

Daemon reason-scheduler composition consumes this public snapshot. It must not
use `getattr` against `_tools` or `_langchain_models`, silently treat missing
private fields as empty capabilities, or repeat tag filtering outside the
conversation runtime.

The snapshot-to-scheduler-to-advancer tool pipeline is typed as LangChain
`BaseTool` throughout. Reason workspace and persona tool builders also return
`BaseTool` tuples. `ReasonAdvancer` does not accept arbitrary objects or probe
for a `metadata` attribute dynamically.

Tool log routing may read the optional `metadata["service_component"]` value.
Only a string value enters the internal tool-to-service map; missing or
non-string metadata leaves the tool valid and uses the reason default
component. Tool objects are transferred by identity.

All runtime interpretation of a framework tool's service component uses the
shared tool metadata helpers. Chat call logging, skill grouping, and reason
tool routing must not repeat direct dictionary interpretation. The shared
resolver returns only string values and never infers ownership from a tool
name; the shared index omits tools with missing or invalid metadata.

Prompt text may summarize loaded tools for models that still use NuSelf's JSON response envelope, but prompt text is not the source of truth. The registered LangChain tool objects and their schemas are the source of truth.

### Agent Skills

Every agent-facing service should be described by two prompt layers:

1. **Tool inventory**: the LangChain tools the agent can call.
2. **Service skill**: the behavioral policy for when the agent should call those tools.

Tools alone are not enough. A model may treat tools as optional buttons unless the prompt explains that a service is not ambient context. Skills tell the agent how the subsystem should participate in reasoning.

Skills are stored as flat Markdown files under `src/nuself/agent/skills/`:

```text
skills/
  memory.md
  reflection.md
  reason.md
  reason_proposal.md
  trace.md
  selves.md
```

Each skill file starts with YAML frontmatter containing `name`, `description`, and `allowed-tools`, followed by Markdown instructions. `allowed-tools` names the exact LangChain tools the skill may call. A skill may omit `allowed-tools` only when it is intentionally advisory and does not call tools.

Current chat runtime loads these Markdown files through the `load_skill` tool. Skill prose must stay file-backed rather than moving back into hard-coded prompt strings.

Rules:

- A skill may require a tool call before answering a class of questions.
- A skill may prohibit claims that would require service data unless a tool result or visible context supports them.
- A skill that calls tools must name the exact tools it depends on in `allowed-tools`.
- A skill should be reusable across ordinary response generation and persona-synthesized responses.
- Skills must not invent hidden access. If the service data is not in visible context, the agent must call the relevant tool or state uncertainty.
- Skills that can mutate state must state the confirmation boundary: direct user confirmation is required for destructive, archival, reprioritization, or proposal actions unless the corresponding tool contract explicitly says otherwise.
- Skills should distinguish raw service output from final answer behavior. Tool results are evidence or private context; the final response should synthesize them naturally unless the user asks to inspect raw records.
- Skills for durable operational state, such as reason workspaces, must describe data shape precisely enough for the agent to call tools correctly.
- Skill instructions must live in `src/nuself/agent/skills/*.md`; do not hard-code service skill prose in `chat.py`.

### Tool Invocation Flow

Chat tool invocation must follow LangChain's current tool-calling contract:

```text
create_agent(model, tools=tools, response_format=...) → LangChain-managed tool loop → structured_response
```

When agent state contains `structured_response`, that field is authoritative:
NuSelf requires an actual `ChatStructuredOutput` instance and rejects
dictionary values, malformed values, or visible tool-protocol text. It must
not silently reinterpret the final ordinary message after an authoritative
structured value fails validation; the endpoint retry/failover boundary
handles that failure.

NuSelf must not ask the model to print a private tool protocol in the assistant message body. In particular:

- no visible `[Tool call: ...]` markers;
- no NuSelf-only `"tool"` / `"tool_args"` JSON envelope as the primary path;
- no hidden parallel registry outside LangChain `BaseTool` objects.

### Tool-Safe Model Retry

Chat model retry and endpoint failover are allowed only before an agent
invocation executes its first tool. Once middleware records any successful or
failed tool outcome, the current turn must not retry the model or switch
endpoints: NuSelf cannot prove that a tool was read-only, idempotent, or
uncommitted from its visible result.

An agent failure after tool execution writes
`chat/llm_retry_suppressed_after_tool_call` and enters the existing no-tool
local response fallback. The fallback may explain failure but cannot replay
tools. Invocation-local deduplication remains useful within one LangGraph
agent run, but it is not authority to replay a completed tool in a new agent
run. Before any tool executes, the existing bounded same-endpoint retry and
endpoint failover behavior remains unchanged.

Before any tool executes, clear implementation and process-integrity failures
(`AssertionError`, `AttributeError`, `ImportError`, `LookupError`,
`MemoryError`, `NameError`, `NotImplementedError`, `RecursionError`,
`SyntaxError`, `SystemError`, and `TypeError`) are not model degradation. They
propagate unchanged without retry, endpoint failover, or local response fallback.
Protocol and structured-response validation failures remain recoverable under
the bounded retry/local-fallback policy. Once any tool outcome exists, every
ordinary invocation `Exception` suppresses retry and failover. A recoverable
failure enters the no-tool local fallback; a sharedly classified implementation
or process-integrity failure propagates unchanged after retry suppression.
Neither path replays the tool.

All agent capabilities use the shared endpoint runner. The runner may perform
a caller-configured bounded retry on the same endpoint, but only an endpoint
availability failure may advance to another configured endpoint. Chat retries
one non-availability failure once on the same endpoint. A repeated protocol or
validation failure enters the local response policy without probing another
endpoint.

Retry eligibility is evaluated after each failed invocation so middleware
state can close the retry gate. Once chat has any tool outcome, both same-
endpoint retry and endpoint switching are disabled before the runner can
invoke another agent.

### No-Model Local Response

The chat runtime has one real model protocol: LangChain endpoints and agents.
No-model behavior is a deterministic local response policy, not a second
`ChatLLM.complete()` implementation. It returns the existing configuration
guidance plus the last user message and is converted directly into
`ChatStructuredOutput`.

`nuself.llm` owns LangChain endpoint construction, endpoint preference state,
error redaction, and availability classification. It must not expose a raw
text-completion protocol, a default model selector, or a private text failover
adapter. Generated text and structured behavior belong behind the shared agent
capabilities.

Chat response services and evaluation fixtures exchange framework-native
LangChain `BaseMessage` values. NuSelf must not
define a parallel prompt-message DTO or convert framework messages through a
NuSelf-only wire shape before model invocation. Persisted `ThreadMessage`
remains a storage model and is converted to framework messages at the runtime
boundary.

`ConversationGraphRuntime` and `ConversationResponseSynthesizer` do not accept
`llm=`. Tests that need generated responses inject the typed
`ConversationResponseService`; endpoint exhaustion and tool-safe retry
suppression use the deterministic local response policy. The local policy
cannot call tools, claim model reasoning, or emit a NuSelf-only response
protocol.

### Tool Outcome Transfer

Middleware transfers tool execution state internally as one immutable
`ToolOutcome`, never as a positional tuple. The record contains tool name,
detached arguments, and exactly one of `result` or `error`. Successful and
failed outcomes therefore remain distinguishable to retry policy, audit
projection, and persisted reason-step snapshots.

Reason tool outcomes are projected even when the enclosing agent later fails.
Projection failure remains secondary, but the authoritative agent error is not
allowed to erase evidence that a tool already ran. Public tool-log snapshots
retain the existing `metadata.result` / `metadata.error` wire contract.

`ConversationGraphRuntime` runs a small LangGraph workflow with four nodes:

1. **prepare_context** — assemble durable context (memory, thread state, skills)
2. **respond** — delegate to `create_agent` with LangChain-native tool calling and structured output
3. **state_update** — persist messages and update thread state
4. **compression** — summarize when the message window grows past the trigger threshold

The `nuself.agent.chat` package composes focused collaborators rather than
implementing every node directly:

- `ConversationContextPreparer` owns durable-context retrieval and prompt-window
  message filtering for **prepare_context**.
- `ConversationStateManager` owns message-state persistence and bounded
  summarization for **state_update** and **compression**.
- Model-backed compression uses an optional shared `TextAgent` with LangChain
  system and human messages. `ConversationStateManager` does not depend on
  `ChatLLM`, construct a model, or call `complete()`.
- When no LangChain model is configured, the text capability fails, or it
  returns invalid empty text, compression uses the bounded deterministic local
  summary. This is an explicit persistence-safety policy: it preserves the
  previous summary plus the newest older transcript tail and never invents
  content.
- `ConversationPersonaOrchestrator` owns persona activation, bounded selves
  consultation, discussion escalation, and persona activity logging.
- `ConversationResponseSynthesizer` owns endpoint failover, framework-native
  tool execution, structured-output parsing, and final response acceptance.
- `ConversationToolRuntime` owns tool registration, service-skill loading,
  prompt-facing tool metadata, and service-tool call logging.

`ConversationGraphRuntime` exposes explicit node methods that delegate to these
collaborators. They are testable graph seams, not compatibility adapters. The
runtime remains responsible for graph wiring and turn-level error/trace
boundaries.

The package root is the stable public import boundary. Runtime implementation,
context preparation, state management, persona orchestration, conversation
types, and thread persistence live in separate modules beneath it.

Tool calling is delegated to `create_agent` inside the **respond** node.
Persona/selves work is not a fixed pre-response stage; it is invoked through the `selves_consult` subagent tool when the main chat agent decides it is useful.

LangChain agent execution must return `structured_response` produced through
framework-native `ToolStrategy(ChatStructuredOutput)`. Missing or invalid
structured state is a protocol failure; message content is never reparsed as a
second response protocol, and dictionary state is never revalidated into the
response model.

When no configured LangChain model exists, the runtime constructs the
deterministic local `ChatStructuredOutput` directly. It does not invoke or
parse model-shaped text. Tests or alternate composition roots that need
non-default structured fields inject `ConversationResponseService`; they must
not emulate a model by returning prompted JSON.

Within one logical chat turn, repeated tool calls with the same normalized tool name and identical arguments should reuse the first result. The runtime should still return a `ToolMessage` for every LangChain tool call id, but it should not execute or log duplicate service calls. This keeps interactive logs readable and prevents repeated status queries such as `memory_count` from looking like retries.

Duplicate identity uses the tool name plus canonical strict JSON arguments:
mapping keys must be strings, floats must be finite, and mapping key order does
not affect the key. The cache must not stringify arbitrary Python objects.
Arguments that cannot cross the JSON tool boundary bypass duplicate
suppression; middleware still delegates them to LangChain's handler so caching
does not introduce a second validation protocol or suppress execution.

The shared tool middleware owns its cache, capture sink, tool-log callback, and
tool-log failure reporter for its complete lifetime. These constructor-bound
effects are not replaced between invocations. A caller that needs different
per-invocation effects creates another middleware instance; a reused agent
must instead serialize access to any shared mutable capture state.

Middleware constructs exactly one immutable `ToolOutcome` for each executed
tool whose arguments can cross the strict JSON boundary. The same object is
passed to the tool-log callback and appended to the capture sink; logging does
not reconstruct a parallel `name/args/result/error` message. `ToolOutcome`
requires exactly one of result or error and freezes its JSON-safe argument
mapping before either consumer sees it. Non-JSON arguments still execute; an
outcome-construction failure follows the same secondary log-failure reporter
and cannot replace the tool result or exception.

Tool-log projection is a secondary observation effect:

- failure after a successful tool execution cannot replace its `ToolMessage`
  or `Command`;
- failure while reporting a tool exception cannot replace that original
  exception;
- the composition root provides a failure reporter backed by shared structured
  observability;
- if no reporter is configured, or the reporter itself fails, middleware emits
  a `RuntimeWarning` without changing the primary tool outcome;
- captured tool-error text and fallback warnings use the shared safe diagnostic
  formatter. The original tool exception is re-raised unchanged, while its
  secondary projection cannot expose credential-like values or fail because
  exception stringification is broken;
- no logging or reporting failure triggers a hidden tool retry.

Domain tool adapters also use the shared diagnostic exception formatter when
returning an expected error result to the model. A repository, validation, or
lookup error may retain its existing tool-result classification, but its local
adapter must not directly stringify the caught exception or expose
credential-like values.

Direct service-status queries, such as asking how many memory/reflection/reason/trace records exist, should call those service tools directly. These are operational tool queries; persona discussion before tool results tends to invent capability limits and adds noise.

## Tool Catalog

### Current

| Tool             | Purpose                                                               |
| ---------------- | --------------------------------------------------------------------- |
| `memory_search`  | Query durable memory, profiles, and source chunks.                    |
| `memory_count`   | Count durable memory entries with optional type/tag filters.          |
| `selves_consult` | Invoke the internal multi-persona subagent for perspective synthesis. |

Tool names must start with the owning subsystem name. This keeps agent-visible tool calls readable in logs and avoids generic names such as `search_*`, `list_*`, or `show_*` becoming ambiguous as more subsystems are exposed.

Each `StructuredTool` definition must set `metadata={"service_component": "<subsystem>"}` — e.g., `metadata={"service_component": "memory"}` for a memory tool. The `service_component` is used by the log wrapper when writing `service_tool_called` events; the renderer reads it directly from the log event's metadata. No code should derive the service tag from the tool name.

Service ownership is declared at the individual framework-tool construction
site. A registry builder must not maintain a parallel name-to-service table or
mutate tool metadata after construction. Adding or renaming a tool therefore
changes one authoritative definition rather than requiring a second catalog to
remain synchronized.

The public `nuself.agent.tools` package is a composition boundary, not a
monolithic implementation module. Memory, reflection, reason, trace, selves,
and workspace tool definitions live in subsystem-focused modules. The public
package composes those builders with persona tools and re-exports supported
entry points. Subsystem builders receive their service dependencies explicitly
and do not construct unrelated repositories or services.

Tools that emit durable operational logs, such as export flows and other long-running side effects, should include a `log` tag in addition to their behavioral tag(s) so log-oriented tooling can classify them consistently.

#### `memory_count`

- **Args**: `types: list[str] | str | None = None`, `tags: list[str] | str | None = None`
- **Behavior**: Counts memory entries from `MemoryEntryRepository.list()`, optionally filtered by memory `type` or `tags`.
- **Returns**: A simple count string like `"Memory entries: 12 total"` or `"Memory entries: 3 total (filtered by type=['goal'], tags=['runtime'])"`.
- **When to use**: When the user asks how many memories exist, wants a quick overview, or asks about specific types/tags.

#### `selves_consult`

- **Args**: `topic: str`, `mode: str = "consult"`, `context: str | None = None`
- **Behavior**: Runs the internal selves subagent in isolated context. The subagent may activate relevant personas and, when warranted, run competitive discussion. It returns compact persona notes and synthesis to the main chat supervisor.
- **Returns**: A concise internal-perspective report for the supervisor to use when composing the final user-facing answer.
- **When to use**: When the user explicitly asks for multiple perspectives, asks for NuSelf's inner discussion, faces a tradeoff, asks an architectural/design question that benefits from internal challenge, or discusses emotionally loaded/self-model topics.
- **When not to use**: Direct service status/count/search questions should call the relevant memory/reflection/reason/trace tools directly. The selves subagent should not pre-judge tool availability before tool results exist.

`selves_consult` is a synchronous subagent tool. It does not speak directly to the user. The final answer is still produced by the main chat supervisor after receiving the tool result.

### New: Reflection Consumption Tools

| Tool                      | Purpose                                                         |
| ------------------------- | --------------------------------------------------------------- |
| `reflection_list_pending` | Return pending reflection ideas from the reflection repository. |
| `reflection_count`        | Count pending reflection ideas.                                 |
| `reflection_dismiss`      | Mark a reflection idea as dismissed.                            |
| `reflection_archive`      | Archive a reflection idea after the discussion is complete.     |

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

- **Args**: `index: int` (0-based index from `reflection_list_pending` output)
- **Behavior**: Looks up the pending entry at the given index, calls `ReflectionRepository.dismiss(entry.id)`, and returns confirmation.
- **Returns**: Confirmation or error message.
- **When to use**: After the user explicitly declines interest in a suggested reflection topic.

#### `reflection_archive`

- **Args**: `index: int` (0-based index from `reflection_list_pending` output)
- **Behavior**: Looks up the pending entry at the given index, calls `ReflectionRepository.archive(entry.id)`, and returns confirmation.
- **Returns**: Confirmation with entry title, or error if not found.
- **When to use**: After the user has engaged with a reflection idea and the discussion feels complete.

### New: Memory Management Tools

| Tool                       | Purpose                                                                                                |
| -------------------------- | ------------------------------------------------------------------------------------------------------ |
| `memory_archive`           | Change a memory entry's review state to `archived`. Archived entries are excluded from default search. |
| `memory_update_importance` | Adjust the importance score (0.0-1.0) of a memory entry.                                               |

#### `memory_archive`

- **Args**: `entry_id: str`
- **Behavior**: Loads the memory entry, sets `review_state="archived"`, and saves it back.
- **Returns**: Confirmation with entry title, or error if not found.
- **Error boundary**: Only `MemoryEntryNotFound` is rendered as a missing-entry
  result. Repository, decoding, persistence, reindexing, invariant, and
  programming failures propagate to the shared tool middleware and are
  recorded as failed tool outcomes.
- **When to use**: When the user indicates a memory is outdated, no longer relevant, or should be hidden from active context.

#### `memory_update_importance`

- **Args**: `entry_id: str`, `importance: float`
- **Behavior**: Updates the entry's importance score and saves it back.
- **Returns**: Confirmation with new importance value, or error if not found.
- **Error boundary**: Only `MemoryEntryNotFound` is rendered as a missing-entry
  result. Repository, decoding, persistence, reindexing, invariant, and
  programming failures propagate to the shared tool middleware and are
  recorded as failed tool outcomes.
- **When to use**: When the user emphasizes or downplays the significance of a memory during conversation.

### New: Reason Awareness Tools (Read-Only)

| Tool                 | Purpose                                      |
| -------------------- | -------------------------------------------- |
| `reason_list_active` | Return active/paused reasoning threads.      |
| `reason_count`       | Count active/paused reasoning threads.       |
| `reason_show`        | Show details of a specific reasoning thread. |

#### `reason_list_active`

- **Args**: none
- **Behavior**: Reads `ReasonService.list_threads()` and formats active/paused threads for the LLM.
- **Returns**: Numbered list of threads with topic, status, step count, and last-advanced time. Empty message if none.
- **When to use**: The agent may call this when the user asks about "what I'm thinking about", "open topics", "reasoning threads", or when contextually relevant.

#### `reason_count`

- **Args**: none
- **Behavior**: Counts active/paused reasoning threads from `ReasonService.list_threads()`.
- **Returns**: A simple count string.
- **When to use**: When the user asks how many active reasoning threads exist.

#### `reason_show`

- **Args**: `thread_id: str`
- **Behavior**: Reads the full thread via `ReasonService.show_thread(thread_id)` including topic, description, mandates, reasoning prompt, tracked items (active, pending, next steps), evidence refs, recent steps, step output, and persisted tool logs.
- **Returns**: Formatted thread details, or error if not found.
- **When to use**: When the user asks about a specific reasoning thread in detail.

#### `reason_propose`

- **Args**: `topic: str`, `working_summary: str`, `active_items: list[dict]`, `mandates: list[str]`
- **Behavior**: Proposes a reasoning thread through the approval-decorator path. The decorated tool emits the proposal record, awaits approval, and then creates the reasoning thread.
- **Returns**: The composed tool returns a structured JSON string to chat agents. On approval it includes the original result and approver metadata, for example:

```
{"approved": true, "component": "reasoning", "approver": "<user>", "result": "<thread_id>"}
```

On cancellation it returns:

```
{"approved": false, "component": "reasoning", "result": null}
```
- **When to use**: When the user wants NuSelf to start a reason thread. The agent must provide initial tracked items and mandates, even if either list is empty. The tool wrapper handles the confirmation prompt.
- **Evidence**: The tool does not accept arbitrary `evidence_refs`; durable evidence refs must be added through explicit service paths.

### New: Trace Awareness Tools (Read-Only)

Trace tools let the chat agent inspect thought provenance without mutating it.

| Tool            | Purpose                                                              |
| --------------- | -------------------------------------------------------------------- |
| `trace_search`  | Query thought provenance records.                                    |
| `trace_count`   | Count thought provenance records matched by an optional query.       |
| `trace_show`    | Show a specific trace record with its links.                         |
| `trace_related` | List trace records and direct links for an exact artifact reference. |

#### `trace_count`

- **Args**: `query: str | None = None`
- **Behavior**: Counts default-visible trace records, optionally using the same text query as `trace_search`.
- **Returns**: A simple count string.
- **When to use**: When the user asks how many provenance records exist or how many match a topic.

#### `trace_related`

- **Args**: `artifact_ref: str`, `limit: int = 5`
- **Behavior**: Finds default-visible traces that directly mention an exact artifact reference, plus direct links whose source or target equals the artifact reference.
- **Returns**: A concise record list and related links.
- **When to use**: When the user asks what provenance exists for a specific `memory:<id>`, `reflection:<id>`, `reason:<id>`, `reason_step:<id>`, `persona_prompt:<id>`, or `trace:<id>`.

### Concrete Tool Families

The detailed tool catalog above should be read as grouped capability blocks, not a flat list of unrelated helpers:

| Family                         | Typical tools                                                                                                                                                                                     | Decorator need               |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| Read-only discovery            | `memory_search`, `memory_count`, `reflection_list_pending`, `reflection_count`, `reason_list_active`, `reason_count`, `reason_show`, `trace_search`, `trace_count`, `trace_show`, `trace_related` | `log` only                   |
| Durable mutation               | `reflection_dismiss`, `reflection_archive`, `memory_archive`, `memory_update_importance`                                                                                                          | `log` + sometimes `approval` |
| Approval-gated proposal/export | `reason_propose`, `reason_export`                                                                                                                                                                 | `log` + `approval`           |

Approval-gated tools return structured JSON that records whether the user approved the action and, if approved, the underlying result payload.
| Internal synthesis      | `selves_consult`                                                                                                                                                                                  | `log` only                   |

This grouping is the preferred order for future code organization and for any registry builder that wants to assemble tools by capability instead of by file location.

### Tool Composition Contract

Tool definitions should stay as plain Python functions first, then be assembled into `StructuredTool` instances through a small composition pipeline. The preferred order is:

1. define the underlying function
2. apply one or more decorators from the shared tool-decorator model
3. pass the composed callable into `StructuredTool.from_function(...)`

### Decorator Categories

Tool decorators are categorized by intent so the agent builder can combine them without hard-coding control flow into the graph runtime.

Standard categories:

- `log` — records `service_tool_called` and other operational audit data. It should not decide whether a tool is allowed to run.
- `approval` — gates user-confirmed or otherwise durable actions. It may return a pending result, request confirmation, or resume the original callable after approval.

Future categories may exist, such as rate limiting, metrics, caching, or tracing, but they must follow the same composable decorator contract.

The shared ordering rule is: decorators may be stacked, but the builder must keep the approval boundary around the actual side-effecting work and the log boundary around the observable tool invocation. The exact stack order is chosen by the owning subsystem, not by the agent runtime.

The logging decorator is responsible for operational audit. The approval decorator is responsible for user-confirmed state transitions. Neither decorator should live inside the agent graph itself; the agent builder chooses which decorators a tool needs, then passes the already-composed registry into the runtime.

Approval decorators are intended for tools that change durable state or trigger expensive, user-visible actions. Read-only tools should remain undecorated except for shared logging.

Logging and approval decorators accept a declared `LogComponent`, not an
arbitrary string. Composition must assign each decorated tool to an existing
domain or shared-infrastructure component; casts must not manufacture unknown
log files.

The current approval decorator is a synchronous request boundary. It owns the
wrapped callable only through normal decorator composition, prompts and decides
within the same invocation, and never places the callable or its arguments in a
process-global pending registry. Decline returns without executing the callable;
approval executes it exactly once in that invocation. A future deferred
approval flow would require a durable typed request/job contract with explicit
project, identity, expiry, and idempotency semantics; retaining arbitrary
Python callables is not such a contract.

The prompt interaction, approval decision, wrapped callable, original callable
exception, and structured approval result are primary effects. The
`approval_prompted`, `service_tool_executed`, and `service_tool_approved`
records are secondary observations and use shared best-effort observability:

- prompt rendering and stdout failures propagate unchanged rather than being
  represented as a user decline;
- stdin EOF means no affirmative approval was received and therefore follows
  the safe-default decline path;
- unexpected input failures propagate unchanged; they are not user decisions;
- every render, output, EOF, input-failure, and explicit-decline path leaves
  the wrapped callable unexecuted;

- audit persistence failure never skips the prompt, changes a decline, replaces
  an approved result, or masks the wrapped callable's exception;
- each failed audit write emits a structured degraded diagnostic containing
  the failed operation and tool name;
- if that diagnostic cannot be persisted, a `RuntimeWarning` is emitted while
  the primary approval flow continues;
- neither an audit failure nor its diagnostic triggers a prompt, callable, or
  audit retry.

Reasoning thread creation is the first migration target for this pattern. The old post-turn confirmation flow remains documented below for compatibility, but the implementation goal is to move approval into the tool composition layer so the agent lifecycle does not depend on a separate after-turn replay step.

### Behavioral Guidelines for Reason Awareness (Prompt-Level)

> "You can also read active reasoning threads—durable long-run topics the user is working through. If the user asks about their open topics, questions, or threads, summarize the active reasoning threads. You may suggest creating or advancing a thread if the conversation relates, but never call `reason_propose` until the user has explicitly confirmed they want a thread. When proposing, enrich the context with a working summary, initial tracked items, and required mandates."

### Behavioral Guidelines for Memory Curation (Prompt-Level)

> "You can also help the user curate their memory. If they say something like 'that doesn't matter anymore' or 'this is very important', you may archive the entry or adjust its importance. Always confirm the action with the user before invoking the tool."


## System Prompt Integration

Every chat response-generation prompt must include the same `Available tools` section, built from the registered LangChain tool set.

Each tool is described with:

- Name
- Argument schema
- When the agent should consider using it

Every chat response-generation prompt must list tool names and descriptions. The prompt must also state that these tools are loaded in the current NuSelf runtime. If the user asks whether memory tools are available, the agent should answer from this runtime tool list rather than from generic model limitations.

Skill behavioural instructions are NOT inlined into the system prompt. Instead, a `load_skill` tool is registered in every runtime. The agent calls `load_skill("memory")`, `load_skill("reflection")`, etc. to load a skill's full policy on-demand. This progressive-disclosure pattern follows LangChain's documented approach: tool signatures are always visible, but detailed behavioural guidelines are loaded only when the agent is about to act in that domain.

Skill files must not hard-code globally registered tool names in their instruction body. They should reference local action placeholders such as `{tool:search}`, `{tool:list_pending}`, `{tool:show}`, or `{tool:consult}`. At render time, `render_tool_placeholders(...)` replaces those placeholders with the actual tool names generated from the current tool registry, such as `memory_search`, `reflection_list_pending`, or `selves_consult`.

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

The memory skill lives in `src/nuself/agent/skills/memory.md` and must include this behavioral contract:

> "Durable memory is not ambient context. If the user asks about past preferences, decisions, recurring patterns, previous discussions, stored memories, or what NuSelf remembers, use `{tool:search}` before answering unless the answer is fully present in the current visible conversation or already provided in `Relevant memory context`. Do not say you lack memory tools when `{tool:search}` is listed. If you do not call `{tool:search}`, do not claim that no memory exists."

### Reflection Skill

The reflection skill lives in `src/nuself/agent/skills/reflection.md` and must include this behavioral contract:

> "Reflection ideas are proactive suggestions, not facts about the user. Use `{tool:list_pending}` only when the user asks for ideas/thoughts/reflections, the conversation naturally pauses, or a topic strongly matches proactive exploration. Introduce at most one idea in natural language. Use `{tool:dismiss}` when the user declines a topic, and `{tool:archive}` when the user engages and the discussion feels complete."

### Reason Skill

The reason skill lives in `src/nuself/agent/skills/reason.md` and must include this behavioral contract:

> "Reason is NuSelf's durable long-run thinking space. If the user asks about active long-running topics, open threads, or what NuSelf is continuing to think about, use `{tool:list_active}`, `{tool:count}`, or `{tool:show}` before answering unless the answer is fully present in visible context. This skill is read-only and must not call write tools."

### Reason Proposal Skill

The reason proposal skill lives in `src/nuself/agent/skills/reason_proposal.md` and must include this behavioral contract:

> "Use this skill when the user wants to start a new long-run reasoning thread. Distill the current discussion into `topic`, `working_summary`, `active_items`, and `mandates`; ask before adding mandates; call `{tool:propose}` once the user wants to start the thread. Tool approval and audit belong to the decorated tool wrapper, while the agent only assembles and invokes the already-composed tool registry."

### Trace Skill

The trace skill lives in `src/nuself/agent/skills/trace.md` and must include this behavioral contract:

> "Trace is NuSelf's thought provenance database. If the user asks where an idea came from, how a memory/belief/answer formed, or what prior records support a conclusion, use `{tool:search}` or `{tool:show}` before answering unless the provenance is fully visible in the current conversation."

## Dismissed Reflection Lifecycle

1. `reflection_dismiss` calls `ReflectionRepository.dismiss(entry_id)`.
2. Entry status becomes `dismissed`.
3. `reflection_list_pending` only queries `status="pending"`, so dismissed entries disappear from the agent's view.

## Testing Strategy

- Unit test each new tool in isolation.
- Integration test: verify the agent can invoke `reflection_list_pending` and `reflection_dismiss` through the graph runtime.
- Integration test: verify the agent can invoke `reason_list_active` and `reason_show` through the graph runtime.
- Integration test: verify the supervisor's `complete()` is used via `LangChainChatSupervisor` for LangChain-native tool calling.
- Test edge cases: empty repository, invalid index, duplicate dismiss, empty reason repository.
- Remove tests for the legacy manual tool protocol (NuSelf-owned `tool`/`tool_args` JSON envelope, `[Tool call:]` markers, `[TOOL_CALL]` blocks). Those paths are deleted.
