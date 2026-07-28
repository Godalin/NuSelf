# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make `nuself.storage` the sole atomic file-write boundary for runtime JSON and
text state so subsystems cannot diverge on collision and cleanup behavior.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. [x] Audit duplicate atomic writers and direct runtime-state writes.
2. [x] Specify one shared unique-temp, cleanup-on-failure write contract.
3. [x] Move reason manifest, progress, chunk, and combined output writes to the
   shared boundary.
4. [x] Move chat thread and persona prompt JSON writes to the shared boundary.
5. [x] Update daemon export recovery to import the neutral storage writer.
6. [x] Remove all subsystem-local atomic JSON writer implementations.
7. [x] Run focused/full tests, type checking, and formatting checks.
8. [x] Update user-facing docs/changelog and commit this stage.

## Out Of Scope

- Changing persisted JSON schemas or record identities.
- Changing reason output composition, chunking, or retry policy.
- Changing thread locking or persona name-index rebuild behavior.
- Making explicit user-selected export/transcript destinations atomic.

## Completion Evidence

- All migrated writes preserve their exact serialized content and paths.
- Every write uses a unique sibling temporary file and atomic replacement.
- A failed write preserves an existing destination and removes its temporary
  file.
- Concurrent writes do not share a fixed temporary path.
- `rg` finds no local `write_json_atomic` definition outside `nuself.storage`
  and no direct runtime-state writes in the migrated modules.
- Focused storage/reason/thread/persona tests, full pytest, Pyright, and
  `git diff --check` pass.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Audit remaining explicit exports and user artifact writes for documented
partial-file semantics.
