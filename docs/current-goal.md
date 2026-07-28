# Current Goal

This is NuSelf's short-lived execution board. It contains only the active
objective, ordered work, explicit exclusions, and completion evidence.
Completed history belongs in Git and `CHANGELOG.md`; deferred work belongs in
[`TODOs.md`](TODOs.md).

## Status

Idle — no implementation objective is currently active.

## Next Action

Before starting non-trivial work:

1. Select and remove one outcome from [`TODOs.md`](TODOs.md), or define a newly
   requested outcome.
2. Replace this idle state with the objective, active branch, ordered steps,
   exclusions, and objective completion evidence.
3. Update the governing specification before implementation when behavior
   changes.
4. Update progress as soon as a step completes or scope changes, and include
   that update in the same functional commit.
5. On completion, move only unresolved follow-ups to `TODOs.md`, preserve
   completed history in Git or `CHANGELOG.md`, and restore this idle state.

## Documentation Responsibilities

- `AGENTS.md`: mandatory development constraints and high-value navigation.
- `docs/current-goal.md`: the one active execution board, or this explicit idle
  state.
- `docs/TODOs.md`: unresolved medium/long-term backlog only.
- `docs/architecture.md`: current high-level boundaries and rationale.
- `docs/spec/`: authoritative current behavior and development policies.
- `CHANGELOG.md`: completed user-visible changes by release.
- Git history: completed internal work and superseded implementation plans.
- `README.md` and `README.zh-CN.md`: synchronized user-facing overview and
  entry points.
