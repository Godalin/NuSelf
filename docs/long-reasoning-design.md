# Reason Infrastructure Design

Status: evolving design; v0.2.0 has the first manual durable-thread foundation.

## Purpose

Reason is not traditional chain-of-thought, and it is not a prompt trick for producing longer explanations.

Reason is NuSelf's long-running cognitive runtime: a subsystem for managing durable reasoning processes, exploratory branches, revisions, tool use, and eventual synthesis around explicit user-approved questions.

It is separate from reflection:

- Reflection discovers many lightweight ideas from memory, conversations, and sources.
- Reason maintains durable reasoning spaces around questions the user wants NuSelf to keep thinking about.

The system should feel like a continuing research notebook and an internal thinking runtime: each step records what changed, which hypotheses are still alive, what remains uncertain, which paths failed, and whether the user needs to be involved.

For v0.2.0, reason is designed together with trace. Reason owns durable question state; trace owns the provenance for how each reasoning step was derived.

## Core Framing

Reason should be treated as infrastructure.

It manages internal cognitive state over time:

- persistent questions;
- competing hypotheses;
- branching explorations;
- reflective checks;
- tool-mediated investigation;
- uncertain or failed paths;
- user-readable summaries.

It must not be reduced to a single text chain. Text is only one presentation of an evolving internal state.

## Dynamic Reason Graph

Real reasoning is rarely linear:

```text
A -> B -> C
```

It is more often:

- multiple paths explored in parallel;
- hypotheses that compete or coexist;
- reversals and corrections;
- local reflection on unstable steps;
- long-distance links to memory, trace, tools, and prior conversations.

The long-term model for Reason is therefore a dynamic reason graph.

For v0.2.0, `ReasoningThread` and `ReasoningStep` are the first storage slice of that graph. A thread is a durable problem space. A step is an update in that space. Future versions should make branches, links, and competing hypotheses more explicit rather than forcing every development into one linear timeline.

## Design Principles

1. **Infrastructure, not CoT**: Reason manages cognitive state. It does not store or expose hidden token-level chain-of-thought.
2. **Dynamic graph, not string chain**: support branches, competing hypotheses, revisions, and failed paths over time.
3. **Few active spaces, high continuity**: active reasoning spaces should remain small enough to review and maintain.
4. **Durable state, not just logs**: each thread has a working summary, hypotheses, open questions, evidence references, and eventually branch/link state.
5. **Incremental progress**: every advance should explain what changed since the previous state.
6. **Reflective self-checks**: Reason should inspect its own outputs for contradictions, hallucination risk, instability, and premature convergence.
7. **Persistence of failures**: failed or abandoned paths can remain useful cognitive assets and should not be erased by default.
8. **Controlled creativity**: Reason may support different exploration modes, from strict analysis to speculative/fantasy-style association, while keeping uncertainty explicit.
9. **User control**: NuSelf may suggest creating or advancing a thread, but should not silently create, advance, resolve, or archive one from ordinary chat.
10. **Separation of thinking and presentation**: internal reasoning may be exploratory; user-visible summaries should be concise, readable, and non-deceptive.

## Core Capabilities

### Branching

Reason should allow multiple live directions instead of forcing early convergence.

Use cases:

- keep several hypotheses alive;
- explore practical, emotional, philosophical, or technical branches separately;
- return to a previously failed branch when new evidence appears;
- compare branches before synthesis.

The first implementation represents branches indirectly through hypotheses, open questions, and steps. A later implementation should add explicit branch records or graph links.

### Reflection

Reason should reason about its own reasoning.

Reflective checks should ask:

- Is this step grounded in evidence?
- Did it contradict another branch or prior conclusion?
- Is the conclusion too confident?
- Is this a hallucination risk?
- Should the system continue, branch, roll back, or ask the user?

This is separate from the reflection subsystem. The reflection subsystem discovers candidate ideas. Reason reflection audits and improves an active reasoning process.

### Persistence

Reasoning history is an important cognitive asset.

It should remain inspectable because it can:

- explain how a view developed;
- become context for future reasoning;
- reveal recurring user patterns;
- preserve abandoned but still useful paths;
- feed stable conclusions back into memory when appropriate.

### Isolated Workspace

Each reasoning thread should have its own isolated generic private workspace.

This workspace is the thread's private scratch environment, separate from global memory, trace, and other reasoning threads. It can hold intermediate artifacts that are useful for the ongoing task but not yet stable enough to become memory or trace.

Planned shape:

```text
private/workspaces/reason/{thread_id}/
  workspace.sqlite
  artifacts/
  notes/
```

The path uses the generic private workspace facility (`scope=reason`, `owner_id=thread_id`). `workspace.sqlite` is a per-thread SQLite database that the reasoning process may use freely for task-local state:

- branch tables;
- temporary hypotheses;
- local evidence indexes;
- tool results;
- scratch rankings;
- intermediate plans;
- failed-path records;
- structured data produced by a long task.

The database is intentionally scoped to one reasoning thread. A reason worker should not use another thread's SQLite database directly, and other subsystems should not treat it as authoritative global state. Access should go through Reason service/tool-facing methods rather than direct path manipulation.

Stable outputs leave the workspace through explicit promotion:

- important durable facts may become memory candidates;
- important process changes may become trace records;
- useful user-facing updates become reasoning steps;
- durable files may become sources only through an explicit source/memory flow.

This keeps Reason powerful enough to run complex tasks while preserving NuSelf's global data boundaries.

### Tool Use

Tools are not external add-ons. They are action capabilities inside reasoning.

Reason should be able to:

- decide when a tool is needed;
- call memory, trace, reflection, source, or future external tools through service interfaces;
- analyze tool results;
- record how the result changed the reasoning state.

Tool use inside Reason should be traceable as part of the reasoning process.

### Creative / Fantasy Mode

Reason should not be limited to strict formal logic.

Some valuable reasoning comes from analogy, incomplete inference, speculative exploration, emotion-driven association, or narrative thinking. Reason should support modes with different creativity levels, while clearly marking epistemic status and confidence.

Strict verification belongs to specialized subsystems. Reason should preserve exploratory potential without pretending that speculative steps are proven.

## Domain Model

### ReasoningThread

One durable long-run question or reasoning space.

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

Future graph-oriented fields:

- `parent_step_ids`
- `branch_id`
- `supersedes_step_ids`
- `tool_call_refs`
- `trace_ids`
- `epistemic_status`
- `mode`: e.g. `analytic`, `speculative`, `creative`, `formal`

These are not required for the first manual implementation, but the current model should evolve toward them rather than toward a single flat transcript.

## Relationship To Other Systems

### Trace

Reason produces trace records. It is not the same thing as trace.

Reason is dynamic, revisable, branching, and allowed to fail. Trace is the audit layer: it records what happened, which inputs were used, what changed, and what artifacts were produced.

Expected relation:

```text
Reason step -> ThoughtTrace(kind=reason_step)
Reason branch/synthesis -> ThoughtTrace links
Reflection promotion -> ThoughtTrace(kind=promotion)
```

### Memory

Memory provides durable background, historical context, user preferences, and concept associations.

Reason may retrieve memory and may eventually write stable results back to memory. Not every reasoning step deserves memory storage. Promotion back into memory should depend on:

- importance;
- stability;
- reusability;
- emotional weight;
- user confirmation or high confidence.

### Reflection

Reflection discovers candidate ideas. Reason sustains selected questions.

Promotion from reflection into reason should be explicit. The source reflection remains an input artifact; Reason owns the continued exploration.

### Tools

Tool calls should be modeled as part of reasoning, not as invisible side effects.

A tool result may create a new step, branch, contradiction, or evidence link. The reasoning state should preserve enough information to explain why the tool was called and how the result changed the process.

### Nusolang

Reason may eventually become one of the runtime layers for Nusolang: a higher-level cognitive workflow system where reasoning steps, tools, branching, and reflection can be expressed as executable structures.

This should remain a future direction. v0.2.0 should keep the implementation simple and file-backed.

## Pipeline

```text
advance(reasoning_thread)
  ├─ load current thread state
  ├─ retrieve relevant memory, sources, chat context, reflections, and prior steps
  ├─ ReasoningWorker explores one or more branches
  ├─ optional reflective check inspects contradictions, hallucination risk, and premature convergence
  ├─ optional critic/persona discussion checks high-impact or uncertain updates
  ├─ ReasoningPresenter writes a concise user-readable step summary
  ├─ persist ReasoningStep
  ├─ update ReasoningThread working state
  ├─ record Trace for non-trivial changes
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

Done / foundation:

- Add `ReasoningThread` and `ReasoningStep` domain models.
- Add file-backed repositories under `private/reasoning/`.
- Add CLI list/show/start/pause/resume/resolve/archive.
- Add manual `advance`.
- Add shared TUI record renderers.

Still TODO:

- Write `ThoughtTrace` records for thread creation and non-trivial advances.

### Phase 2: Chat Tools

TODO:

- Add chat tools for active thread lookup and explicit user-approved thread creation.
- Let chat answer questions about existing reasoning threads.
- Let chat trigger manual advance when the user asks.

### Phase 3: Graph-Oriented Advance

TODO:

- Replace placeholder advance with LLM-backed structured step generation.
- Add branch-aware or link-aware fields.
- Add reflective self-checks for contradiction, hallucination risk, and premature convergence.
- Preserve no-change and failed paths as inspectable artifacts.

### Phase 4: Scheduled Advance

TODO:

- Add low-frequency scheduler with per-thread `next_review_after`.
- Keep no-change steps quiet by default.
- Gate notifications through the existing outbox.

## Open Questions

- Should `priority` be deterministic user policy only, or can the LLM suggest it with confirmation?
- Should long-run reasoning pull from all threads by default, or only linked evidence?
- How many active threads should be allowed before the system asks the user to pause one?
- Should resolved threads become memory entries, source documents, or remain only reasoning artifacts?
