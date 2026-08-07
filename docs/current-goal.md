# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — deliver structured Tool outcomes across daemon worker threads.

## Objective

Ensure persisted `service_tool_called` outcomes are also delivered to daemon
live activity when Tool execution occurs on a scheduler worker thread.

## Next Steps

1. Replace request-thread ContextVar dependence with an explicitly composed
   live outcome sink.
2. Cover cross-thread persistence and live delivery without duplicate writes.
3. Run full validation and update draft PR #4.

## Exclusions

- Do not move Tool outcome schema into middleware or `ObservationEffect`.
- Do not use audit replay/polling as a live event bus.

## Completion Evidence

- A worker-thread Tool outcome is persisted once and delivered live once.
- Full pytest, Pyright, build, wheel smoke, and diff checks pass.
