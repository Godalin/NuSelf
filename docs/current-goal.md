# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Give each project root one cross-process daemon owner so concurrent starts
cannot unlink or replace a live daemon's socket and PID resources.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. [x] Audit daemon PID, socket, startup, and shutdown ownership.
2. [x] Specify a stable per-project daemon instance lock.
3. [x] Acquire the lock before touching socket or PID resources.
4. [x] Make lock contention observable and return non-zero without constructing
   daemon state or modifying the current owner's resources.
5. [x] Keep socket/PID cleanup inside the lock owner's `finally` boundary,
   including partial startup failures.
6. [x] Start workers only after the Unix server binds successfully.
7. [x] Run focused/full tests, type checking, and formatting checks.
8. [x] Update user-facing docs/changelog and commit this stage.

## Out Of Scope

- Changing daemon protocol, request handlers, or client retry behavior.
- Automatically killing an existing process based on PID contents.
- Changing CLI start polling duration or stop escalation policy.
- Strictly validating PID contents in this same commit.

## Completion Evidence

- The first daemon holds an exclusive lock for its complete owned lifecycle.
- A second daemon returns non-zero, emits `instance_lock_contended`, and leaves
  the first daemon's socket and PID files unchanged.
- A lock becomes acquirable after the owner releases it.
- Stale socket/PID resources are removed only after ownership is acquired.
- Bind or partial startup failures still stop started workers and clean owned
  socket/PID resources before releasing the lock.
- Focused daemon tests, full pytest, Pyright, and `git diff --check` pass.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Audit daemon PID parsing and start/stop status reporting for observable stale or
malformed lifecycle metadata.
