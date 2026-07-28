# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make `HandlerRegistry.seal()` the explicit boundary between mutable
composition and immutable runtime dispatch.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit CLI, REPL, daemon, and shared handler dispatch paths.
2. Specify sealed-only runtime dispatch.
3. Compile middleware chains once when the registry is sealed.
4. Reject dispatch from a partially composed registry.
5. Verify middleware order, exception identity, and immutable dispatch state.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Preserve typed handler signatures and registration order.
- Keep `resolve()` available to composition-time validation and inspection.
- Do not fold argparse's parser-bound adapter into the keyed registry.

## Completion Evidence

- `HandlerRegistry.seal()` compiles one immutable dispatch table from the
  registered handlers and middleware stack.
- `dispatch()` rejects unsealed registries with
  `HandlerRegistryUnsealedError`, preventing runtime use of partial
  composition state.
- Sealing is idempotent, direct `resolve()` remains available for composition
  inspection, and sealed registration/middleware mutation remains rejected.
- Tests prove unsealed dispatch rejection, middleware order, original
  exception identity, and that dispatch does not rebuild middleware chains.
- Focused handler, daemon-request, and REPL-dispatch tests: `20 passed`.
- `.venv/bin/pytest -q`: `1501 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `e621657`.

## Next Review Batch

Audit runtime event publication and log projection ownership.
