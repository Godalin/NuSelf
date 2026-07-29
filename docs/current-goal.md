# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make closed handler catalogs a shared typed sealing contract. Daemon and REPL
composition must prove exact registered-key coverage through
`HandlerRegistry`, without local set comparisons or generic `RuntimeError`.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Verify whether direct diagnostic audit construction has the duplicate
   envelope risk fixed in the previous batch.
2. Inventory shared handler users and local catalog completeness checks.
3. Correct the runtime spec's stale claim that argparse bypasses
   `HandlerRegistry`.
4. Specify typed exact-coverage validation at registry sealing.
5. Migrate daemon and REPL composition to the shared coverage contract.
6. Run focused and full quality gates, commit by functional boundary, and push.

## Out Of Scope

- No replacement of argparse parsing or LangChain tool dispatch.
- No process-global handler registry.
- No runtime fallback for incomplete catalogs.
- No compatibility path preserving local completeness checks.

## Completion Evidence

- `report_observed_failure(...)` already constructs exactly one envelope
  through `write_log_event(...)`; it has no duplicate identity, context, or
  mutable-input read.
- Diagnostic envelope construction and persistence intentionally share one
  terminal catch because this reporter must not replace an already-decided
  primary outcome. Moving construction outside would violate that contract.
- Daemon, CLI, and REPL runtime dispatch already use `HandlerRegistry`.
- Daemon and REPL nevertheless duplicate exact catalog coverage with local set
  comparisons and generic `RuntimeError`.
- `runtime-infrastructure.md` incorrectly says argparse is not routed through
  the registry, while implementation and `development.md` show parser-local
  sealed registry dispatch.
- `HandlerRegistry.seal(expected_keys=...)` now validates exact catalog
  coverage before publishing the dispatch table and raises typed
  `HandlerRegistryCoverageError` with immutable `missing` and `extra` sets.
- Failed coverage leaves an unsealed registry repairable; coverage supplied
  again after sealing is still validated without changing the compiled
  dispatch table.
- Daemon request and REPL command composition now use the shared coverage
  contract; their local set comparisons and generic `RuntimeError` paths are
  removed.
- The runtime spec now accurately describes parser-local CLI registry
  dispatch and labels the original problem inventory as historical.
- Focused handler, daemon request, and REPL tests: 29 passed.
- Full suite: 2132 passed.
- Pyright: 0 errors, 0 warnings.
- `git diff --check` passed; static search finds no migrated local coverage
  comparison or legacy mismatch message.

## Publication

Typed closed-catalog handler sealing was implemented in `c948bf7`; milestone
publication is pending this goal update and push.

## Next Review Batch

After this boundary is complete, review handler middleware ownership and
exception translation for the next shared-infrastructure risk.
