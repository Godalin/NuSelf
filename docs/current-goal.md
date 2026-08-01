# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

In progress — continuously audit and simplify while preserving composability.

## Current Phase

Audit daemon server startup/cleanup composition for duplicated lifecycle state
or wrapper steps while preserving one process owner and exhaustive cleanup.

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
- Daemon request-handler state no longer exposes the conversation runtime that
  no registered request handler uses; domain runtime ownership remains inside
  daemon composition.
- Five recurring submissions now derive from one immutable task/interval list;
  four mutable interval mirror fields and repeated startup branches are gone.
- Replaced obsolete named-factory boundary checks with stronger application
  package boundaries after those factories were deleted.
- Daemon/boundary focused suite: 221 passed. Post-periodic-composition
  `uv run --locked pytest -q`: 2448 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Daemon protocol/payload codecs remain intentionally distinct: each represents
  a different exact wire schema and classified decode context; no generic codec
  layer was introduced.
- Reason export now receives workspace, output service, and scheduler sink as
  complete construction dependencies. Removed nullable dependency mirrors,
  `prepare()`, late sink binding, and their runtime guards.
- Reason-export focused suite: 91 passed. Post-export-composition
  `uv run --locked pytest -q`: 2448 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Lifecycle start/stop/restart result types remain justified by their distinct
  transition and audit consumers. `DaemonStopError` no longer mirrors an
  independently supplied ownership value; it derives ownership from its sole
  authoritative status snapshot.
- Lifecycle/CLI focused suite: 444 passed. Post-lifecycle-state
  `uv run --locked pytest -q`: 2448 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Activity broker, wire codecs, and REPL fallback remain separate because they
  own bounded fan-out, protocol validation, and durable recovery respectively.
  Removed four historical underscore lifecycle aliases from live visibility;
  only registered dotted runtime identities and current audits remain.
- Activity-only close and event-classification helpers are now private module
  details instead of implied cross-module APIs.
- Activity/client focused suite: 120 passed. Post-activity cleanup
  `uv run --locked pytest -q`: 2449 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Scheduler task, submission, completion, active identity, and busy-resource
  state remain necessary for coalescing and serialization. Four lifecycle
  booleans were replaced by one monotonic `created/running/stopping/stopped`
  phase; running and accepting health now derive from that source.
- Scheduler/daemon focused suite: 50 passed. Post-scheduler-lifecycle
  `uv run --locked pytest -q`: 2449 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.

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
