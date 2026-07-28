# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. The persisted Profile and Source read-model ownership batch is complete.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- `ProfileItem` detaches and freezes tags, source refs, relations, and evidence
  membership.
- `SourceDocument` detaches and freezes tags.
- Both models preserve existing JSON list/dict wire fields and return detached
  containers.
- Focused Profile, Source, and integration tests: 47 passed.
- Full tests: 1237 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Audit remaining repository summary/index read models.
