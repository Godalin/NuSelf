# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — unifying application Service exposure names.

## Objective

Expose each domain's single public Service directly under its domain name,
retain resource snapshots only for genuine multi-capability domains, and make
Persona Tool builders consistently accept `service=`.

## Next Steps

1. Update the governing boundary specification.
2. Flatten Memory, Reason, and Reflection Service fields in `ApplicationGraph`.
3. Rename Persona Tool builder service parameters and migrate all callers.
4. Add architecture guards and run full verification.
5. Commit in stages and return this file to Idle.

## Exclusions

- Do not flatten `trace`, whose query and recorder are distinct public
  capabilities sharing one authority.
- Do not rename internal constructor parameters where `_service` distinguishes
  a dependency from other state.
- Do not add compatibility aliases or a service-locator API.

## Completion Evidence

- `ApplicationGraph` exposes `memory`, `reason`, and `reflection` directly as
  their Service types.
- No process adapter uses `memory_service`, `reason.service`, or
  `reflection.service` graph access.
- Persona Tool builders and callers use `service=` terminology.
- Architecture tests, full pytest, Pyright, and `git diff --check` pass.
