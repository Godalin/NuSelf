# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — restore structured Tool outcome projection.

## Objective

Restore production `service_tool_called` emission with structured arguments and
result/error while preserving the privacy-safe `tool.activity` lifecycle and
the middleware/effect ownership boundaries.

## Next Steps

1. Specify the immutable Tool outcome and projection ownership precisely.
2. Add an injectable projection boundary and connect it to real framework Tool
   execution without making middleware an event-schema authority.
3. Wire Chat and Reason production runtimes and add real execution-path tests.
4. Run focused and full verification, review the diff, update documentation,
   and append the fix to draft PR #4.

## Exclusions

- Do not put arguments or results into `ObservationEffect` lifecycle events.
- Do not make Tool outcome logs authoritative execution state.
- Do not change approval transport, wire protocol, or domain service behavior.

## Completion Evidence

- A real Tool invocation emits privacy-safe lifecycle plus exactly one
  structured `service_tool_called` terminal outcome.
- Success and failure shapes are tested without duplicate execution.
- Pyright, full pytest, build, wheel smoke, and diff checks pass.
