# Long-Run Reasoning Design

Status: TODO design, not implemented.

## Purpose

Long-run reasoning is a slow-thinking subsystem for staying with one explicit question over time.

It is separate from reflection:

- Reflection discovers many lightweight ideas from memory, conversations, and sources.
- Long-run reasoning maintains a small number of durable reasoning threads around questions the user wants NuSelf to keep thinking about.

The system should feel like a continuing research notebook: each step records what changed, which hypotheses are still alive, what remains uncertain, and whether the user needs to be involved.

For v0.2.0, reason is designed together with trace. Reason owns durable question state; trace owns the provenance for how each reasoning step was derived.

## Design Principles

1. **Few threads, high continuity**: long-run reasoning is for a small set of active questions, not a general inspiration feed.
2. **Durable state, not just logs**: each thread has a working summary, hypotheses, open questions, and evidence references.
3. **Incremental progress**: every advance should explain what changed since the previous step.
4. **Quiet by default**: if no meaningful progress is made, the system should stay quiet or record a minimal internal no-change step.
5. **User control**: the user can start, pause, resume, resolve, and archive threads.
6. **Separation of thinking and presentation**: internal reasoning may be exploratory; user-visible summaries should be concise and readable.
7. **No silent commitment**: NuSelf may suggest creating a long-run thread, but should not silently create one from ordinary chat.

## Domain Model

### ReasoningThread

One durable long-run question.

Core fields:

- `id`
- `question`
- `status`: `active`, `paused`, `resolved`, or `archived`
- `working_summary`
- `hypotheses`
- `open_questions`
- `evidence_refs`
- `priority`
- `last_advanced_at`
- `next_review_after`
- `created_at`
- `updated_at`

### ReasoningStep

One advance in the thread.

Core fields:

- `id`
- `thread_id`
- `kind`: `progress`, `no_change`, `question`, `synthesis`, `contradiction`, or `resolution`
- `summary`
- `delta`
- `new_hypotheses`
- `retired_hypotheses`
- `new_open_questions`
- `evidence_refs`
- `confidence`
- `created_at`

## Pipeline

```text
advance(reasoning_thread)
  ├─ load current thread state
  ├─ retrieve relevant memory, sources, chat context, reflections, and prior steps
  ├─ ReasoningWorker explores the question and proposes an update
  ├─ optional critic/persona discussion checks high-impact or uncertain updates
  ├─ ReasoningPresenter writes a concise user-readable step summary
  ├─ persist ReasoningStep
  ├─ update ReasoningThread working state
  └─ decide whether a notification is warranted
```

## Entry Points

### User-created

The user can explicitly start a thread:

```text
nuself reason start "Why do I keep getting stuck on this kind of decision?"
:reason start Why do I keep getting stuck on this kind of decision?
```

### Reflection promotion

A pending reflection can be promoted into a long-run reasoning thread:

```text
nuself reflection promote <id_or_index>
```

This is a bridge, not an automatic conversion. Reflection remains the discovery system; long-run reasoning owns sustained follow-up.

### Chat suggestion

The chat agent may suggest that a question is suitable for long-run reasoning, but must ask before creating a thread.

## CLI Shape

First implementation slice should stay manual:

```text
nuself reason list
nuself reason show <id_or_index>
nuself reason start "<question>"
nuself reason advance <id_or_index>
nuself reason pause <id_or_index>
nuself reason resume <id_or_index>
nuself reason resolve <id_or_index>
nuself reason archive <id_or_index>
```

REPL equivalents:

```text
:reason
:reason show 1
:reason start ...
:reason advance 1
```

## Chat Integration

The chat agent should eventually get tools for:

- listing active reasoning threads;
- showing a thread summary;
- starting a thread after user confirmation;
- advancing a thread when explicitly requested;
- pausing, resolving, or archiving a thread.

When the user asks about an existing long-run question, the agent should answer from `working_summary` plus recent steps instead of re-deriving from scratch.

## Notification Policy

Do not notify on every advance.

Notify only when:

- a meaningful new conclusion emerges;
- a previous hypothesis is contradicted;
- the system needs user input;
- the user marked the thread as high priority.

Notifications should link to the reasoning thread and summarize the new development briefly.

## Implementation Phases

### Phase 1: Manual Durable Threads

TODO:

- Add `ReasoningThread` and `ReasoningStep` domain models.
- Add file-backed repositories under `private/reasoning/`.
- Add CLI list/show/start/pause/resume/resolve/archive.
- Add manual `advance`.
- Add shared TUI record renderers.
- Write `ThoughtTrace` records for thread creation and non-trivial advances.

### Phase 2: Chat Tools

TODO:

- Add chat tools for active thread lookup and explicit user-approved thread creation.
- Let chat answer questions about existing reasoning threads.
- Let chat trigger manual advance when the user asks.

### Phase 3: Scheduled Advance

TODO:

- Add low-frequency scheduler with per-thread `next_review_after`.
- Keep no-change steps quiet by default.
- Gate notifications through the existing outbox.

## Open Questions

- Should `priority` be deterministic user policy only, or can the LLM suggest it with confirmation?
- Should long-run reasoning pull from all threads by default, or only linked evidence?
- How many active threads should be allowed before the system asks the user to pause one?
- Should resolved threads become memory entries, source documents, or remain only reasoning artifacts?
