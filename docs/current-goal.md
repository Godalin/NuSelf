# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Unify safe exception serialization into daemon wire errors.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit every `DaemonResponse` failure construction path.
2. Define one protocol-layer exception-to-error constructor.
3. Make compact exception-chain output credential-safe by construction.
4. Replace local daemon `str(exception)` wire and audit projections.
5. Preserve stable explicit protocol messages and original control flow.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Explicit `DaemonResponse.fail(..., error: str)` remains available for stable
  protocol-owned text.
- Client retry phase and response status semantics remain unchanged.
- Arbitrary successful payload strings are never treated as diagnostics.

## Completion Evidence

- `DaemonResponse.fail_from_exception(...)` is the protocol-owned constructor
  for safe single-exception or compact-chain wire errors.
- `diagnostic_exception_chain(...)` now owns safe rendering, cause/context
  traversal, duplicate removal, and credential sanitization in
  `runtime.diagnostics`; the former observability formatter alias was removed
  and all internal callers migrated.
- Socket read/parse/handler failures, typed request rejection, activity lookup,
  chat failure, client connection wrapping, and daemon lifecycle audit paths no
  longer serialize exceptions locally with `str(...)`.
- Tests prove broken exception renderers fall back safely and both outer and
  root-cause credentials are absent from daemon response frames and audit logs.
- Focused protocol, daemon, chat, worker, observability, and REPL suites:
  `248 passed`.
- Full test suite: `1641 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `c1962ff`.

## Next Review Batch

Review remaining direct exception rendering in CLI and domain adapters after
daemon wire errors are centralized.
