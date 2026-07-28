# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make ordinary repositories share the process-owned default storage backend so
daemon shutdown can close every long-lived SQLite connection it owns.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit repository backend creation and SQLite close semantics.
2. Specify default versus explicitly injected backend ownership.
3. Migrate ordinary repository and persona construction to the default backend.
4. Verify repositories for one root share one backend and reset closes it.
5. Keep explicit backend injection isolated and caller-owned.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Do not change repository domain behavior or collection layouts.
- Keep migration/diagnostic backends explicitly caller-owned.
- Do not make repositories close a shared backend individually.

## Completion Evidence

- Memory entry/candidate/source, profile, reason, reflection, trace,
  notification, and persona construction now use
  `get_default_backend(project_root)` by default.
- Production search leaves `auto_backend()` only in its low-level factory,
  default-registry creation, and the explicitly owned dev diagnostic command.
- Eight repository families for one root obtain the same registered backend.
- `reset_default_backend(root)` closes the SQLite connection used by an
  already-created default repository.
- Explicit `MemoryCandidateRepository(backend=...)` now passes that backend to
  its implicit entry/profile repositories and never consults the registry.
- `.venv/bin/pytest -q`: `1476 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `6682cd2`.

## Next Review Batch

Audit CLI-owned temporary backend closure and process teardown symmetry.
