# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Treat legacy persona prompt files as authoritative and make the derived name
index self-validating, atomically rebuildable, and free of stale rename aliases.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. [x] Trace legacy prompt/index save, rename, delete, and lookup behavior.
2. [x] Specify authoritative records and derived-index recovery.
3. [x] Validate name-index shape and equality with healthy prompt records.
4. [x] Rebuild missing, malformed, or stale indexes atomically.
5. [x] Rebuild after save so prompt renames remove old aliases.
6. [x] Run focused/full tests, type checking, and formatting checks.
7. [x] Update user-facing docs/changelog and commit this stage.

## Out Of Scope

- Migrating thread-scoped persona prompts into the primary storage backend.
- Automatically resolving duplicate authoritative prompt names.
- Changing dynamic persona tool commands or lookup precedence.
- Suppressing real prompt/index filesystem I/O failures.

## Completion Evidence

- Missing index is reconstructed from healthy authoritative prompt files.
- Malformed/wrong-shape and stale index projections emit a payload-safe
  corruption event and are atomically replaced.
- Saving the same prompt ID with a new name removes the old name mapping.
- Corrupt prompt records remain isolated and do not enter the rebuilt index.
- Focused persona repository tests, full pytest, Pyright, and `git diff --check`
  pass.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Audit remaining structured LLM fallback parsers and derived-state recovery
boundaries.
