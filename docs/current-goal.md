# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

In progress — continuously audit and simplify while preserving composability.

## Current Phase

Audit the remaining daemon and service adapters for redundant composition or
pass-through APIs; remove only seams whose callers and lifecycle ownership are
already explicit.

## Constraints

- Preserve domain-owned registries, semantic validators, service APIs, durable
  recovery, and the single-scheduler daemon.
- Add no generic bus, facade hierarchy, compatibility shim, worker, or lock.
- Keep each reduction independently tested and committed; do not return this
  board to Idle while the persistent review goal remains active.

## Phase Evidence

- Memory, reason, persona, notification, reflection, Chat, endpoint, storage,
  and observability audit validators now compose the shared exact-field
  primitive; their registries and semantic value checks remain domain-owned.
- Daemon start/stop lifecycle projection shares one transition metadata
  builder; client/lifecycle protocol and state APIs were retained only after
  confirming current CLI/REPL production callers.
- Focused affected-domain suite: 325 passed.
- `uv run --locked pytest -q`: 2447 passed.
- `uv run --locked pyright`: 0 errors, 0 warnings.
- Registered daemon, storage, endpoint, Chat, memory, notification, persona,
  reason, reflection, and observability failure producers now share one narrow
  interpreter for diagnostic derivation, definition validation, and sink
  invocation; event/message/metadata selection remains domain-owned.
- Registered-failure focused suite: 272 passed; endpoint failover integration:
  45 passed.
- Post-interpreter `uv run --locked pytest -q`: 2447 passed; Pyright remains
  0 errors and 0 warnings.
- `ApplicationRuntime` no longer mirrors the backend cache or exposes unused
  opened/closed flags; its behavioral laziness, reuse, idempotent close, and
  post-close rejection remain tested.
- CLI uses the sole application runtime context directly; the pass-through
  `use_cli_application_runtime` alias is gone while authority-drift validation
  remains in CLI composition.
- Daemon server injects `ApplicationGraph` into `DaemonState`; state no longer
  discovers, creates, or retains an `ApplicationRuntime`.
- Composition/lifecycle focused suite: 62 passed.
- Post-ownership `uv run --locked pytest -q`: 2448 passed; Pyright remains
  0 errors and 0 warnings.
- `ApplicationGraph` now composes one authority-scoped memory query, reason,
  and reflection service; Chat, CLI, REPL, and daemon consumers reuse them.
- Removed the repeated reason/reflection service factories; a model-backed
  reason advancer is a one-operation method input rather than a parallel
  service graph.
- Post-service-composition `uv run --locked pytest -q`: 2448 passed;
  `uv run --locked pyright`: 0 errors, 0 warnings; `uv build`: sdist and wheel
  succeeded.

## Last Completed Goal

Simplified composable daemon audit infrastructure without merging domain
registries or changing protocol, storage, scheduler, or CLI behavior.

## Completion Evidence

- Removed the production-unused worker-timeout event, reporter, schema, and
  tests left by the former multi-worker daemon.
- Removed the constant `memory_curation_requested` chat audit field; durable
  recovery remains authoritative.
- Daemon audit domains now compose one exact-field validation primitive while
  retaining independent event definitions and producers.
- Focused daemon/shared audit suite: 71 passed.
- `uv run --locked pytest -q`: 2447 passed.
- `uv run --locked pyright`: 0 errors, 0 warnings.
- `uv build`: `nuself-0.3.1` sdist and wheel built successfully.
