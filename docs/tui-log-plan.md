# TUI And Logging Plan

This plan defines a short interaction polish slice before returning to the persona-runtime work. The goal is not to build a large UI framework. It is to make everyday NuSelf use easier to inspect, safer to operate, and less noisy.

## Goals

- Make interactive chat feel like a persistent local companion rather than a raw readline loop.
- Make daemon, chat, memory, and future notification activity observable from one consistent log surface.
- Keep private data under ignored `private/` paths.
- Preserve the current daemon protocol unless a specific logging or TUI feature needs a typed response change.
- Keep implementation small enough to finish before returning to persona activation and routing.

## Non-Goals

- Full web UI.
- Cross-platform desktop app.
- Rich multi-pane knowledge browser.
- Streaming token protocol overhaul.
- Remote log aggregation.
- Public telemetry.

## Current Baseline

- `nuself chat`, `nuself attach`, and `nuself daemon attach` share a readline-backed interactive loop.
- Interactive mode supports `:q`, `:quit`, `:exit`, `:memory`, and command help.
- The daemon writes stdout and stderr to `private/logs/daemon.log`.
- Memory curator and optimizer append action lines to `private/logs/memory.log`.
- `nuself daemon logs` prints the whole daemon log file.
- There is no unified log model, log filtering, tailing, structured event metadata, or TUI state surface.

## TUI Direction

Keep the first TUI as a terminal-native shell around existing commands. It should improve visibility without changing core chat semantics.

### First Slice

- Add a dedicated interactive session renderer module under `src/nuself/tui/`.
- Keep standard-library rendering first: clear sections, stable prompts, status lines, and command output blocks.
- Preserve readline history when available.
- Add a compact session header with daemon status, thread ID, and memory update state.
- Add interactive commands:
  - `:help` shows commands.
  - `:status` shows daemon/socket/thread status.
  - `:logs` shows recent relevant log lines.
  - `:memory` keeps the existing memory preview behavior.
  - `:clear` redraws the session view.
- Keep non-interactive `--message` output plain and script-friendly.

### Later Slice

- Consider a richer optional TUI dependency only after the standard-library shell exposes the right state model.
- If adopted, prefer an optional dependency group instead of making normal CLI startup require it.
- Add navigable panes only when thread commands, outbox review, and richer memory review exist.

## Logging Direction

Logging should become structured at the write boundary while still being readable with plain text tools.

### Log Files

- `private/logs/daemon.log`: daemon lifecycle, socket handling, request failures, background job failures.
- `private/logs/chat.log`: chat turns, thread IDs, runtime outcomes, graph diagnostics summaries.
- `private/logs/memory.log`: curator and optimizer actions, already present.
- `private/logs/outbox.log`: future notification/outbox delivery events, already planned.

### Event Shape

Use JSON Lines for new structured logs:

```json
{"time":"2026-05-08T12:00:00+08:00","level":"info","component":"chat","event":"turn_completed","thread_id":"default","message":"chat turn completed"}
```

Required fields:

- `time`
- `level`
- `component`
- `event`
- `message`

Optional fields:

- `thread_id`
- `request_id`
- `node`
- `duration_ms`
- `status`
- `error`
- `metadata`

### Privacy Rules

- Do not log full user messages by default.
- Do not log full assistant answers by default.
- Do not log raw memory bodies, source chunks, or profile text.
- Log stable IDs, counts, summaries, statuses, and diagnostics.
- Allow explicit debug logging later through ignored private configuration.

### CLI Surface

- Extend `nuself daemon logs` into a general log viewer:
  - `nuself logs`
  - `nuself logs --component daemon`
  - `nuself logs --component chat`
  - `nuself logs --component memory`
  - `nuself logs --tail 50`
  - `nuself logs --follow`
- Keep `nuself daemon logs` as a thin alias while the daemon command group remains.
- Render JSONL logs as concise text by default.
- Provide `--json` for raw log records.

## Implementation Order

1. Add a small structured logging module with JSONL append helpers and safe field normalization.
2. Route daemon lifecycle and daemon request errors through the new logger.
3. Add `chat.log` entries around conversation runtime completion and failures without storing message bodies.
4. Add `nuself logs` with component filtering, tail count, and plain rendering.
5. Refactor interactive loop rendering into a `tui` module without changing chat behavior.
6. Add `:status` and `:logs` commands to interactive mode.
7. Update README and Chinese README command docs after the user-facing CLI surface lands.

## Validation

- `uv run pytest tests/test_cli.py tests/test_daemon_server.py`
- Focused tests for JSONL log writing and redaction.
- CLI tests for `nuself logs --tail`, missing log files, and component filtering.
- Interactive command tests for `:status`, `:logs`, and existing `:memory`.
- `uvx pyright`
- Full `uv run pytest` before merging back to `main`.

## Commit Plan

1. `docs(cli): plan TUI and logging polish`
2. `feat(logging): add structured local log writer`
3. `feat(cli): add log viewer commands`
4. `feat(tui): extract interactive session renderer`
5. `feat(tui): add status and log commands`
6. `docs(cli): update TUI and logging progress`

After these are implemented and reviewed, merge this branch back to `main` and resume the persona activation/routing focus.
