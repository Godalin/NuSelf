# Current Goal

This is NuSelf's short-lived execution board. It contains only the active
objective, the next ordered steps, explicit exclusions, and completion
evidence. Update it when active work changes. Completed history belongs in Git
and `CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Simplify the documentation system without weakening authoritative behavioral
specifications, and restore `current-goal.md` as the reliable entry point for
active development progress.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. [x] Define and document the responsibilities of active documentation.
2. [ ] Repair specification indexes, status labels, and internal links.
3. [ ] Reduce `TODOs.md` to unresolved backlog and remove the completed
   milestone plan from active documentation.
4. [ ] Replace overlapping historical design documents with one concise
   current architecture document.
5. [ ] Update English/Chinese README and `AGENTS.md` navigation.
6. [ ] Run link, anchor, spec-index, formatting, and repository validation.
7. [ ] Commit in reviewable stages and push `dev/v0.3.x`.

## Documentation Responsibilities

- `AGENTS.md`: development constraints and high-value navigation.
- `docs/current-goal.md`: the one active execution board.
- `docs/TODOs.md`: unresolved medium/long-term backlog only.
- `docs/architecture.md`: current high-level system boundaries and design
  rationale; no behavioral contract duplication.
- `docs/spec/`: authoritative current behavior and development policies.
- `CHANGELOG.md`: user-visible completed changes by release.
- Git history: completed internal work and superseded implementation plans.
- `README.md` and `README.zh-CN.md`: synchronized user-facing overview and
  entry points.

## Out Of Scope

- Changing runtime behavior while reorganizing documentation.
- Removing detailed behavioral contracts merely to reduce line count.
- Preserving superseded plans in an active archive; Git already retains them.

## Completion Evidence

- No broken local Markdown file or heading links.
- Every authoritative spec is listed in `docs/spec/README.md`.
- No active spec describes an implemented subsystem as merely planned or
  draft.
- `TODOs.md` contains no completed checklist history.
- Active navigation does not reference removed design or milestone documents.
- `git diff --check`, the documentation audit, and the project test/type gates
  pass.
