# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. LangChain typed structured output is now the only reason
step-generation boundary; the manual dictionary response protocol is deleted.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- `ReasonStepOutput` is a strict Pydantic model with domain enums, bounded
  confidence, forbidden extra fields, and typed nested tracked items.
- The advancer accepts only a framework-returned `ReasonStepOutput` instance
  and converts it directly to `ReasoningStep`.
- `step_from_data`, evidence filtering, tracked-item filtering, confidence
  clamping, terminal fallback, and arbitrary `model_dump` acceptance are
  deleted.
- Tests inject typed framework responses and explicitly prove dictionary
  responses are rejected.
- Persisted `TrackedItem` requires a non-empty string label and rejects
  malformed present fields while retaining documented omission defaults.
- Focused reason tests: 117 passed.
- Final full tests: 1420 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Audit other agent subsystems for framework structured-output results that are
reparsed through manual dictionary protocols.
