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
- resume state
- creation and update timestamps

## Storage Contract

Reason output composition jobs live in the owning reason workspace.
Export execution is handled by one daemon-global worker loop that scans reason workspaces and processes queued export jobs across the process.

Required workspace layout:

```text
private/workspaces/reason/{thread_id}/
  workspace.sqlite
  artifacts/
    export/
      manifest.json
      chunk-001.md
      chunk-002.md
      combined.md
      progress.json
      queue/
      processing/
      failed/
```

Rules:

- The workspace is thread-local.
- Export data must not be stored in transcript storage.
- Export data must not be written into another thread's workspace.
- The export root is fixed for the thread, so repeated exports rewrite the same manifest and artifact files instead of creating a new per-job directory.
- The manifest is the resumable source of truth for the export job.

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
- compose each segment into a chunk
- persist chunk and manifest updates
- combine completed chunks into a final artifact
- resume a partially completed job from the manifest

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

The first chat-facing export tool call must be fire-and-return: it plans the job, writes the manifest, enqueues the background work, and immediately returns the queued job metadata. The daemon worker is a single process-global loop responsible for composing chunks and writing the final artifact.

Repeated calls with the same selected source range and export settings should be idempotent and rewrite the same fixed export root for the thread.

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

- load the manifest
- skip completed chunks
- recompute only incomplete work
- finalize the artifact once all chunks are present

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
