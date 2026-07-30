# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Close the remaining v0.3.0 release blockers by making canonical SQLite
creation migration-owned, exercising the real v0.2.5 authority switch, and
finishing strict finite-number and JSON Schema dialect validation.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Replace the ambiguous SQLite factory with an existing-file opener and a
   migration-private creator; make `dev db-schema` inspect only the active
   backend and fail without publishing authority.
2. Upgrade the frozen v0.2.5 fixture through the atomic migration boundary,
   reopen it through automatic authority selection, and verify current domain
   repositories plus rejection of renewed file authority.
3. Reject non-finite configured numbers and validate the published schema with
   the dialect it declares.
4. Run focused and complete local gates, build and smoke-test the wheel, then
   push the functional commits and require the six-platform CI matrix.
5. Return this board to idle only after every release-preparation result is
   recorded in Git.

## Out Of Scope

- Stable `v0.3.0` promotion, release metadata, merging to `main`, tagging, and
  package publication remain separate explicitly authorized release actions.
- Global plus directory-local configuration and package-manager publication
  remain deferred in [`TODOs.md`](TODOs.md).
- Existing documented semi-durable ThreadStore follow-ups remain deferred.

## Completion Evidence

- SQLite creation is now migration-private and limited to unpublished
  temporary databases; runtime and direct backend opening require an existing
  regular file. `dev db-schema` reuses the CLI-owned active backend and fails
  on file authority without creating canonical SQLite or hiding an existing
  record. The frozen v0.2.5 fixture now loads its historical config, migrates
  through the exclusive atomic authority switch, reopens through
  `auto_backend()`, decodes every current repository record, and proves file
  authority cannot be reacquired. Focused release-storage verification:
  135 passed; locked Pyright reported 0 errors and 0 warnings.
- Every strict configuration model now rejects non-finite numbers, with YAML
  regressions for positive infinity, negative infinity, and NaN across both
  provider and chat timeout fields. Published-schema tests select and check
  the validator from the document's declared Draft 7 dialect before comparing
  acceptance. Focused configuration verification: 44 passed; locked Pyright
  reported 0 errors and 0 warnings.
- The final combined gate, wheel smoke test, push, and six-platform CI remain.
