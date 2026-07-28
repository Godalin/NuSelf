# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active stabilization target, immediate context, and the next few steps. Completed work belongs in [`docs/TODOs.md`](TODOs.md), not here.

## Focus

The `v0.2.x` stabilization line is complete and merged into `main` (released at
`v0.2.5`). The active line is now `v0.3`, focused on code-review-driven
optimization: correctness/concurrency fixes, a caching layer over the post-v0.2.4
"recompute derived data from `list()`" model, and CLI/subsystem deduplication.

v0.3 optimization batches (do in order, each its own commit + tests):

1. ☑ Batch A — correctness/concurrency bug fixes.
2. ☑ Batch B — caching / N+1 performance.
3. ☑ Batch C — dedup & dead-code cleanup.

`main` remains the stable, releasable branch. `dev/v0.3.x` is the active line;
`feature/*` stays isolated for one feature or fix at a time.

## Immediate Context

- We are working on `dev/v0.3.x` (branched from `main` at `v0.2.5` + CLAUDE.md).
- `v0.2.5` is the current release; next target is `v0.3.0`.
- `main` now tracks the merged `v0.2.x` line and is pushed to origin.
- First v0.3 commit: interactive tool-approval prompt redesign (`render_approval_prompt`).
- Specs remain the source of truth for behavior changes; the daemon error-response
  and config-load changes in Batch A/B touch `errors.md` / `config.md`.
- User-visible changes should keep README, specs, TODOs, and changelog synchronized.

## Next Steps

### ✅ Done — interactive tool-approval prompt redesign

(First v0.3 commit. `render_approval_prompt` replaces the duplicated
`[approval_prompted]` / `Confirm execute ... ? (y/n):` lines.)

### Batch A — correctness / concurrency bug fixes

- [x] `daemon/server.py` `handle()`: catch non-`ProtocolError` exceptions and return `DaemonResponse.fail` (fixes `UnboundLocalError` that hangs the client).
- [x] `daemon/server.py` `_export_timers`: guard with a lock; drop fired timers to stop unbounded growth.
- [x] `persona/graph.py` `_complete_persona_structured`: mirror chat.py failover policy and log swallowed errors instead of silent `None`.
- [x] `notification/macos.py`: add a `timeout=` to the `osascript` subprocess.
- [x] `config.py`: narrow the broad `except Exception: pass` around config load so malformed config is not silently treated as "no config".

### Batch B — caching / N+1 performance

- [x] Memoize `ConfigSystem.load()` on `(config_path, mtime, size)`.
- [x] Compute the symbolic graph / transitive closure once per `MemoryQueryService.search`.
- [x] Share reason/trace/memory service instances in `agent/tools.py`.
- [x] SQLite backend: cache column tuple and push `find()` into a `WHERE` clause.
- [x] Fix remaining N+1 reads (reason `get_job` direct read, notification single scan, reflection single `last_reflection` read, batched reasoning step counts, wasted moderator synthesizer call).

### ✅ Review follow-up — data safety and worker reliability

- [x] Preserve v1 SQLite payloads during schema upgrade and create a pre-upgrade backup.
- [x] Make reason step + thread batches real SQLite transactions with rollback.
- [x] Scope cached default backends by project root and close them on reset.
- [x] Keep background workers alive after unexpected iteration errors and expose `daemon health`.
- [x] Declare directly imported runtime packages and use `README.md` as package metadata.

### Batch C — dedup & dead-code cleanup

- [x] `cli.py`: generic `_resolve_handle` helpers.
- [x] Move one-shot command handlers into focused `nuself.cli.commands` modules,
  with memory commands grouped under `nuself.cli.commands.memory`.
- [x] Convert `nuself.cli` into a package containing parser, commands, and REPL
  modules while preserving `nuself.cli:main`.
- [x] Move REPL input, session state/control, subsystem commands, and transcript
  rendering/export into focused `nuself.cli.repl` modules.
- [x] Extract shared memory text/json/clamp helpers.
- [x] Dedup `persona/tools.py` builders.
- [x] Remove dead reflection event-trigger and `_handle_proposals_after_turn` paths.
- [x] Replace `reindex()` no-ops with real rebuildable derived JSON projections.

## Completion Criteria

- Batches A → B → C land in order, each as its own commit with `pytest` + `pyright` green.
- Specs are updated before code for each non-trivial behavioral change.
- README, specs, TODOs, and CHANGELOG stay synchronized for user-visible changes.
- Work stays on `dev/v0.3.x`; `v0.3.0` is tagged when the batches are complete.
