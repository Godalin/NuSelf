# Long-Run Reasoning Spec

Status: CURRENT — general-purpose tracked items with chat tools and `topic` field.

## Purpose

Long-run reasoning maintains durable, incremental reasoning around a small number of explicit user-approved topics.

Reason is infrastructure, not chain-of-thought. It manages persistent cognitive state and must not expose or rely on hidden token-level reasoning transcripts.

It must not replace reflection. Reflection discovers candidate ideas; long-run reasoning sustains work on selected topics.

Reason must integrate with trace. Reason owns durable long-run topic state; trace records provenance for thread creation, advances, and reflection promotion.

## Conceptual Model

The long-term target is a dynamic reason graph:

- threads are durable reasoning spaces;
- steps are state updates inside those spaces;
- tracked items (active, pending, next steps) are live graph state, with
  free-text `kind` tags that adapt to the task (character, suspect,
  hypothesis, plot_thread, ...);
- future branches and links may represent competing paths, revisions, tool calls, and failed explorations.
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

CLI-only thread creation (`:reason start "<topic>"`) is too primitive for complex
reasoning tasks. Before starting a long-run thread, the user and NuSelf should be
able to discuss the topic, explore different angles, gather relevant context from
memory/reflection, and enrich the initial topic with tracked items (each with
free-text kind tags) and evidence — all within a normal chat conversation.

Only after the idea is well-formed should a reasoning thread be created, carrying
the enriched context as its initial state.

### Flow

```
1. User and NuSelf discuss a topic during normal chat.
2. NuSelf identifies the topic has depth and would benefit from long-run reasoning.
3. NuSelf proposes a draft topic and invites the user to refine it.
4. Optional back-and-forth: NuSelf uses existing reason/reflection/memory/trace tools
   to gather context, proposes initial tracked items (each with a free-text `kind` tag
   such as "character", "suspect", "hypothesis", "plot_thread"), and refines the topic
   together with the user.
5. When the idea is mature, NuSelf calls reason_propose(...) with the enriched context.
   This tool does NOT create the thread — it validates the proposal, writes a
   "reason_proposal_created" log event, and returns a PENDING signal.
6. The chat turn completes normally. The CLI (not the agent) detects the pending
   proposal via the log event and prompts the user:
   [reason] 开启推理线程「topic」? (y/n):
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
2. **Co-enrich** — help the user refine the topic, surface initial tracked items
   (with appropriate kind tags), and reference relevant memory or reflection entries.
3. **Confirm before propose** — do NOT call `reason_propose` until the user has
   explicitly confirmed. Confirmation may be as simple as "yes, start it" or "go ahead".
4. **Propose with context** — when confirmed, call `reason_propose` with the full
   enriched context: the spoken/settled topic as `topic`, a concise
   `working_summary` of the discussion's key insights, initial `active_items`
   (each with label, optional description, and free-text kind tag), and
   `evidence_refs` pointing to memory/reflection entries discussed.

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
    topic: str,
    working_summary: str = "",
    evidence_refs: list[str] = [],
    active_items: list[dict] = [],
) -> str:
```

- `topic` (required) — finalised, user-approved topic.
- `working_summary` (optional) — enriched context from the discussion.
- `evidence_refs` (optional) — references to memory, reflection, trace records.
- `active_items` (optional) — initial tracked items, each with `"label"` (required),
  `"description"` (optional), `"kind"` (optional free-text tag that adapts to
  the task — e.g. `"hypothesis"`, `"character"`, `"suspect"`, `"plot_thread"`).

### Role Of The Agent

The chat agent is the actor. The system prompt must instruct the agent to:

1. **Identify depth** — when a user's topic has multiple dimensions, unresolved
   tensions, or would benefit from durable incremental reasoning, proactively
   suggest creating a reasoning thread.
2. **Co-enrich** — help the user refine the topic, surface initial tracked items
   (with appropriate kind tags), and reference relevant memory or reflection entries.
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
context (`topic`, `working_summary`, `active_items`) in its metadata.

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
        "proposal_id": str,     # unique id — MUST be unique per proposal so
                                # the CLI can deduplicate stale log entries
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
    print(f"[tag] 确认内容「{meta['topic']}」? (y/n): ", end="", flush=True)
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

Machine-readable records store timezone-aware ISO timestamps. Human-readable CLI output renders timestamps in the current system timezone per `cli.md`.

Repository writes must be atomic: write to a temporary sibling file, then replace the target file.

### Per-Thread Workspace Contract

Each reasoning thread owns an isolated generic private workspace:

```text
private/workspaces/reason/{thread_id}/
```

The workspace is task-local storage for the reasoning process. It follows `workspace.md`. It is not global memory, not trace, and not a shared cross-thread database.

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
start_thread(topic, working_summary="", evidence_refs=(), source_trace_ids=())
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
start_reasoning_thread_after_confirmation(topic)
advance_reasoning_thread_after_confirmation(thread_id)
```

## ReasoningThread

Typed domain model:

| Field                     | Type           | Meaning                                                               |
| ------------------------- | -------------- | --------------------------------------------------------------------- |
| `id`                      | string         | Stable thread id (uuid4 hex)                                          |
| `topic`                   | string         | User-approved long-run topic                                          |
| `status`                  | string         | `active`, `paused`, `resolved`, or `archived`                         |
| `working_summary`         | string         | Current compact state of the reasoning                                |
| `active_items_data`       | list[dict]     | General-purpose tracked items (see `TrackedItem`)                     |
| `pending_items_data`      | list[dict]     | Items still unresolved                                                |
| `next_steps_data`         | list[dict]     | Planned actions for the next advance                                  |
| `evidence_refs`           | list[string]   | Memory, source, thread, reflection, or step refs                      |
| `priority`                | string         | `normal` or `high`                                                    |
| `last_advanced_at`        | string \| null | Last successful advance timestamp                                     |
| `skip_next_advance_until` | string \| null | ISO timestamp; background scheduler skips this thread until this time |
| `next_review_after`       | string \| null | Earliest scheduler review time (null for first impl)                  |
| `created_at`              | string         | Creation timestamp                                                    |
| `updated_at`              | string         | Last state update timestamp                                           |

### TrackedItem

General-purpose tracked item with free-text kind tag:

| Field         | Type   | Meaning                                   |
| ------------- | ------ | ----------------------------------------- |
| `label`       | string | Short name (required)                     |
| `description` | string | Optional detail                           |
| `kind`        | string | Free-text tag — LLM chooses based on task |
| `status`      | string | `"active"` by default                     |

The `kind` field is the extension point. Different tasks use different kinds
without any code change:

| Task             | Example kind values                                        |
| ---------------- | ---------------------------------------------------------- |
| Storytelling     | `"character"`, `"plot_thread"`, `"conflict"`, `"location"` |
| Investigation    | `"suspect"`, `"evidence"`, `"timeline"`, `"alibi"`         |
| World simulation | `"world_rule"`, `"faction"`, `"region"`, `"event"`         |
| Science          | `"hypothesis"`, `"theory"`, `"experiment"`, `"prediction"` |

Properties on `ReasoningThread`:

- `active_items` — returns `[TrackedItem]` from `active_items_data`, falling
  back to legacy `hypotheses` (list of strings → kind `"item"`).
- `pending_items` — returns `[TrackedItem]` from `pending_items_data`, falling
  back to legacy `open_questions`.
- `next_steps` — returns `[TrackedItem]` from `next_steps_data`.

Legacy fields `hypotheses` and `open_questions` are still written to disk for
backward compat but are no longer the primary storage for new threads.

## ReasoningStep

Typed domain model:

| Field                   | Type                 | Meaning                                                                                        |
| ----------------------- | -------------------- | ---------------------------------------------------------------------------------------------- |
| `id`                    | string               | Stable step id (uuid4 hex)                                                                     |
| `thread_id`             | string               | Parent reasoning thread                                                                        |
| `kind`                  | string               | `progress`, `no_change`, `question`, `synthesis`, `contradiction`, `resolution`, or `planning` |
| `summary`               | string               | User-readable step summary                                                                     |
| `delta`                 | string               | What changed since the previous step                                                           |
| `new_hypotheses`        | list[string]         | Legacy — added strings (now replaced by `new_findings_data`)                                   |
| `retired_hypotheses`    | list[string]         | Legacy — retired strings (now replaced by `retired_findings_data`)                             |
| `new_open_questions`    | list[string]         | Legacy — added questions (now replaced by `new_pending_data`)                                  |
| `new_findings_data`     | list[dict]           | Items to add to `active_items` (TrackedItem wire format)                                       |
| `new_pending_data`      | list[dict]           | Items to add to `pending_items`                                                                |
| `retired_findings_data` | list[dict]           | Items to remove from `active_items` (matched by label)                                         |
| `next_steps_data`       | list[dict]           | Items to add to `next_steps`                                                                   |
| `evidence_refs`         | list[string]         | Evidence used by this step                                                                     |
| `tool_calls`            | list[string] \| null | Tool invocations during this step                                                              |
| `confidence`            | float \| null        | Optional confidence estimate                                                                   |
| `created_at`            | string               | Step timestamp                                                                                 |

Properties on `ReasoningStep`:

- `new_findings` — returns `[TrackedItem]` from `new_findings_data`, falling
  back to legacy `new_hypotheses` (list of strings → kind `"finding"`).
- `new_pending` — returns `[TrackedItem]` from `new_pending_data`, falling
  back to legacy `new_open_questions`.
- `retired_findings` — returns `[TrackedItem]` from `retired_findings_data`,
  falling back to legacy `retired_hypotheses`.
- `next_steps` — returns `[TrackedItem]` from `next_steps_data`.
| `new_open_questions` | list[string] | Added subquestions |
| `tool_calls` | list[string] \| null | Tool invocations during this step, stored as `name(args)` strings for display |
| `evidence_refs` | list[string] | Evidence used by this step |
| `confidence` | float \| null | Optional confidence estimate |
| `created_at` | string | Step timestamp |

## State Transitions

| From                           | Action    | To         |
| ------------------------------ | --------- | ---------- |
| none                           | `start`   | `active`   |
| `active`                       | `pause`   | `paused`   |
| `paused`                       | `resume`  | `active`   |
| `active`, `paused`             | `resolve` | `resolved` |
| `active`, `paused`, `resolved` | `archive` | `archived` |

Archived threads are hidden from default list output but remain addressable by id.

## Advance Contract

The implementation provides two advance paths:

### Manual Advance

```text
advance(thread)
  ├─ load thread
  ├─ reject unless status=active
  ├─ retrieve thread context (working_summary, active_items, pending_items, next_steps, evidence_refs)
  ├─ create a deterministic placeholder ReasoningStep with kind=progress
  ├─ update last_advanced_at
  └─ persist atomically
```

### LLM-Backed Advance (ReasonAdvancer)

When an explicit `step` is provided to `advance_thread`, the service uses it instead of creating a placeholder. The LLM-backed step is generated by `ReasonAdvancer`, which:

- Takes the thread's `topic`, `working_summary`, `active_items`, `pending_items`, `next_steps`, and `evidence_refs` as context.
- Calls `ChatLLM.complete()` with a system prompt requesting a structured JSON reasoning step.
- Validates the response has required fields (`summary`, `delta`, `kind`) and a valid `kind`.
- Returns a `ReasoningStep` with parsed fields, or `None` if the LLM response is empty or unparseable.
- Supports `kind` values: `progress`, `no_change`, `question`, `synthesis`, `contradiction`, `resolution`, `planning`.
- Integrates `new_findings`, `new_pending`, `retired_findings`, and `evidence_refs` from the step into the updated thread state.

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

First-pass context retrieval scope: thread's own `working_summary`, `active_items`, `pending_items`, and `evidence_refs`. No external retrieval from memory/reflection/trace in first implementation.

### Graph-Oriented Advance Contract

LLM-backed advance must preserve the graph nature of reasoning:

- it may add, retire, or revise tracked items without forcing a final answer;
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
nuself reason start "<topic>" [--priority normal|high]
nuself reason advance <id_or_index> [--by-index]
nuself reason pause <id_or_index> [--by-index]
nuself reason resume <id_or_index> [--by-index]
nuself reason resolve <id_or_index> [--by-index]
nuself reason archive <id_or_index> [--by-index]
nuself reason delete <id_or_index> [--by-index]
nuself reason watch [--interval <seconds>]
```

Human-readable output must use the shared record renderer style from `cli.md`.

### Thread Header Format

Both `reason show` and `reason watch` begin by printing the thread's global
context. The header consists of:

1. **Header line**: `[reason] <topic>` followed by inline metadata fields
   (`id`, `status`, `priority`, `created_at`, `last_advanced_at`).
2. **Description section**: labeled `description:`, shows the thread's
   `working_summary` as bulleted markdown-rendered text.
3. **Active items section**: `active_items:`, each rendered as
   `label — description (kind)`.
4. **Pending items section**: `pending_items:`, same format as active.
5. **Next steps section**: `next_steps:`, each rendered as `label`.
6. **Evidence refs section**: `evidence_refs:`, each rendered as markdown.

After the thread header, `reason show` appends each step's body (see
`_render_step_body`). `reason watch` prints existing steps followed by
a polling loop for new steps.

`--full` on `reason show` renders each step with all fields (step id, index, delta, tool calls, findings, pending, evidence refs, confidence) even when empty, showing `(no ...)` placeholders instead of omitting the section.

Default list output shows active and paused threads. `--status all` includes resolved and archived threads.

### `delete` Behavior

`reason delete <id>` permanently removes a thread and all its data:

- Thread file (`private/reasoning/threads/{id}.json`)
- Steps directory (`private/reasoning/steps/{id}/`)
- Workspace (`private/workspaces/reason/{id}/`)
- A `thread_deleted` log event is written before deletion.

The `--yes` flag is required to confirm. Without it, the command prints
"Use --yes to confirm deletion." and exits with code 1.

This operation is irreversible. For reversible hiding, use `archive` instead.

### `watch` Behavior

`reason watch` enters a blocking loop that polls for new reasoning steps:

1. On start, prints each thread's full [Thread Header Format](#thread-header-format)
   followed by all existing steps.
2. Then polls for new steps every N seconds (default 5 for CLI, 2 for
   interactive).
3. Each new step is printed as it arrives via `render_step_watch_entry`
   (same format as a single step in `reason show --full`).
4. Press Ctrl+C to stop.

The loop runs in the foreground. It is not a daemon background process.

## REPL Contract

`:reason` with no arguments prints reason subcommand help. `:reason show` supports `--full` to show all step fields.

`:reason delete` and `:reason watch` have the same behavior as their
CLI counterparts (`reason delete`, `reason watch`), except that
`:reason delete` does not require the `--yes` flag (interactive context
already implies intent) and `:reason watch` uses a 2-second default
poll interval instead of 5.

Interactive commands:

```text
:reason
:reason list
:reason show <id_or_index>
:reason start <topic>
:reason advance <id_or_index>
:reason pause <id_or_index>
:reason resume <id_or_index>
:reason resolve <id_or_index>
:reason archive <id_or_index>
:reason delete <id_or_index>
:reason watch
```

`:reason` with no arguments prints reason subcommand help. `:reason show` supports `--full` to show all step fields.

REPL output must match CLI formatting as closely as possible.

## Chat Tool Contract

Reason tools let the chat agent inspect, propose, and manage reasoning threads.
Tools that create a thread (propose) use the turn-confirmation protocol; tools
that change a thread's status act directly after the agent reports the action.

### Read-Only Tools

| Tool                     | Description                                                                  |
| ------------------------ | ---------------------------------------------------------------------------- |
| `reason_list_active()`   | List active and paused threads with step counts.                             |
| `reason_count()`         | Return count of active and paused threads.                                   |
| `reason_show(thread_id)` | Show a thread's topic, description, tracked items, evidence refs, and steps. |

No user confirmation is needed for read-only tools.

### Write Tool (Turn-Confirmation): `reason_propose`

Proposes a reasoning thread for user confirmation. Does NOT create the thread.
Validates the proposal, writes a `reason_proposal_created` log event, and
returns a PENDING signal. See the Turn-Confirmation Protocol for how the
CLI handles the pending proposal.

```python
def reason_propose(
    topic: str,
    working_summary: str = "",
    evidence_refs: list[str] = [],
    active_items: list[dict] = [],
) -> str:
```

Parameters:

- `topic` (required) — finalised, user-approved topic for the thread.
- `working_summary` (optional) — enriched context from the discussion.
- `evidence_refs` (optional) — references to memory, reflection, trace records.
- `active_items` (optional) — initial tracked items, each with `"label"` (required),
  `"description"` (optional), `"kind"` (optional free-text tag that adapts to
  the task — e.g. `"hypothesis"`, `"character"`, `"suspect"`, `"plot_thread"`).

Returns `"PENDING:reason-proposal:{proposal_id}"`.

The agent must NOT call `reason_propose` until the user has given explicit
verbal confirmation. See also [Confirmation Rule](#confirmation-rule-1).

### Write Tools (Direct): State Transitions

The agent may pause, resume, resolve, or archive a thread directly. The agent
should tell the user what it intends to do before calling the tool so the user
can object before the turn ends.

| Tool                        | Effect                                                        |
| --------------------------- | ------------------------------------------------------------- |
| `reason_pause(thread_id)`   | Pause an active thread.                                       |
| `reason_resume(thread_id)`  | Resume a paused thread back to active.                        |
| `reason_resolve(thread_id)` | Mark a thread as resolved (answered/concluded).               |
| `reason_archive(thread_id)` | Archive a thread (hidden from list, still addressable by id). |

Each returns a one-line confirmation string.

These tools do NOT use the turn-confirmation protocol. The normal chat flow
(agent says what it will do, user agrees, agent calls tool in the same turn)
is sufficient. If the user disagrees, the agent aborts before calling the tool.

### Write Tool (Reserved): `reason_advance`

(Reserved for future implementation — not yet registered as a chat tool.
The background scheduler handles automatic advances; manual advance from
chat would require the turn-confirmation protocol because it invokes an
LLM and may change state unpredictably.)

### Confirmation Rule

The chat agent may suggest, discuss, and enrich a reasoning thread topic,
but must NOT call `reason_propose` until the user has given explicit verbal
confirmation. The system prompt must include this hard rule:

> "You may propose and refine a reasoning thread idea with the user. You
> may surface context from memory, reflection, and existing threads. But
> you MUST NOT call `reason_propose` until the user has explicitly said
> something like 'yes, start it', 'go ahead', 'create the thread', or
> equivalent clear confirmation. A user's agreement that a topic is
> 'interesting' or 'worth exploring' does not count as confirmation.
> For state changes (pause, resume, resolve, archive), tell the user
> what you intend first and let them respond before calling the tool."

### System Prompt Skill

The chat prompt must include the following Reason skill:

> "Reason is NuSelf's durable long-run thinking space. If the user asks
> about active long-running topics, what NuSelf is still thinking about,
> or the state of a specific reasoning thread, use reason tools before
> answering unless the answer is fully present in visible context. When a
> discussion reveals a topic with real depth, you should suggest creating
> a reasoning thread. Help the user refine the topic and add initial
> tracked items with appropriate kind tags, and only call `reason_propose`
> after the user explicitly confirms. For state changes (pause, resume,
> resolve, archive), explain what you're doing and call the tool directly."

## Trace Contract

Every reason thread creation and non-trivial advance writes a `ThoughtTrace`.

- Thread creation writes `kind=reason_thread`. When created via `reason_propose`
  + user confirmation, the trace must include the enriched context
  (`topic`, `working_summary`, `active_items`, `evidence_refs`) in its metadata.
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

| Event                   | Status      | Meaning                            |
| ----------------------- | ----------- | ---------------------------------- |
| `thread_started`        | `created`   | New reasoning thread created       |
| `thread_status_changed` | `updated`   | Pause, resume, resolve, or archive |
| `advance_started`       | `started`   | Advance began                      |
| `advance_completed`     | `completed` | Step persisted                     |
| `advance_no_change`     | `skipped`   | No meaningful update               |
| `advance_failed`        | `failed`    | Advance failed safely              |

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
- First-pass context retrieval: thread-local only (working_summary, active_items, pending_items, next_steps, evidence_refs).
- Reason is infrastructure for cognitive state evolution, not a stored chain-of-thought transcript.
- The current thread/step model is the first implementation slice of a future dynamic reason graph.
- All user-visible tool call display goes through the `service_tool_called` log event + `render_log_event` pipeline, not ad-hoc inline formatting.
- `tool_calls` on `ReasoningStep` is a denormalized cache populated from agent message history, rendered via the log pipeline.
