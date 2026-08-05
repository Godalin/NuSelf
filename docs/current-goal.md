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

1. Completed: updated the governing boundary specification.
2. Completed: flattened Memory, Reason, and Reflection Service fields in
   `ApplicationGraph`.
3. Completed: renamed Persona Tool and Reason advancer Service dependencies.
4. Completed: architecture guards and full verification.
5. In progress: commit the implementation and return this file to Idle.

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
- Architecture guards cover direct graph Service names and Persona builder
  parameters.
- `uv run --locked pytest`: 2,335 passed.
- `uv run --locked pyright`: 0 errors, 0 warnings.
- `git diff --check`: passed.
