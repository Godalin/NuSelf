# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Consolidate `AGENTS.md` into a concise repository-level development workflow
and a non-duplicative documentation map.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. [x] Audit duplicated guidance and documentation links.
2. [x] Consolidate mandatory development constraints and progress handling.
3. [x] Replace the selective spec link list with authoritative entry points.
4. [x] Verify links, responsibilities, formatting, and repository state.
5. [ ] Commit and push the reviewed change.

## Out Of Scope

- Changing runtime behavior or subsystem contracts.
- Duplicating detailed policies already governed by `docs/spec/development.md`.
- Maintaining a hand-picked list of subsystem specs in `AGENTS.md`.

## Completion Evidence

- `AGENTS.md` states the full mandatory workflow without repeating detailed
  subsystem policy.
- Documentation links resolve and point to authoritative indexes.
- `docs/current-goal.md` returns to an explicit idle state after completion.
- `git diff --check` passes and the remote branch matches local `HEAD`.
