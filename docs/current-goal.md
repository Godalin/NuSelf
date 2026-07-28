# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Prevent memory agent tools from misclassifying repository and programming
failures as user-visible missing-entry results.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Classify broad domain catches by control-boundary ownership.
2. Confirm the repository's typed missing-entry contract.
3. Catch only `MemoryEntryNotFound` in memory mutation tools.
4. Let storage, decode, invariant, and programming failures reach middleware.
5. Verify both missing-entry rendering and unexpected-error propagation.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Tool argument validation remains a concise returned error.
- A genuinely absent memory entry remains a concise returned error.
- Repository save/reindex failures remain authoritative and continue to
  propagate.

## Completion Evidence

- `memory_archive` and `memory_update_importance` catch only the repository's
  typed `MemoryEntryNotFound`.
- Missing entries retain their concise tool result, while injected repository
  `RuntimeError` failures propagate unchanged for both mutation tools.
- Save and reindex remain outside the missing-entry catch and therefore cannot
  be mislabeled.
- A repository-get/broad-catch source search found no equivalent remaining
  pattern.
- Focused chat-agent and middleware tests: `79 passed`.
- `.venv/bin/pytest -q`: `1567 passed` with no warnings.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `a3b88f7`.

## Next Review Batch

Continue classifying broad domain catches, prioritizing non-boundary code that
can hide storage, invariant, or programming failures.
