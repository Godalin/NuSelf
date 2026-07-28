# Reason Output Composition Spec

Status: implemented current contract.

## Purpose

Reason output composition turns an ordered reason thread into a user-facing long-form artifact such as a story, report, outline, or summary.

This subsystem is reason-scoped in the first version. It consumes reason state and produces finished output, but it does not replace reason itself.

The chat runtime may orchestrate the job, but it must not be required to hold the full long-form output in prompt context.

## Scope

The first implementation:

- uses `ReasoningThread` and `ReasoningStep` as its source of truth
- writes job state and intermediate artifacts into the owning reason workspace
- supports chat-driven, resumable, chunked composition
- produces Markdown output in the initial version

The first implementation does not require trace as an input. Trace may be added later as an optional provenance layer, but it is not part of the initial contract.

## Non-Goals

- This spec does not alter the reason thread or reason step schema.
- This spec does not define a general unrestricted filesystem API.
- This spec does not make chat transcripts the source of truth for long-form output.
- This spec does not define a trace-backed provenance export path in the first version.
- This spec does not require the composed output to be stored inside the chat thread.

## Domain Model

### Source

A source is an ordered stream of items that can be composed into a finished artifact.

For the first version, valid source types are:

- `reason_thread`
- `reason_step`

### Item

An item is the smallest unit consumed by the composer.

For reason output, an item is typically one reason step and should expose:

- a stable id
- an order index
- a short summary
- the full step body or observable output
- optional evidence references
- optional kind or type metadata

### Section planner ownership

`ReasonOutputService` receives an optional section planner through its
constructor. The planner is instance-scoped and is used only by that service's
`plan_job()` calls.

- Chat/daemon composition passes the daemon's configured LLM planner through
  the conversation runtime and reason-export tool factory.
- CLI, tests, and callers that do not inject a planner use the deterministic
  `plan_sections()` fallback.
- No module-level setter or mutable process-global planner is allowed.
- Constructing or starting one daemon/runtime must not alter planner behavior
  in another project or service instance.

### Segment

A segment is a batch of ordered items processed together.

Segments are the unit of incremental work for the export worker.

### Chunk

A chunk is an intermediate composed artifact produced from one segment.

Chunks are persisted so the job can resume without recomputing finished work.

### Manifest

A manifest is the control record for one export job.

It must record:

- job id
- source thread id
- selected step range or cursor
- output mode
- output format
- segment size
- completed chunk inventory
- section plan derived from source content and reused across chunks
- resume state
- creation and update timestamps

## Storage Contract

### Two storage domains

Export state lives in two places with different persistence semantics:

- **Job data** — per-thread, persistent in the owning reason workspace (`private/workspaces/reason/{thread_id}/artifacts/export/jobs/{job_id}/`)
- **Queue signal** — daemon-global, in-memory (`queue.SimpleQueue` on the daemon process)

The queue is in-memory because the manifest is the real persistent state. A queue event is just a "go check the manifest" signal. The daemon worker is a single process-global event loop that reads from `SimpleQueue` and processes jobs by looking up their manifests.

### Job data layout (per-thread)

```text
private/workspaces/reason/{thread_id}/
  workspace.sqlite
  artifacts/
    export/
      jobs/
        {job_id}/
          manifest.json
          progress.json
          chunk-001.md
          chunk-002.md
          combined.md
          combined.pdf
```

Rules:

- The workspace is thread-local.
- Export data must not be stored in transcript storage.
- Export data must not be written into another thread's workspace.
- Each export job has a deterministic `job_id` derived from its parameters. The job's data lives under `jobs/{job_id}/`, not in the root `export/` directory. This allows multiple export ranges or settings to coexist without destructive collision: re-planning with different parameters does not touch other jobs' directories.
- The manifest is the resumable source of truth for the export job.
- The manifest stores a deterministic section plan derived from the selected source steps, not from chunk boundaries, so each chunk can reuse the same chapter or section names, focus, and ordering context across the full export.
- Repeated calls with the same selected source range and export settings are idempotent: they produce the same `job_id`, reuse the same `jobs/{job_id}` directory, and skip re-enqueueing if the job is already pending or complete.
- **All persistent data must use typed domain models.** Raw `dict` manipulation (accessing `dict[str, object]` directly, setting fields via string keys) is prohibited for manifest and progress data. Only `dataclasses.replace()` and `to_wire()`/`from_wire()` are permitted for state mutations.

### Manifest schema

The manifest is a typed dataclass (`ReasonOutputManifest`) persisted as JSON via `to_wire()` / `from_wire()`:

```json
{
    "schema": "NuSelfReasonOutput/v1",
    "job_id": "reason-output-{sha256}",
    "thread_id": "reason-...",
    "mode": "narrative",
    "output_format": "markdown",
    "source_start_index": 0,
    "source_end_index": null,
    "source_step_ids": ["step-id-1", "step-id-2"],
    "segment_size": 5,
    "status": "planned",
    "combined_filename": "combined.md",
    "progress_filename": "progress.json",
    "created_at": "2026-01-01T00:00:00.000000+00:00",
    "updated_at": "2026-01-01T00:00:00.000000+00:00",
    "sections": [...],
    "chunks": [...],
    "attempts": 0,
    "last_error": null,
    "last_attempt_at": null
}
```

- `attempts` — number of failed compose attempts (persisted across daemon restarts to prevent infinite retry cycles).
- `last_error` — error message from the most recent failed compose attempt, or `null`.
- `last_attempt_at` — ISO timestamp of the most recent failed compose attempt, or `null`.
- All field mutations go through `dataclasses.replace()` which enforces type checking at the model level. Direct dict mutation of the manifest file is prohibited.

### Progress schema

Progress is a typed dataclass (`ReasonOutputProgress`) persisted as JSON:

```json
{
    "job_id": "reason-output-{sha256}",
    "thread_id": "reason-...",
    "status": "complete",
    "completed_chunks": [0, 1],
    "total_chunks": 2,
    "pdf_status": "generated",
    "pdf_path": "combined.pdf",
    "updated_at": "2026-01-01T00:00:00.000000+00:00"
}
```

Progress is a read-friendly summary of the manifest state. The manifest is always the authoritative source of truth.

### Recovery read contract

- `ReasonOutputManifest.from_wire()` strictly requires the complete version-1
  manifest shape written by `to_wire()`, including the exact
  `NuSelfReasonOutput/v1` schema marker. Missing, unknown, wrongly typed, or
  unsupported-version fields are corrupt state; the decoder never fills
  persisted control fields from current defaults.
- `ReasonOutputService.list_jobs()` treats each job directory as an independent
  record. A missing, malformed, non-object, schema-invalid, or identity-mismatched
  manifest emits one payload-safe `reasoning/record_decode_failed` diagnostic
  and is omitted while healthy neighboring jobs remain visible.
- `ReasonOutputService.get_job()` is a direct authoritative lookup. A missing
  manifest raises `ReasonNotFound`; corrupt content or identity mismatch raises
  a decode error. Non-missing filesystem failures such as permission errors
  propagate from both list and direct lookup and are never converted into an
  empty result or not-found response.
- Startup reconciliation and dequeue processing decode `manifest.json` through
  `ReasonOutputManifest.from_wire()` before inspecting status or identity.
- Missing, unreadable, non-object, or schema-invalid manifests are corrupt job
  state. The worker logs `export_job_manifest_invalid` (or the reconciliation
  equivalent), records degraded worker health, and does not compose or
  automatically retry that job.
- `complete` and `failed` manifests are terminal and are never recomposed from
  a stale queue wake-up.
- `progress.json` is non-authoritative. A missing progress file is normal. An
  unreadable or schema-invalid progress file writes
  `export_job_progress_invalid`; composition may continue from the valid
  manifest.
- Progress decoding requires the complete documented wire shape. Identity and
  status fields are non-blank strings, `updated_at` is timezone-aware ISO-8601,
  integer fields exclude booleans, and completed chunk indexes are unique,
  non-negative, and lower than `total_chunks`. Invalid list members are rejected
  rather than filtered or numerically coerced.
- Readers attempt the progress read directly. Only `FileNotFoundError` is the
  normal absent state; other filesystem failures are retained as
  `progress_error` and flow through the same payload-safe degraded diagnostic
  as JSON, shape, field, and identity failures.
- Recovery diagnostics identify the thread and job but do not include chunk
  contents or the raw manifest/progress payload.

### Queue model: typed in-memory job wake-ups

The export queue is **not** a filesystem directory or a general event bus. It
is a `queue.SimpleQueue[JobMessage]` owned by the daemon composition root.

**Rationale**: The `manifest.json` in the job directory is the real persistent state. The queue event is purely a signal — "there is a pending job, go look at its manifest". Writing that signal to a file is unnecessary I/O that introduces its own failure modes (duplicate events, partial writes, stale processing claims). An in-memory queue eliminates the `queue/`, `processing/`, and `failed/` directory tree entirely.

#### Queue event

A queue item is an immutable `JobMessage` backed entirely by a versioned
`kind="job"` envelope. Its `job_id` property comes from envelope context and
its `resource_id` property (the reason thread id) comes from the strict job
payload. Optional wake-up hints live under the payload's `data` mapping.
The chat tool receives the queue's typed `JobSink` through constructor
injection; the reason module does not install a process-global enqueue
callback.

The worker reconstructs the job data path from `thread_id` and `job_id`: `private/workspaces/reason/{thread_id}/artifacts/export/jobs/{job_id}/manifest.json`.

#### Retry model

Retries are scheduled via `threading.Timer` rather than a persistent `next_attempt` field:

- On failure, the worker checks
  `manifest.attempts < MAX_EXPORT_ATTEMPTS`.
- If retryable, it starts a `threading.Timer` with exponential backoff (capped at 600s).
- When the timer fires, it enqueues a new typed wake-up for the same durable job.
- If `attempts >= MAX_EXPORT_ATTEMPTS`, the worker updates the manifest status
  to `failed` and does not re-enqueue.
- A failed compose attempt is retryable only after its incremented attempt
  count, last error, and attempt timestamp are atomically persisted to the
  manifest.
- If the manifest cannot be decoded or the retry-state write fails, the worker
  logs `export_job_state_persist_failed` and does not schedule an in-memory
  retry. Startup reconciliation must not be relied on to recover state that was
  never durably recorded.
- Once retry state is durably persisted, audit storage failure cannot suppress
  an otherwise eligible retry timer. Manifest writes and timer construction or
  start remain authoritative failures; export audit records are projections.

This is a purely in-memory retry schedule. On daemon crash, all in-flight retry timers are lost; the reconciliation step (see below) restores them.

#### File-level locking

Because the export worker and the synchronous CLI (`resume_job`) can attempt to compose the same job concurrently, each job subdirectory carries an optional `.lock` file.

Lock protocol:

- Before composing a job, the caller attempts to create `jobs/{job_id}/.lock` atomically (`O_CREAT | O_EXCL`).
- If creation succeeds, the caller owns the lock and may proceed with composition.
- If creation fails (`.lock` already exists), the caller must assume another thread or process is already composing the job and must either skip or back off.
- After composition completes (success or failure), the lock owner must remove `.lock`.
- A stale lock (e.g., process crash while holding the lock) is cleaned up by the startup reconciliation step (see below).
- The lock is purely advisory and cooperative. It does not protect against malicious or incorrect callers.

#### Startup reconciliation

When the daemon export worker starts, it must run a one-time reconciliation step before entering its event loop:

1. **Re-enqueue incomplete jobs**: Scan `private/workspaces/reason/*/artifacts/export/jobs/*/manifest.json`. For each manifest with status other than `complete` or `failed`, construct a typed `JobMessage` and push it into the in-memory queue. This recovers any jobs that were in flight when the daemon last exited.
2. **Clear stale locks**: Scan `private/workspaces/reason/*/artifacts/export/jobs/*/.lock`. Remove any `.lock` file found — these were held by crashed processes and are now stale.

Invalid-manifest diagnostics are best effort. Failure to persist one
`export_reconciliation_skip` record cannot abort the scan or prevent later
valid incomplete jobs from being enqueued. The final reconciliation summary is
also auxiliary to the completed scan.

This ensures that no pending work is lost across daemon restarts without requiring a persistent queue. The number of pending jobs at any time is bounded by the number of reason threads, so the startup scan is fast.

### State lifecycle summary

| Concept | Where | Persistent? |
|---|---|---|
| Job data (manifest, chunks, artifacts) | Per-thread workspace (`jobs/{job_id}/`) | Yes |
| Queue signal | `queue.SimpleQueue` in daemon process | No (rebuilt from manifests on startup) |
| Retry timer | `threading.Timer` in daemon process | No (rebuilt from manifest attempts on startup) |
| Compose lock | `.lock` file in job subdirectory | Yes (but cleared on startup) |

## Output Modes

The first version supports a small set of output modes:

- `outline` — chapter or section summary
- `narrative` — complete story-like prose
- `report` — analytical or documentary prose
- `summary` — compact digest

## Service Contract

Reason output composition is a reason-scoped service.

The service must be able to:

- plan a job from a selected reason source
- collect ordered items from the source
- partition items into segments
- derive a stable section plan from the source content and reuse it for every chunk
- compose each segment into a chunk
- persist chunk and manifest updates
- combine completed chunks into a final artifact
- generate a PDF artifact from the final Markdown output when the export completes
- resume a partially completed job from the manifest
- guard concurrent composition via the `.lock` file protocol (see Storage Contract)

The service must not enqueue an already-pending or already-complete job. It must only push to the in-memory queue on the initial plan for a new job.

The service may read reason state through reason service-facing methods or a dedicated adapter. It must not reinterpret reason state as chat history.

## Chat-Facing Contract

Chat may orchestrate the export job.

The chat-facing interface must allow the caller to specify:

- source thread id
- output mode
- output format
- step range or cursor
- segment size
- whether to include the manifest in the final response

Chat must not need to store the full long-form result in the chat context to complete the job.

The first chat-facing export tool call must be approval-gated, but the agent should call it directly when the user asks for an export rather than waiting for a separate confirmation turn. During the call, it prompts the user for confirmation, then plans the job, writes the manifest, pushes to the in-memory queue, and returns structured JSON that includes whether the user approved and, when approved, the queued job metadata. The daemon worker is a single process-global event loop responsible for composing chunks and writing the final artifact, and it must reconcile on startup (re-enqueue incomplete jobs from manifests) before entering its event loop.

### Daemon worker ownership

`nuself.daemon.reason_export.ReasonExportWorker` owns the daemon-side lifecycle
of reason export jobs. It exposes four composition capabilities:

- `enqueue(JobMessage)` accepts an already-typed job envelope;
- `prepare()` constructs workspace and output-service dependencies before the
  owned thread starts, so initialization failure cannot create a live worker;
- `run()` performs startup reconciliation and then consumes the in-memory
  queue until daemon shutdown;
- `stop()` cancels retry timers and drains queued work before the supervisor
  joins the owned thread.

The worker restores each dequeued envelope context and replaces its thread,
job, and source with the authoritative export resource identity. It reports
operation success/failure through `DaemonWorkerSupervisor`, but owns manifest
inspection, failure persistence, retry scheduling, reconciliation, and export
audit events itself. `DaemonState` must not retain parallel export queues,
timers, stores, services, or processor helpers.

`stop()` closes the in-memory enqueue boundary before draining it. A concurrent
or later enqueue/retry callback is ignored because the already-persisted
manifest remains authoritative and will be recovered by the next startup
reconciliation; no in-memory work may appear after the drain.

All export worker lifecycle and caught-failure audit writes use the shared
observable best-effort boundary. Audit failure cannot change an already-made
queue, manifest, retry, composition, reconciliation, or shutdown decision.
Invalid optional progress remains degraded input: its diagnostic may fail, but
composition still runs from the valid manifest.

Reason output planning, chunk skip/start/completion, composition, and PDF
lifecycle records use the validated Reason audit adapter over shared
best-effort observability. They cannot prevent a durable manifest/progress
transition, skip an existing chunk, block chunk composition, or replace a
composed Markdown/PDF outcome.

### Audit contract

The Reason subsystem owns one sealed audit registry across lifecycle, output,
and export-worker operations. `reasoning` records describe durable output
artifacts; `daemon` records describe wake-up delivery, queue consumption,
retries, and startup recovery. Component placement does not split semantic
ownership into parallel string protocols or a separate output-only registry.

Each definition fixes level, optional status, error policy, duration policy,
and exact metadata. Producers resolve and validate before entering the
best-effort sink. Unknown events and invalid payloads are programming errors,
not audit persistence failures. The domain-specific
`reason_audit_write_failed` record reports projection failure and remains
governed by shared observability.

Reasoning-side events:

| Event | Level | Status | Error / duration | Metadata |
|---|---|---|---|---|
| `reason_output_planned` | `info` | `created` | none | thread/job, mode/format, source start and nullable end, segment and step counts |
| `reason_output_chunk_skipped` | `info` | none | none | thread/job/chunk |
| `reason_output_chunk_started` | `info` | none | none | thread/job/chunk |
| `reason_output_chunk_failed` | `error` | `error` | error required | thread/job/chunk |
| `reason_output_chunk_completed` | `info` | `ok` | duration required | thread/job/chunk |
| `reason_output_composed` | `info` | `completed` | none | thread/job/chunk count |
| `reason_output_pdf_started` | `info` | none | none | thread/job |
| `reason_output_pdf_timeout` | `warning` | `error` | none | thread/job |
| `reason_output_pdf_failed` | `warning` | `error` | error required | thread/job |
| `reason_output_pdf_created` | `info` | `completed` | none | thread/job |

Daemon-side events:

| Event | Level | Status | Error | Metadata |
|---|---|---|---|---|
| `export_job_enqueue_failed` | `warning` | `degraded` | required | thread/job |
| `export_job_enqueued` | `info` | `queued` | forbidden | thread/job |
| `export_queue_drained` | `warning` | none | forbidden | positive drained job count |
| `export_worker_get_error` | `warning` | `error` | required | none |
| `export_job_type_ignored` | `warning` | none | forbidden | none |
| `export_job_dequeued` | `info` | none | forbidden | none; runtime context carries thread/job |
| `export_job_manifest_invalid` | `error` | `error` | required | none; runtime context carries thread/job |
| `export_job_progress_invalid` | `warning` | `degraded` | required | none; runtime context carries thread/job |
| `export_job_composition_started` | `info` | none | forbidden | chunk count |
| `export_job_state_persist_failed` | `error` | `error` | required | none; runtime context carries thread/job |
| `export_job_failed` | `error` | `error` | required | attempts |
| `export_job_retry` | `info` | `retry` | forbidden | attempts/backoff |
| `export_reconciliation_skip` | `warning` | `error` | required | thread/job |
| `export_queue_reconciled` | `info` | none | forbidden | non-negative replayed job count |

All event messages are fixed by the registry. Artifact paths, unsupported job
names, message ids, original-operation exception text, and duplicated
thread/job correlation are excluded from metadata. Thread/job ids remain only
where no runtime envelope exists: output operations, enqueue results, and
reconciliation skips.

When the Markdown artifact is finished, the export pipeline should automatically invoke the PDF helper script so the thread can be shared as both Markdown and PDF.

Repeated calls with the same selected source range and export settings should be idempotent. The same deterministic `job_id` is produced, and the same `jobs/{job_id}` directory is reused. If the earlier job is still pending or in progress, the plan step returns the existing manifest without re-enqueueing.

When the selected range is large, the job should be processed in batches and progress should be reported after each completed batch.

## Composition Workflow

### Plan

The service creates a manifest and records the requested source range, mode, format, and segment size.

### Collect

The service loads the selected reason steps and normalizes them into the shared item shape.

### Partition

The service groups items into segments.

The initial partitioning strategy may be fixed-size batches with optional boundary hints from step kind.

### Compose

Each segment is rewritten into a chunk.

The chunk writer must summarize and reframe the source material rather than merely concatenate raw step text.

An exception from the injected chunk runner remains authoritative and
propagates unchanged. `reason_output_chunk_failed` is a secondary structured
projection with thread, job, and chunk identity; diagnostic persistence
failure emits a terminal warning without replacing the runner exception,
writing the failed chunk, or adding an implicit retry.

### Persist

Each completed chunk is written to the workspace and marked complete in the manifest.

### Assemble

When all segments are complete, the service combines the chunks into the final artifact.

The final artifact must be readable on its own.

## Resume Behavior

The export job must be resumable.

If the job is interrupted, a later run must:

- acquire the `.lock` file before starting
- load the manifest
- skip completed chunks
- recompute only incomplete work
- finalize the artifact once all chunks are present
- release the `.lock` file after completion

If the caller cannot acquire the lock (another thread or process is already composing this job), it must skip or back off rather than attempt concurrent writes.

If the source thread changes after the job has begun, the export job must remain consistent with the source range recorded in the manifest.

## Extensibility

The first version is reason-only.

Later extensions may add:

- trace provenance annotations
- chat transcript excerpts
- reflection material
- persona discussion output

Those extensions must not require a redesign of the reason-only path.

## Behavioral Summary

- Reason remains the source of truth for long-run state.
- Reason output composition turns that state into a finished artifact.
- Chat may control the job but should not have to carry the full result in context.
- The reason workspace stores the job state, intermediate chunks, and final output.
