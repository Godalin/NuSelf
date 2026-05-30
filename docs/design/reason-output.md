# Reason Output Composition Design

Status: proposal for the v0.2.x line.

## Purpose

The reason subsystem already produces durable long-run steps, but those steps are not yet a user-facing finished product.

This design introduces a reason-scoped output composition layer that turns ordered reason data into a complete artifact such as a story, report, outline, or narrative summary. It is intentionally designed to be chat-friendly: the chat runtime may orchestrate the work, but it should not need to keep the full long-form content in its own prompt context.

The first version is reason-specific. Trace may later be added as an optional provenance layer, but it is not part of the initial path.

## Goals

- Convert reason steps into a coherent long-form output without relying on a single chat turn.
- Allow chat to drive the process by range, batch, or segment.
- Keep long intermediate text out of chat context.
- Persist the composition job state in the reason workspace, not in transcript storage.
- Support resumable, chunked processing so large outputs can be built incrementally.

## Non-Goals

- This design does not replace the reason subsystem.
- This design does not change the reason step schema.
- This design does not make trace a required input in the first version.
- This design does not use the chat transcript as the source of truth for long output generation.
- This design does not expose a general unrestricted filesystem to the agent runtime.

## Positioning

The subsystem sits beside the existing reason service:

- `reason` owns the durable long-run working state.
- `reason output` consumes reason steps and produces a finished artifact.
- `chat` orchestrates and presents the job.
- `reason workspace` stores intermediate artifacts, chunk files, and manifest data.

The critical boundary is that chat manages the task, but the task state lives in the reason workspace.
The execution loop itself is daemon-global: one background worker scans the thread workspaces and processes export jobs for the whole process.

## Core Concepts

### Source

A source is an ordered stream of items that can be composed into a finished artifact. In the first version the source is a reason thread, but the abstraction should remain simple enough to extend later.

Source examples:

- `reason_thread`
- `reason_step`

### Item

An item is the smallest unit that the composer reads. For reason output, an item is usually one reason step.

Each item should have:

- a stable id
- an order position
- a short summary
- a body field for the full content
- optional evidence references
- optional type or kind metadata

### Segment

A segment is a batch of items processed together. Segments are the work unit of the export worker.

Example segment sizes:

- steps 1-5
- steps 6-10
- latest 20 steps grouped by topic shift

### Chunk

A chunk is a composed intermediate artifact produced from one segment. Chunks are written to the workspace so they can be resumed or recombined later.

### Manifest

The manifest is the control file for one output job. It records:

- source id
- job id
- mode
- output format
- step range or cursor state
- chunk inventory
- generation timestamps
- resume state

The manifest is the primary way to make the job resumable.

### Artifact

The final artifact is the finished user-facing output, usually a Markdown file in the first version.

## Architecture

### Chat Orchestrator

Chat should act as the task controller, not the long-text engine.

Chat responsibilities:

- accept the user request
- choose the source thread
- choose the output mode
- choose the step range or batch size
- prompt for confirmation, then launch the export worker
- surface progress and the final path

Chat should avoid keeping the full long-form output in memory when that output can be stored on disk.

### Export Worker Subagent

The worker performs the heavy lifting:

1. read the selected reason steps
2. batch them into segments
3. compose each segment into a chunk
4. persist the chunk and manifest update
5. combine chunks into the final artifact

The worker should be able to run repeatedly over the same job id without redoing finished segments.

### Reason Service

Reason remains the source of truth for thread state and step storage.

The output composer may read reason steps through reason service-facing methods or a dedicated adapter, but it should not reinterpret reason state as chat history.

### Workspace Storage

Reason output writes intermediate files into the reason workspace.

Recommended layout:

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

The workspace is thread-local. It should not be used as a shared cross-thread cache.

The export root is fixed for each thread so repeated exports with the same source range and settings reuse the same artifact location instead of creating a new per-job directory.

## Composition Pipeline

### 1. Plan

The worker receives the export request and writes an initial manifest.

The plan records:

- source thread id
- selected step range or cursor
- target mode
- target format
- segment size

### 2. Collect

The worker loads the selected reason steps and normalizes them into a common item shape.

For each item, the worker should capture:

- id
- index
- summary
- output/body
- kind
- evidence refs

### 3. Partition

The worker groups items into segments.

Partitioning can be simple in the first version:

- fixed step batches
- optional boundary hints from step kind
- optional manual range selection from chat

### 4. Compose Chunks

Each segment becomes one chunk.

The chunk writer should summarize and rewrite, not merely concatenate raw step text.

Chunk output may be one of:

- outline-style prose
- story prose
- report prose
- note-style synthesis

### 5. Persist Intermediate Results

Every finished chunk is written to the workspace and marked complete in the manifest.

This makes the job resumable after interruption.

### 6. Assemble Final Artifact

After all chunks are complete, the worker combines them into the final output file.

The final artifact should be readable on its own, while the manifest preserves the mapping back to the source steps.

## Output Modes

The first version should support a small set of modes rather than a large generic surface.

Recommended initial modes:

- `outline` — chapter-level or section-level summary
- `narrative` — complete story-like prose
- `report` — analytical or documentary prose
- `summary` — compact high-level digest

## Chat-Facing Interface

The chat runtime should expose a small, stable command/tool shape.

Suggested parameters:

- source thread id
- mode
- format
- step range or cursor
- segment size
- include manifest flag

Suggested behavior:

- if the user asks for a story, default to `narrative`
- if the user asks for a short synthesis, default to `summary`
- if the user asks for a chapter plan, default to `outline`
- if the selected range is large, process in batches and report progress after each batch

The chat runtime should show a short progress summary and the final artifact path, not the entire intermediate text.

## Failure and Resume Behavior

The export job should be resumable.

If the worker stops halfway through, the next run should:

- read the manifest
- skip completed chunks
- recompute only missing work
- finalize the combined artifact if all chunks are present

If the source thread changes while the export is running, the manifest should record the selected range so the job remains consistent with the original request.

## Extensibility

The first version only needs reason output.

Later the same structure can be extended to:

- trace summaries as provenance annotations
- chat transcript excerpts as context
- reflection items as source material
- persona discussion outputs as source material

The composition layer should stay source-agnostic enough that those additions do not require a redesign.

## Design Summary

This subsystem is deliberately narrow:

- reason owns the source data
- the exporter owns the rewrite and assembly work
- the reason workspace owns the intermediate state
- chat owns orchestration and user interaction

That split keeps long outputs out of chat context while still letting chat drive the process in small batches.
