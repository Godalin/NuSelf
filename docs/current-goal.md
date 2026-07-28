# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Move interactive CLI/REPL history, completion, and display state from mutable
module globals into explicit session ownership.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. [x] Trace creation, mutation, reset, and test ownership of interactive state.
2. [x] Specify session-scoped input and display lifecycle.
3. [x] Introduce one typed session-state owner without changing REPL behavior.
4. [x] Remove mutable CLI/REPL globals and migrate callers/tests.
5. [x] Audit remaining interactive lifecycle leaks.
6. [x] Run full tests, type checking, and formatting checks.
7. [ ] Commit; push all pending commits after explicit authorization.

## Out Of Scope

- Changing command syntax, history persistence format, completion results, or
  visible transcript rendering.
- Replacing prompt-toolkit or the existing REPL runtime.
- Combining daemon worker lifecycle changes into this slice.

## Completion Evidence

- Two interactive sessions do not share header, history, or completer state.
- Input history still persists and de-duplicates under the existing contract.
- Existing CLI/REPL output tests remain unchanged.
- No mutable session-behavior globals remain in `nuself.cli` or
  `nuself.cli.repl.input`.
- Full pytest, Pyright, and `git diff --check` pass.

## Next Review Batch

Consolidate daemon worker start/stop/join state transitions behind one lifecycle
primitive. Preserve each worker's scheduling semantics, but make duplicate
start, shutdown signaling, join timeout, liveness, and cleanup consistent.
