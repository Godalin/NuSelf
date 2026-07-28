# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Prevent approval prompt infrastructure and programming failures from being
silently reclassified as user declines.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit approval render, output, input, decision, and callable ownership.
2. Define the one safe-default input condition.
3. Restrict decline fallback to stdin EOF.
4. Propagate render, output, and unexpected input failures unchanged.
5. Verify every failure path leaves the wrapped tool unexecuted.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Any non-yes response remains a normal decline.
- EOF remains a safe-default decline because no approval was received.
- Audit projection remains secondary and cannot alter the prompt decision.

## Completion Evidence

- Approval prompt rendering and both stdout writes execute outside the input
  fallback and propagate their original failures.
- Only `EOFError` from stdin becomes the safe-default declined JSON result.
- Unexpected stdin `RuntimeError` propagates unchanged.
- Render, output, EOF, unexpected-input, and explicit-decline tests verify the
  wrapped callable remains unexecuted.
- Focused approval and chat-agent tests: `78 passed`.
- `.venv/bin/pytest -q`: `1574 passed` with no warnings.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `edbefd5`.

## Next Review Batch

Continue classifying broad domain catches after approval interaction ownership
is explicit.
