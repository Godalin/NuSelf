# Long-Run Reasoning Spec

Status: ready for first v0.2.0 implementation.

## Purpose

Long-run reasoning maintains durable, incremental reasoning around a small number of explicit user-approved questions.

It must not replace reflection. Reflection discovers candidate ideas; long-run reasoning sustains work on selected questions.

Reason must integrate with trace. Reason owns durable long-run question state; trace records provenance for thread creation, advances, and reflection promotion.

## Non-Goals For First Implementation

- No autonomous creation of reasoning threads from ordinary chat.
- No always-on high-frequency background thinking.
- No automatic notification for every reasoning step.
- No replacement of memory curation or reflection.

## Storage Contract

File-backed repository under:

```text
private/reasoning/threads/{thread_id}.json
private/reasoning/steps/{thread_id}/{step_id}.json
```

Machine-readable records store timezone-aware ISO timestamps. Human-readable CLI output renders timestamps in the current system timezone per `cli-interaction.md`.

Repository writes must be atomic: write to a temporary sibling file, then replace the target file.

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
- Chat may inspect active reason summaries through tools, but must not create or advance a reason thread without explicit user confirmation.

Required first service methods:

```text
list_threads(status_filter)
show_thread(id_or_index)
start_thread(question, evidence_refs=(), source_trace_ids=())
advance_thread(id_or_index)
pause_thread(id_or_index)
resume_thread(id_or_index)
resolve_thread(id_or_index)
archive_thread(id_or_index)
```

Required first tool-facing methods:

```text
list_active_reasoning_threads()
show_reasoning_thread(thread_id)
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

Manual advance only for first implementation.

```text
advance(thread)
  ├─ load thread
  ├─ reject unless status=active
  ├─ retrieve thread context (working_summary, hypotheses, open_questions, evidence_refs)
  ├─ generate a structured ReasoningStep via LLM
  ├─ update working_summary, hypotheses, open_questions, evidence_refs
  ├─ update last_advanced_at (next_review_after remains null)
  └─ persist atomically
```

Each non-`no_change` step must explain the `delta` from the prior state. A step that cannot identify meaningful movement should use `kind=no_change` and should not notify by default.

First-pass context retrieval scope: thread's own `working_summary`, `hypotheses`, `open_questions`, and `evidence_refs`. No external retrieval from memory/reflection/trace in first implementation.

## Active Thread Cap

Default cap: 5 active threads. If the user tries to start a new thread when already 5 are active, the service must reject with a message listing active threads and asking the user to pause, resolve, or archive one first.

Default priority: `normal`. The `--priority high` flag is accepted at start time but does not change cap behavior in first implementation.

## CLI Contract

Commands:

```text
nuself reason list [--status active|paused|resolved|archived|all] [--json]
nuself reason show <id_or_index> [--by-index] [--json]
nuself reason start "<question>" [--priority normal|high]
nuself reason advance <id_or_index> [--by-index]
nuself reason pause <id_or_index> [--by-index]
nuself reason resume <id_or_index> [--by-index]
nuself reason resolve <id_or_index> [--by-index]
nuself reason archive <id_or_index> [--by-index]
```

Human-readable output must use the shared record renderer style from `cli-interaction.md`.

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

`:reason` with no arguments prints reason subcommand help.

REPL output must match CLI formatting as closely as possible.

## Chat Tool Contract

Add chat tools after manual CLI support exists:

- `list_reasoning_threads`
- `show_reasoning_thread`
- `start_reasoning_thread`
- `advance_reasoning_thread`
- `pause_reasoning_thread`
- `resolve_reasoning_thread`
- `archive_reasoning_thread`

The chat agent may suggest a new reasoning thread, but must not create one without user confirmation.

## Trace Contract

Every reason thread creation and non-trivial advance writes a `ThoughtTrace`.

- Thread creation writes `kind=reason_thread`.
- Advance writes `kind=reason_step`.
- Reflection promotion writes `kind=promotion`.
- Trace outputs include the created or updated reason artifact ids.
- Reason records store trace ids for steps once implemented.

## Reflection Bridge

Add an explicit promotion command after the base repository exists:

```text
nuself reflection promote <id_or_index> [--by-index]
```

Promotion creates a reasoning thread from the reflection title/body and records the reflection id in `evidence_refs`. The original reflection must remain pending — promotion does not automatically archive or dismiss the source reflection.

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

## Decisions

- A new `reasoning` log component is used (as defined above).
- Active thread cap: 5 by default. Priority does not change the cap.
- Promotion does not archive the source reflection automatically.
- First-pass context retrieval: thread-local only (working_summary, hypotheses, open_questions, evidence_refs).
