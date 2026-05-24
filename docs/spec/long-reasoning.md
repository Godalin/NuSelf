# Long-Run Reasoning Spec

Status: updated — chat-based thread initiation + turn-confirmation protocol (v2).

## Purpose

Long-run reasoning maintains durable, incremental reasoning around a small number of explicit user-approved questions.

Reason is infrastructure, not chain-of-thought. It manages persistent cognitive state and must not expose or rely on hidden token-level reasoning transcripts.

It must not replace reflection. Reflection discovers candidate ideas; long-run reasoning sustains work on selected questions.

Reason must integrate with trace. Reason owns durable long-run question state; trace records provenance for thread creation, advances, and reflection promotion.

## Conceptual Model

The long-term target is a dynamic reason graph:

- threads are durable reasoning spaces;
- steps are state updates inside those spaces;
- hypotheses and open questions are live graph state;
- future branches and links may represent competing paths, revisions, tool calls, and failed explorations.

The first v0.2.0 implementation stores this as `ReasoningThread` plus ordered `ReasoningStep` records. This is an implementation slice of the graph model, not a claim that reasoning is linear.

Reason steps may be exploratory, uncertain, speculative, or failed. Such steps can be useful cognitive assets. User-facing presentation must summarize them without pretending they are proven conclusions.

## Non-Goals For First Implementation

- No always-on high-frequency background thinking.
- No automatic notification for every reasoning step.
- No replacement of memory curation or reflection.
- No raw hidden model chain-of-thought storage.
- No explicit branch graph schema in the first storage slice.

## Chat-Based Reasoning Initiation

### Motivation

CLI-only thread creation (`:reason start "question"`) is too primitive for complex
reasoning tasks. Before starting a long-run thread, the user and NuSelf should be
able to discuss the topic, explore different angles, gather relevant context from
memory/reflection, and enrich the initial question with hypotheses, open questions,
and evidence — all within a normal chat conversation.

Only after the idea is well-formed should a reasoning thread be created, carrying
the enriched context as its initial state.

### Flow

```
1. User and NuSelf discuss a topic during normal chat.
2. NuSelf identifies the topic has depth and would benefit from long-run reasoning.
3. NuSelf proposes a draft question and invites the user to refine it.
4. Optional back-and-forth: NuSelf uses existing reason/reflection/memory/trace tools
   to gather context, proposes hypotheses, and refines the question together with the user.
5. When the idea is mature, NuSelf calls reason_propose(...) with the enriched context.
   This tool does NOT create the thread — it validates the proposal, writes a
   "reason_proposal_created" log event, and returns a PENDING signal.
6. The chat turn completes normally. The CLI (not the agent) detects the pending
   proposal via the log event and prompts the user:
   [reason] 开启推理线程「question」? (y/n):
7. User types "y". The CLI calls ReasonService.start_thread() with the enriched
   context. Thread is created. A confirmation line is printed:
   [reason] 推理线程已创建: <id>
8. If the user types "n", the proposal is discarded silently.
9. Normal chat loop resumes with the next NuSelf> prompt.
```

### Role Of The Agent

The chat agent is the actor. The system prompt must instruct the agent to:

1. **Identify depth** — when a user's topic has multiple dimensions, unresolved
   tensions, or would benefit from durable incremental reasoning, proactively
   suggest creating a reasoning thread.
2. **Co-enrich** — help the user refine the question, propose hypotheses, surface
   open questions, and reference relevant memory or reflection entries.
3. **Confirm** — do NOT call `reason_start` until the user has explicitly confirmed.
   Confirmation may be as simple as "yes, start it" or "go ahead".
4. **Create with context** — when confirmed, call `reason_start` with the full
   enriched context: the spoken/settled question as `question`, a concise
   `working_summary` of the discussion's key insights, any `hypotheses` that
   emerged, and `evidence_refs` pointing to memory/reflection entries discussed.

### Proposal Tool: `reason_propose`

The `reason_propose` tool does NOT create the thread. It validates the
proposal and writes a `reason_proposal_created` log event that the CLI
will detect. The tool returns a PENDING signal string such as:

```
PENDING:reason-proposal:{id}
```

The agent must never call this tool speculatively. See the
[Turn-Confirmation Protocol](##turn-confirmation-protocol) for how the
CLI handles pending proposals.

### Tool Signature

```python
def reason_propose(
    question: str,
    working_summary: str = "",
    hypotheses: list[str] = [],
    evidence_refs: list[str] = [],
) -> str:
```

- `question` (required) — finalised, user-approved question.
- `working_summary` (optional) — enriched context from the discussion.
- `hypotheses` (optional) — initial hypotheses that emerged.
- `evidence_refs` (optional) — references to memory, reflection, trace records.

### Role Of The Agent

The chat agent is the actor. The system prompt must instruct the agent to:

1. **Identify depth** — when a user's topic has multiple dimensions, unresolved
   tensions, or would benefit from durable incremental reasoning, proactively
   suggest creating a reasoning thread.
2. **Co-enrich** — help the user refine the question, propose hypotheses, surface
   open questions, and reference relevant memory or reflection entries.
3. **Confirm before propose** — do NOT call `reason_propose` until the user has
   explicitly said something like "yes, start it", "go ahead", "create the thread".
4. **Propose with context** — when confirmed, call `reason_propose` with the full
   enriched context.

### Active Thread Cap Interaction

If the active thread cap (default 5) is already reached when the agent calls
`reason_propose`, the tool must reject with an error listing active threads.
The agent should relay this to the user and suggest pausing or resolving one
before retrying. No pending proposal is created.

### Trace Contract

Thread creation after user confirmation must record the same `reason_thread`
trace as `ReasonService.start_thread()`. The trace must include the enriched
context (working_summary, hypotheses, evidence_refs) in its metadata.

## Turn-Confirmation Protocol

A shared architecture layer for any subsystem to ask the user a
yes/no question in the chat flow without blocking the agent.

### Domain Events vs Operational Logs

This protocol uses the existing log system as a **domain event bus**,
not as operational logging:

- **Domain events** (`proposal_created`, `candidate_created`) carry
  structured payloads that CLI code consumes to drive interactive
  behavior. They are written by domain logic (tools, curators) and
  read by the CLI after each chat turn.
- **Operational logs** (`turn_completed`, `service_tool_called`) record
  what happened for display and debugging. They are a read-only
  record and must never drive control flow.

The log file (`private/logs/reasoning.log`) is the transport medium:
the producer writes an event entry, the consumer reads it after the
turn. It is NOT an audit trail — confirmed proposals are consumed
immediately and should not be replayed.

Future subsystems (memory curator, reflection promoter, etc.) can
plug into this protocol by writing their own `proposal_created` event
with a unique component name, then adding a handler in
`_handle_proposals_after_turn`.

### Lifecycle

```
producer (tool/curator)                     consumer (CLI)
        │                                        │
        │  write_log_event(component,             │
        │    "proposal_created",                  │
        │    metadata={...})                      │
        ├─────────────────────────────────────────►
        │                                        │
        │  return "PENDING:{ns}:{id}"            │
        │                                        │
        │                              turn finishes
        │                              reply printed
        │                              _handle_proposals_after_turn()
        │                                        │
        │                              print "[tag] 确认? (y/n):"
        │                              readline()
        │                                        │
        │                              if y/yes: execute action
        │                              if n/no:  discard silently
        │                                        │
        │                              resume normal chat loop
```

### Event Schema

```python
write_log_event(
    component,              # e.g. "reasoning", "memory"
    "proposal_created",     # fixed event name for all proposals
    f"{description}",       # human-readable one-liner
    project_root=...,
    metadata={
        "proposal_id": str,     # unique id from producer
        # ... subsystem-specific fields ...
    },
)
```

### CLI Contract

After each chat turn, the CLI calls `_handle_proposals_after_turn`
which scans for `proposal_created` events and dispatches to the
appropriate handler:

```python
def _handle_proposals_after_turn(events, project_root):
    # 1. Check in-band events from the turn (one-shot mode)
    for event in events:
        handler = _PROPOSAL_HANDLERS.get((event.component, event.event))
        if handler:
            handler(event, project_root)
            return
    # 2. Also scan the shared log (daemon mode — turn_ids differ)
    for event in reversed(read_log_events(tail=50)):
        handler = _PROPOSAL_HANDLERS.get((event.component, event.event))
        if handler:
            handler(event, project_root)
            return
```

A dispatch registry maps (component, event) to handlers:

```python
_PROPOSAL_HANDLERS: dict[tuple[str, str], Callable] = {
    ("reasoning", "proposal_created"): _confirm_reason_proposal,
    # ("memory",    "proposal_created"): _confirm_memory_candidate,  # future
}
```

Each handler follows the same pattern:

```python
def _confirm_reason_proposal(event, project_root):
    meta = event.metadata
    print()  # blank line before prompt
    print(f"[tag] 确认内容「{meta['question']}」? (y/n): ", end="", flush=True)
    line = sys.stdin.readline().strip().lower()
    if line in ("y", "yes"):
        # materialise: call domain service with meta fields
        ...
    # else: discard silently
```

### Daemon Mode

In daemon mode the proposal event is written on the daemon side but
the log files are shared (`private/logs/` under the same project root).
The CLI reads the daemon's events from the shared log in step 2 above.
The daemon never blocks for user input — prompting is always the
CLI's responsibility.

### One-Shot Mode

One-shot chat (`nuseful chat --message "..."`) does not enter the
interactive loop. Proposal events are silently ignored because there
is no context to prompt in.

### Extending To Memory (Future)

When the memory curator creates a medium-confidence candidate,
instead of adding it quietly to the candidate queue, it writes a
`proposal_created` event with `component="memory"`. The CLI handler
detects it and asks the user to confirm the memory entry immediately.

High-confidence memories bypass the protocol (auto-create).
Low-confidence proposals stay in the queue for offline review.

```text
private/reasoning/threads/{thread_id}.json
private/reasoning/steps/{thread_id}/{step_id}.json
```

Machine-readable records store timezone-aware ISO timestamps. Human-readable CLI output renders timestamps in the current system timezone per `cli-interaction.md`.

Repository writes must be atomic: write to a temporary sibling file, then replace the target file.

### Per-Thread Workspace Contract

Each reasoning thread owns an isolated generic private workspace:

```text
private/workspaces/reason/{thread_id}/
```

The workspace is task-local storage for the reasoning process. It follows `private-workspace.md`. It is not global memory, not trace, and not a shared cross-thread database.

Rules:

- Workspace ids must match reason thread ids.
- A reason worker may read and write only the workspace for the thread it is advancing.
- Other subsystems may access workspace contents only through Reason service/tool-facing methods.
- Workspace storage must not be used to bypass Memory, Trace, or Source promotion rules.
- Deleting or archiving a thread must not silently delete its workspace in the first implementation; cleanup should be explicit.

The first workspace storage mechanism is the generic per-owner SQLite database:

```text
workspace.sqlite
```

The SQLite database may store arbitrary task-local structured state, including branch records, temporary hypotheses, local evidence indexes, tool results, scratch rankings, intermediate plans, and failed-path records.

Stable data leaves the workspace only through explicit promotion:

- reason steps for user-readable reasoning updates;
- trace records for provenance;
- memory candidates or source ingestion for durable reusable knowledge.

## Service And Tool-Facing Interface

Reason is a subsystem service. It should not be implemented as CLI code that directly edits files.

Layers:

- `ReasoningThread` / `ReasoningStep`: domain models and validation.
- `ReasonRepository`: file-backed persistence for threads and steps.
- `ReasonService`: user-intent operations and state transitions.
- Reason renderers: human-readable CLI/REPL output.
- Tool-facing adapter: explicit, typed operations suitable for chat and future agents.

Rules:

- CLI and REPL commands call `ReasonService`.
- Chat tools call the tool-facing adapter, which delegates to `ReasonService`.
- Reason writes trace records through `TraceRecorder`; it must not write trace files directly.
- Reason reads memory/reflection/trace through service interfaces, not private file paths.
- Reason treats tool use as part of reasoning. Tool calls and tool results should become evidence refs, step metadata, or trace links when they materially change the reasoning state.
- Chat may inspect active reason summaries through tools, but must not create or advance a reason thread without explicit user confirmation.

Required first service methods:

```text
list_threads(status_filter)
show_thread(id_or_index)
start_thread(question, working_summary="", evidence_refs=(), source_trace_ids=())
advance_thread(id_or_index)
pause_thread(id_or_index)
resume_thread(id_or_index)
resolve_thread(id_or_index)
archive_thread(id_or_index)
promote_reflection(entry_id_or_index)
```

Required first tool-facing methods:

```text
reason_list_active()
reason_count()
reason_show(thread_id)
start_reasoning_thread_after_confirmation(question)
advance_reasoning_thread_after_confirmation(thread_id)
```

## ReasoningThread

Typed domain model:

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Stable thread id (uuid4 hex) |
| `question` | string | User-approved long-run question |
| `status` | string | `active`, `paused`, `resolved`, or `archived` |
| `working_summary` | string | Current compact state of the reasoning |
| `hypotheses` | list[string] | Current live hypotheses |
| `open_questions` | list[string] | Subquestions still unresolved |
| `evidence_refs` | list[string] | Memory, source, thread, reflection, or step refs |
| `priority` | string | `normal` or `high` |
| `last_advanced_at` | string \| null | Last successful advance timestamp |
| `skip_next_advance_until` | string \| null | ISO timestamp; background scheduler skips this thread until this time |
| `next_review_after` | string \| null | Earliest scheduler review time (null for first impl) |
| `created_at` | string | Creation timestamp |
| `updated_at` | string | Last state update timestamp |

## ReasoningStep

Typed domain model:

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Stable step id (uuid4 hex) |
| `thread_id` | string | Parent reasoning thread |
| `kind` | string | `progress`, `no_change`, `question`, `synthesis`, `contradiction`, or `resolution` |
| `summary` | string | User-readable step summary |
| `delta` | string | What changed since the previous step |
| `new_hypotheses` | list[string] | Added hypotheses |
| `retired_hypotheses` | list[string] | Retired hypotheses |
| `new_open_questions` | list[string] | Added subquestions |
| `tool_calls` | list[string] \| null | Tool invocations during this step, stored as `name(args)` strings for display |
| `evidence_refs` | list[string] | Evidence used by this step |
| `confidence` | float \| null | Optional confidence estimate |
| `created_at` | string | Step timestamp |

## State Transitions

| From | Action | To |
|---|---|---|
| none | `start` | `active` |
| `active` | `pause` | `paused` |
| `paused` | `resume` | `active` |
| `active`, `paused` | `resolve` | `resolved` |
| `active`, `paused`, `resolved` | `archive` | `archived` |

Archived threads are hidden from default list output but remain addressable by id.

## Advance Contract

The implementation provides two advance paths:

### Manual Advance

```text
advance(thread)
  ├─ load thread
  ├─ reject unless status=active
  ├─ retrieve thread context (working_summary, hypotheses, open_questions, evidence_refs)
  ├─ create a deterministic placeholder ReasoningStep with kind=progress
  ├─ update last_advanced_at
  └─ persist atomically
```

### LLM-Backed Advance (ReasonAdvancer)

When an explicit `step` is provided to `advance_thread`, the service uses it instead of creating a placeholder. The LLM-backed step is generated by `ReasonAdvancer`, which:

- Takes the thread's `question`, `working_summary`, `hypotheses`, `open_questions`, and `evidence_refs` as context.
- Calls `ChatLLM.complete()` with a system prompt requesting a structured JSON reasoning step.
- Validates the response has required fields (`summary`, `delta`, `kind`) and a valid `kind`.
- Returns a `ReasoningStep` with parsed fields, or `None` if the LLM response is empty or unparseable.
- Supports `kind` values: `progress`, `no_change`, `question`, `synthesis`, `contradiction`, `resolution`.
- Integrates `new_hypotheses`, `new_open_questions`, and `evidence_refs` from the step into the updated thread state.

### Background Scheduler (ReasonScheduler)

The daemon runs a `ReasonScheduler` background thread that periodically advances eligible threads:

```text
run_once()
  ├─ list all threads
  ├─ filter to active status (active, paused)
  ├─ skip any thread whose skip_next_advance_until is in the future
  ├─ select the first eligible thread
  ├─ call ReasonAdvancer.advance(thread)
  ├─ if step returned, call ReasonService.advance_thread(id, step=step)
  ├─ set skip_next_advance_until to now + interval_seconds
  └─ log the advance result
```

Config:

- `daemon.reason_scheduler.interval_seconds` (default: 600) controls the check interval and per-thread cooldown.
- The scheduler thread is daemonized and follows the same pattern as `memory_curator` and `reflection_scheduler`.
- The scheduler is only active when the daemon is running; it has no CLI-or REPL-triggered execution path.

### Step Content Rules

Each non-`no_change` step must explain the `delta` from the prior state. A step that cannot identify meaningful movement should use `kind=no_change` and should not notify by default.

First-pass context retrieval scope: thread's own `working_summary`, `hypotheses`, `open_questions`, and `evidence_refs`. No external retrieval from memory/reflection/trace in first implementation.

### Graph-Oriented Advance Contract

LLM-backed advance must preserve the graph nature of reasoning:

- it may add, retire, or revise hypotheses without forcing a final answer;
- it may identify contradictions and create `kind=contradiction` steps;
- it may create `kind=question` steps when user input is needed;
- it may preserve failed paths as no-change or contradiction steps when they remain informative;
- it must mark speculative or creative movement clearly through summary, confidence, and future epistemic fields;
- it must not collapse multiple plausible branches into one premature conclusion.

Reason reflection is internal to the reason process. It audits existing reasoning state for contradictions, hallucination risk, weak evidence, or premature convergence. This differs from the reflection subsystem, which discovers new candidate topics.

## Active Thread Cap

Default cap: 5 active threads. If the user tries to start a new thread when already 5 are active, the service must reject with a message listing active threads and asking the user to pause, resolve, or archive one first.

Default priority: `normal`. The `--priority high` flag is accepted at start time but does not change cap behavior in first implementation.

## CLI Contract

Commands:

```text
nuself reason list [--status active|paused|resolved|archived|all] [--json]
nuself reason show <id_or_index> [--by-index] [--full] [--json]
nuself reason start "<question>" [--priority normal|high]
nuself reason advance <id_or_index> [--by-index]
nuself reason pause <id_or_index> [--by-index]
nuself reason resume <id_or_index> [--by-index]
nuself reason resolve <id_or_index> [--by-index]
nuself reason archive <id_or_index> [--by-index]
```

Human-readable output must use the shared record renderer style from `cli-interaction.md`.

`--full` on `reason show` renders each step with all fields (step id, index, delta, tool calls, hypotheses, open questions, evidence refs, confidence) even when empty, showing `(no ...)` placeholders instead of omitting the section.

Default list output shows active and paused threads. `--status all` includes resolved and archived threads.

## REPL Contract

Interactive commands:

```text
:reason
:reason list
:reason show <id_or_index>
:reason start <question>
:reason advance <id_or_index>
:reason pause <id_or_index>
:reason resume <id_or_index>
:reason resolve <id_or_index>
:reason archive <id_or_index>
```

`:reason` with no arguments prints reason subcommand help. `:reason show` supports `--full` to show all step fields.

REPL output must match CLI formatting as closely as possible.

## Chat Tool Contract

The following tools are registered for the chat agent. Read-only tools are
available to inspect reasoning state; write tools require explicit user
confirmation and include the reasoning thread's enriched conversation context.

### Read-Only Tools

- `reason_list_active` — list active/paused threads.
- `reason_count` — count active/paused threads.
- `reason_show` — show a thread's current state and steps.

### Write Tool: `reason_propose`

Proposes a reasoning thread for user confirmation. Does NOT create the thread.
Validates the proposal, writes a `reason_proposal_created` log event, and
returns a PENDING signal. See the Turn-Confirmation Protocol for how the
CLI handles the pending proposal.

Tool function:

```python
def reason_propose(
    question: str,
    working_summary: str = "",
    hypotheses: list[str] = [],
    evidence_refs: list[str] = [],
) -> str:
```

Parameters:

- `question` (required) — the core long-run question the thread will explore.
  Must be finalised and user-approved before calling this tool.
- `working_summary` (optional) — enriched summary from the chat discussion:
  key insights, contextual background, what has already been considered.
- `hypotheses` (optional) — initial hypotheses that emerged during the
  conversation.
- `evidence_refs` (optional) — references to memory, reflection, trace, or
  other records that were surfaced during the discussion.

Returns a string in the format `"PENDING:reason-proposal:{proposal_id}"`.

The agent must NOT call `reason_propose` until the user has given explicit
verbal confirmation (said "yes, start it", "go ahead", "create the thread",
or equivalent).

### Write Tool: `reason_advance`

(Reserved for future implementation — not yet registered as a chat tool.)

### Write Tool: `reason_pause`, `reason_resolve`, `reason_archive`

(Not yet registered as chat tools. These remain CLI/REPL-only for now.)

### Confirmation Rule

The chat agent may suggest, discuss, and enrich a reasoning thread topic,
but must NOT call `reason_propose` until the user has given explicit verbal
confirmation. The system prompt must include this hard rule:

> "You may propose and refine a reasoning thread idea with the user. You
> may surface context from memory, reflection, and existing threads. But
> you MUST NOT call `reason_propose` until the user has explicitly said
> something like 'yes, start it', 'go ahead', 'create the thread', or
> equivalent clear confirmation. A user's agreement that a topic is
> 'interesting' or 'worth exploring' does not count as confirmation."

### System Prompt Skill

The chat prompt must include the following Reason skill:

> "Reason is NuSelf's durable long-run thinking space. If the user asks
> about active long-running questions, what NuSelf is still thinking about,
> or the state of a specific reasoning thread, use reason tools before
> answering unless the answer is fully present in visible context. When a
> discussion reveals a topic with real depth, you should suggest creating
> a reasoning thread. Help the user refine the question, add hypotheses
> and open questions from your discussion, and only call `reason_propose`
> after the user explicitly confirms."

## Trace Contract

Every reason thread creation and non-trivial advance writes a `ThoughtTrace`.

- Thread creation writes `kind=reason_thread`. When created via the chat tool
  `reason_start`, the trace must include the enriched context
  (`working_summary`, `hypotheses`, `evidence_refs`) in its metadata.
- Advance writes `kind=reason_step`.
- Reflection promotion writes `kind=promotion`.
- Trace outputs include the created or updated reason artifact ids.
- Reason service owns this recording through `TraceRecorder`. CLI, REPL, and future tools must not write trace files directly.
- If trace recording fails, the user-visible reason operation should fail in the first implementation rather than silently creating untraceable long-run state. Best-effort trace writes are reserved for chat turns.

Trace is the audit layer for Reason. Reason may be dynamic, revisable, branching, and allowed to fail; Trace records what happened and why a state changed. Reason must not treat trace as its mutable working memory.

## Reflection Bridge

Add an explicit promotion command after the base repository exists:

```text
nuself inbox reflection promote <id_or_index> [--by-index]
```

Promotion creates a reasoning thread from the reflection title/body and records the reflection id in `evidence_refs`. The original reflection must remain pending — promotion does not automatically archive or dismiss the source reflection.

The promotion flow writes two trace records:

- the normal `reason_thread` trace from `ReasonService.start_thread`;
- a `promotion` trace linking `reflection:<entry_id>` to `reason:<thread_id>`.

## Notification Policy

Integrate with notification outbox only after manual advance is stable.

Notify only when a step is user-worthy:

- `kind=progress` with a meaningful new conclusion;
- `kind=contradiction`;
- `kind=question` when user input is needed;
- high-priority thread update.

No-change steps must not notify by default.

## Logging

Add a `reasoning` log component.

Expected events:

| Event | Status | Meaning |
|---|---|---|
| `thread_started` | `created` | New reasoning thread created |
| `thread_status_changed` | `updated` | Pause, resume, resolve, or archive |
| `advance_started` | `started` | Advance began |
| `advance_completed` | `completed` | Step persisted |
| `advance_no_change` | `skipped` | No meaningful update |
| `advance_failed` | `failed` | Advance failed safely |

### Tool Call Display Via Log System

All user-visible tool call output must go through the existing log system and its
`render_log_event` pipeline, not through ad-hoc inline formatting.

The `ReasonAdvancer` must emit `service_tool_called` log events for every tool
invoked during step generation, using the same `write_log_event` convention as
`chat.py:_write_service_tool_log`. The `service_tool_called` event is shared
between chat and reasoning so that tool call presentation is identical in both
contexts — the same `render_log_event` path renders them identically.

The `tool_calls` field on `ReasoningStep` is a denormalized display cache
populated from the agent message history after each advance. It is rendered in
step display with the same format as `render_log_event`: a header line
`[reasoning] [<service>] service_tool_called  [completed]` followed by an
indented body line showing the tool call arguments, with proper coloring on the
component and service tags.

Rules:
- The advancer's `_advance_with_tools` path must call `write_log_event`
  with component=`reasoning`, event=`service_tool_called` for each tool invocation.
- The step renderer (`_render_step_body`) must render `tool_calls` entries
  with the same header+body format as `render_log_event`, with colored component
  and service tags.
- Tool calls from the `_advance_raw` fallback path (no LangChain tools) may be
  omitted from log output — there are no tool invocations to log.

## Decisions

- A new `reasoning` log component is used (as defined above).
- Active thread cap: 5 by default. Priority does not change the cap.
- Promotion does not archive the source reflection automatically.
- First-pass context retrieval: thread-local only (working_summary, hypotheses, open_questions, evidence_refs).
- Reason is infrastructure for cognitive state evolution, not a stored chain-of-thought transcript.
- The current thread/step model is the first implementation slice of a future dynamic reason graph.
- All user-visible tool call display goes through the `service_tool_called` log event + `render_log_event` pipeline, not ad-hoc inline formatting.
- `tool_calls` on `ReasoningStep` is a denormalized cache populated from agent message history, rendered via the log pipeline.
