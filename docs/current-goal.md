# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — reliable Qwen Reflection evidence selection and delivery.

## Objective

Make Qwen Reflection candidates resolve evidence deterministically against the
closed per-invocation catalog without accepting fabricated references, then
prove the complete local Reflection → Trace → Inbox → email flow succeeds.

## Next Steps

1. [Complete] Capture the exact Qwen/catalog reference mismatch without
   logging prose.
2. [Complete] Specify canonical and uniquely resolvable catalog reference
   forms.
3. [Complete] Implement closed-catalog normalization with strict
   unknown/ambiguity rejection and exact prose cleanup.
4. [Complete] Validate focused/full tests and the real local Qwen endpoint;
   confirm full Reflection → Trace → Inbox output and email/macOS delivery.
5. [In progress] Review and merge the feature PR, then return this file to
   Idle.

## Exclusions

- Do not accept a reference that does not identify a supplied catalog entry.
- Do not infer evidence from candidate title/body text.
- Do not expose private context or model prose in diagnostics.
- Do not weaken the canonical references stored in Reflection ThoughtTrace.

## Completion Evidence

- Exact canonical refs remain unchanged.
- A bare artifact ID resolves only when it is the unique suffix of one supplied
  canonical catalog ref; unknown and ambiguous values reject the entire batch.
- Materialized candidates and ThoughtTrace records contain canonical refs only.
- A real local Qwen run persists a Reflection and Trace, publishes Inbox, and
  completes email delivery using the full non-duplicating provenance format.
- Pyright, focused tests, full suite, CI, and diff review pass.
