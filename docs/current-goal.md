# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make reflection schedule state strictly validated, atomically persisted, and
fail-closed so corruption cannot silently disable cooldown or daily-cap gates.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. [x] Audit all readers and writers of `last_reflection.json`.
2. [x] Specify a versioned authoritative schedule-state record.
3. [x] Replace duplicate permissive readers with one strict decode boundary.
4. [x] Fail closed with a payload-safe diagnostic when state is corrupt.
5. [x] Write schedule state atomically after a reflection is published.
6. [x] Run focused/full tests, type checking, and formatting checks.
7. [x] Update user-facing docs/changelog and commit this stage.

## Out Of Scope

- Changing quiet hours, cooldown, interval, jitter, or daily-cap policy.
- Reconstructing a corrupt schedule record from reflection history.
- Changing reflection candidate generation or relevance policy.
- Migrating other runtime state records in this same commit.

## Completion Evidence

- Valid schedule state preserves cooldown, interval, and daily-cap behavior.
- Missing state still means no reflection has yet been published.
- Malformed JSON, invalid timestamps/dates, booleans as counts, negative counts,
  partial records, and unsupported versions block scheduling with a structured
  corruption diagnostic.
- The relevance gate treats corrupt state as cooldown-active rather than
  silently allowing a candidate.
- State updates use atomic replacement and include a schema version.
- Focused reflection tests, full pytest, Pyright, and `git diff --check` pass.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Continue auditing remaining runtime checkpoints and derived state for strict
validation, atomic recovery, and observable failure behavior.
