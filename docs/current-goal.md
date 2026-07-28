# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make CLI persona lifecycle trace recording use the shared observability
boundary so a successful persona mutation cannot lose its trace failure silently.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. [x] Trace CLI create/enable/disable mutation and trace ordering.
2. [x] Specify lifecycle trace recording as an observable secondary effect.
3. [x] Replace the private RuntimeError catch with
   `run_observed_best_effort(errors=(RuntimeError,))`.
4. [x] Preserve successful command status and output after a recoverable trace
   failure.
5. [x] Preserve propagation of unknown actions and undeclared exceptions.
6. [x] Run focused/full tests, type checking, and formatting checks.
7. [x] Update user-facing docs/changelog and commit this stage.

## Out Of Scope

- Changing persona CRUD, confirmation, handle, or output behavior.
- Adding delete trace semantics.
- Changing agent-facing persona tool trace behavior in this same commit.
- Broadly suppressing all trace implementation failures.

## Completion Evidence

- A create/enable/disable `RuntimeError` still returns command success after the
  persona mutation.
- The same failure emits `persona/trace_recording_failed` with persona identity,
  action, and compact exception chain.
- An unknown lifecycle action or undeclared exception is not swallowed.
- No private try/except wrapper remains around CLI lifecycle trace recording.
- Focused CLI/observability tests, full pytest, Pyright, and
  `git diff --check` pass.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Audit email notification configuration loading and outbox timestamp cleanup for
silent parse failures.
