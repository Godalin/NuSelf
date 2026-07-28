# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. Chat's LangChain `structured_response` state now requires an actual
`ChatStructuredOutput` instance; dictionary revalidation is deleted.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- LangChain state decoding accepts only `ChatStructuredOutput` for
  `structured_response`.
- Dictionary values are rejected rather than passed through a second Pydantic
  validation path.
- Typed structured state remains authoritative over ordinary message content,
  and visible tool-call protocol text is still rejected.
- The separate no-model plain-text fallback and typed
  `ConversationResponseService` seam are unchanged.
- Focused chat/runtime/daemon tests: 110 passed.
- Final full tests: 1420 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Audit remaining Pydantic structured-output models for coercive/default-heavy
configuration that weakens their framework validation.
