# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Prevent sealed handler registries from exposing raw handlers that bypass their
compiled middleware chain.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit registry mutation, seal, resolve, and dispatch ownership.
2. Confirm runtime consumers use dispatch rather than raw resolution.
3. Restrict raw resolution to composition time.
4. Verify sealed registries cannot bypass middleware.
5. Preserve unknown-key and dispatch exception behavior.
6. Run full quality gates, commit, and push.

## Out Of Scope

- `resolve()` remains available before sealing for composition inspection.
- `dispatch()` remains the only runtime invocation API.
- Handler and middleware call semantics remain unchanged.

## Completion Evidence

- `resolve()` checks the one-way sealed state before exposing the raw handler.
- A sealed registry raises `HandlerRegistrySealedError` for raw resolution,
  while `dispatch()` still invokes the compiled middleware chain.
- Production search found no runtime consumer relying on
  `HandlerRegistry.resolve(...)`; daemon and REPL use `dispatch()`.
- Duplicate, unknown, unsealed, middleware-order, and original-exception
  behavior remains covered by the registry suite.
- Focused registry, daemon-request, and REPL-dispatch tests: `21 passed`.
- `.venv/bin/pytest -q`: `1613 passed` with no warnings.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `64563f9`.

## Next Review Batch

Continue reviewing handler and internal-message infrastructure after raw
dispatch bypass is closed.
