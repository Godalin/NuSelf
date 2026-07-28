# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Apply the shared agent failure policy to chat persona discussion orchestration.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory remaining agent-backed fallback catches.
2. Confirm explicitly typed reflection, memory, compression, and reason paths.
3. Route chat discussion orchestration through shared failure eligibility.
4. Preserve provider/runtime discussion fallback and audit behavior.
5. Propagate implementation errors without creating a failure answer.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Discussion engine stage-level score/selection/moderator fallbacks remain
  unchanged.
- A recoverable outer discussion failure retains its visible failure appendix.
- Audit persistence remains secondary to a legitimate discussion fallback.

## Completion Evidence

- Reflection scoring/candidate generation, memory curator/optimizer/intake,
  chat compression, reason prompt, and competitive discussion stages already
  use explicit runtime/validation catches rather than catch-all fallback.
- Chat's outer discussion orchestration now checks
  `is_recoverable_agent_failure(...)` before rendering a failure appendix.
- Injected assertion, attribute, and type failures propagate as the exact
  original object and create no persona failure audit.
- Existing recoverable `RuntimeError` discussion fallback and audit failure
  isolation remain covered.
- Focused discussion, persona graph, and proactive-persona tests: `65 passed`.
- `.venv/bin/pytest -q`: `1586 passed` with no warnings.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `a4c3a35`.

## Next Review Batch

Continue classifying normal-result fallbacks after discussion orchestration
uses the shared policy.
