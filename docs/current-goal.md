# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make reason-output section planning fallback observable. A semantically invalid
typed agent plan must still return the deterministic section plan while
recording one sealed degradation event; diagnostic failure must not replace the
fallback.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Scan production exception handlers that return defaults or continue.
2. Separate normal absence, already-observed fallback, and silent degradation.
3. Verify curator and optimizer deferred paths already emit structured audits.
4. Specify a closed Reason audit for section-plan fallback.
5. Report semantic planner failure without changing deterministic planning.
6. Run focused and full quality gates, commit by functional boundary, and push.

## Out Of Scope

- No fallback for agent runtime/unavailability errors currently propagated for
  job retry.
- No change to deterministic section planning.
- No step contents, generated section text, or prompt data in diagnostics.
- No process-global planner or audit hook.

## Completion Evidence

- Memory curator and optimizer agent/validation fallback returns `deferred` and
  is already followed by `curator_deferred` or `optimizer_deferred` audit.
- Expected parser/display defaults and missing-file paths in the scan are
  documented normal absence, not degraded capabilities.
- The injected reason section planner catches semantic `ValueError` from plan
  materialization and silently returns deterministic `plan_sections()`.
- Existing tests prove complete coverage fallback, but no log distinguishes
  that fallback from a deliberately deterministic planner.
- The sealed Reason audit taxonomy now owns
  `reason_output_section_plan_fallback` with warning level, degraded status,
  required canonical error, and exact `mode` metadata.
- Semantic plan materialization failure reports that event before returning the
  unchanged deterministic plan; agent runtime errors remain authoritative for
  job retry.
- Tests prove the record contains no source content and that terminal
  diagnostic storage failure cannot replace the fallback plan.
- Focused Reason audit, export recovery, and output subagent tests: 117 passed.
- Full suite: 2143 passed.
- Pyright: 0 errors, 0 warnings.
- `git diff --check` passed; static search finds no remaining silent
  `ValueError` return to `fallback_plan`.

## Publication

Observable reason section-plan fallback was implemented in `ee9c4c6`;
milestone publication is pending this goal update and push.

## Next Review Batch

After this boundary is complete, continue reviewing fallback scopes that catch
multiple error classes under one generic outcome.
