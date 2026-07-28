# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make malformed authoritative records observable without making one corrupt
record prevent healthy records from being listed or rebuilt.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. [x] Inventory repository decode-and-skip paths and their existing contracts.
2. [x] Specify corrupt-record isolation, diagnostics, and identity handling.
3. [x] Add one shared repository decode boundary with focused tests.
4. [x] Migrate the highest-risk authoritative repositories in reviewable
   groups.
5. [x] Audit remaining repositories and record the next robustness batch.
6. [x] Run full tests, type checking, and formatting checks.
7. [ ] Commit and push in reviewable stages.

## Out Of Scope

- Rejecting an entire collection because one record is malformed.
- Automatically rewriting or deleting corrupt authoritative data.
- Logging expected missing records or cleanup races as corruption.

## Completion Evidence

- Every migrated skipped record produces a structured warning with collection,
  record identity when recoverable, and compact error detail.
- Healthy records remain readable when one neighboring record is corrupt.
- Diagnostics do not expose complete private record contents.
- Focused tests cover identity-present and identity-missing corrupt records.
- Full pytest, Pyright, and `git diff --check` pass.

## Migration Groups

- [x] Memory entries/candidates, source documents/chunks, and profile items.
- [x] Persona prompts, including thread-scoped legacy files.
- [x] Reason threads/steps.
- [x] Reflection entries and notification outbox.
- [x] Thought traces/links.
- [x] File-backend JSON syntax and top-level shape failures.

## Next Review Batch

Harden daemon reason-export manifest recovery. Manifest/progress read failures
and failed retry-state writes currently have local broad exception fallbacks;
they need explicit durable-state and structured diagnostic behavior without
causing duplicate composition.
