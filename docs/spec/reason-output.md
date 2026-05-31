# Reason Output Composition Spec

Status: DRAFT — reason-scoped long-form export and composition contract for v0.2.x.

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

Reason output composition jobs live in the owning reason workspace.
Export execution is handled by one daemon-global worker loop that scans reason workspaces and processes queued export jobs across the process.

### Workspace layout

Each export job occupies its own subdirectory under `export/jobs/{job_id}`.
Queue, processing, and failed event files live at the `export/` level, keyed by `job_id`.

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
      queue/          # {job_id}.json  — pending events
      processing/     # {job_id}.json  — claimed in-progress events
      failed/         # {job_id}-{ts}.json — exhausted events
```

Rules:

- The workspace is thread-local.
- Export data must not be stored in transcript storage.
- Export data must not be written into another thread's workspace.
- Each export job has a deterministic `job_id` derived from its parameters. The job's data lives under `jobs/{job_id}/`, not in the root `export/` directory. This allows multiple export ranges or settings to coexist without destructive collision: re-planning with different parameters does not delete pending queue events or in-progress processing claims for other jobs.
- The manifest is the resumable source of truth for the export job.
- The manifest stores a deterministic section plan derived from the selected source steps, not from chunk boundaries, so each chunk can reuse the same chapter or section names, focus, and ordering context across the full export.
- Repeated calls with the same selected source range and export settings are idempotent: they produce the same `job_id`, reuse the same `jobs/{job_id}` directory, and skip re-enqueueing if the job is already pending or complete.

### Queue event schema

A queue event is a JSON file named `{job_id}.json` in the `queue/` directory:

```json
{
    "type": "reason_output_job",
    "job_id": "reason-output-{sha256}",
    "thread_id": "reason-...",
    "created_at": "2026-01-01T00:00:00.000000+00:00",
    "attempts": 0,
    "next_attempt": null
}
```

The worker does NOT read the manifest path from the queue event. It reconstructs `jobs/{job_id}/manifest.json` from the `thread_id` and `job_id`. This keeps the queue event lightweight and avoids stale path references.

### File-level locking

Because the export worker and the synchronous CLI (`resume_job`) can attempt to compose the same job concurrently, each job subdirectory carries an optional `.lock` file.

Lock protocol:

- Before composing a job, the caller attempts to create `jobs/{job_id}/.lock` atomically (`O_CREAT | O_EXCL`).
- If creation succeeds, the caller owns the lock and may proceed with composition.
- If creation fails (`.lock` already exists), the caller must assume another thread or process is already composing the job and must either skip or back off.
- After composition completes (success or failure), the lock owner must remove `.lock`.
- A stale lock (e.g., process crash while holding the lock) is detected by the owner: on daemon restart, the startup reconciliation step removes all `.lock` files under `jobs/` (see Startup Reconciliation below).
- The lock is purely advisory and cooperative. It does not protect against malicious or incorrect callers.

### Startup reconciliation

When the daemon export worker starts, it must run a one-time reconciliation step before entering its polling loop:

1. Scan `export/processing/` in every workspace. Any file found there was left by a worker that crashed or was killed while composing. Move each file back to `export/queue/` (preserving its `attempts` count) so the job can be retried.
2. Scan `export/jobs/` in every workspace. Remove any `.lock` file found — these were held by crashed processes and are now stale.

This ensures that no pending work is lost across daemon restarts and that no stale lock blocks future composition.

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

The service must not write a queue event when re-planning an existing job that is already pending (queue event exists) or complete. It must only enqueue on the initial plan for a new job.

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

The first chat-facing export tool call must be approval-gated, but the agent should call it directly when the user asks for an export rather than waiting for a separate confirmation turn. During the call, it prompts the user for confirmation, then plans the job, writes the manifest, enqueues the background work, and returns structured JSON that includes whether the user approved and, when approved, the queued job metadata. The daemon worker is a single process-global loop responsible for composing chunks and writing the final artifact, and it must scan the queue immediately on startup before falling back to its normal polling interval.

When the Markdown artifact is finished, the export pipeline should automatically invoke the PDF helper script so the thread can be shared as both Markdown and PDF.

Repeated calls with the same selected source range and export settings should be idempotent. The same deterministic `job_id` is produced, and the same `jobs/{job_id}` directory is reused. If the earlier job is still pending or in progress, the plan step returns the existing manifest without re-enqueueing. The `plan_job` service must not write a queue event for an existing job that already has one pending, and must not write a duplicate queue event for a job that is already being processed or is complete.

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
