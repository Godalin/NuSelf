# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active.

## Objective

Reduce the frontend boundary to the minimum abstractions needed for a
replaceable UI: keep the typed approval port, publish presentation activity
directly through the existing runtime `EventPublisher`, and remove parallel
frontend-event wrappers and adapters.

## Ordered Steps

1. Remove the duplicate `FrontendEvent`/sink/adapter layer.
2. Publish approval activity directly through `EventPublisher`.
3. Preserve terminal independence and orthogonal feature policies.
4. Prove the smaller boundary with architecture and behavior tests.
5. Run full local and six-platform gates.

## Exclusions

- No web server or remote approval protocol in this goal.
- No second event bus, UI framework, manager, registry, or compatibility shim.
- No speculative abstraction for a frontend that does not yet exist.

## Completion Evidence

- One runtime event type and publisher path serves terminal, daemon, logs, and
  future adapters.
- Backend modules do not import terminal presentation.
- Approval remains a small injected port.
- The change is a net deletion.
- Full local and six-platform gates pass.

## Progress

- Removed `FrontendEvent`, its sink protocol/null object, and the runtime
  adapter module. Approval activity now goes straight from `FeatureExecutor`
  to the existing `EventPublisher`.
- Removed the unnecessary null audit sink; optional projections are represented
  by `None` rather than another class.
- The implementation and tests are currently a net deletion relative to the
  last pushed HEAD. Focused Pyright and 224 runtime/chat/architecture tests pass.
- Full local gates pass: Pyright reports 0 errors and 0 warnings; all 2486
  tests pass; sdist and wheel builds succeed; and the clean Python 3.12 wheel
  imports the simplified execution boundary and runs the CLI. Commit, push,
  and final six-platform CI remain.
