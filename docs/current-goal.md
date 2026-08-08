# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — seal structured activity delivery and frontend rendering boundaries.

## Objective

Finish the current Tool/log architecture with explicit activity naming,
identity-safe delivery, and an end-to-end frontend contract test.

## Next Steps

1. Specify durable persistence, live activity delivery, and frontend visibility.
2. Rename the Tool outcome live callback to an explicit activity sink.
3. Deduplicate repeated delivery of one `LogEvent` identity at the broker.
4. Cover Tool execution through wire decoding and TUI rendering.
5. Run full validation, commit in bounded steps, and update PR #4.

## Exclusions

- Do not introduce a new event bus, frontend abstraction, or effect phase model.
- Do not rename persisted event identities or change their wire schema.

## Completion Evidence

- One event identity is queued at most once per activity subscription.
- A decorated Tool outcome survives broker and wire transport and is rendered
  from the decoded `LogEvent` by the TUI.
- Full pytest, Pyright, build, wheel smoke, and diff checks pass.
