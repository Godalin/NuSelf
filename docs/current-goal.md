# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Deliver the v0.3.1 scoped-authority architecture so an installed NuSelf uses
durable user-owned state by default while explicit workspaces remain isolated.

## Active Branch

`feature/scoped-authorities`

## Ordered Work

1. [complete] Define user/workspace scope, configuration layering, daemon
   identity, and legacy-layout migration in the governing specifications.
2. [complete] Introduce one scope resolver and immutable runtime-path model; remove
   implicit repository-root path selection.
3. [complete] Layer user and workspace configuration while selecting exactly one state
   authority per invocation.
4. [in progress] Add explicit CLI scope selection, initialization, path inspection, and
   legacy `private/` migration.
5. Isolate daemon lifecycle and transport resources by authority identity.
6. Migrate all composition roots and domain callers, then update public
   documentation and v0.3.1 release metadata.
7. Run the complete local and six-platform release gates, integrate coherent
   commits, publish, and verify the final release.

## Out Of Scope

- Automatic parent-directory workspace discovery.
- Queries or writes spanning more than one state authority.
- Local records that shadow or delete user-scope records.
- A single daemon serving multiple authorities.
- Package-manager publication, including Homebrew; v0.3.1 only makes the
  installed runtime layout suitable for separately authorized publication.

## Completion Evidence

- Approved scope/authority contracts are recorded in `docs/spec/scope.md`.
- Scope/path and layered-config tests: 41 passed; focused Pyright reported
  0 errors and 0 warnings.
- User/workspace CLI selection, `init`, `dev paths`, layered `dev config`, and
  authority-root chat/config tests: 245 passed. Full-source Pyright remains at
  0 errors and 0 warnings.
- Pending: CLI/migration and daemon-isolation regression suites.
- Pending: complete pytest, Pyright, build, clean-wheel smoke, and release CI.
