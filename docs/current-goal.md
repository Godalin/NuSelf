# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make manual Ctrl-C and Ctrl-D control flow deterministic across NuSelf's CLI:
an interrupted in-flight operation must release its transport and owned
execution resources before the REPL continues or the process exits, and every
real session exit must run the existing transcript, curator, and storage
cleanup boundaries exactly once.

## Active Branch

`main`

## Ordered Work

1. Specify prompt cancellation, in-flight cancellation, EOF exit, watch-loop
   stop, and outer process cleanup semantics.
2. Add cooperative cancellation to owned interactive sends and daemon socket
   requests; close activity subscriptions before returning control.
3. Normalize interactive prompts and bounded loops so Ctrl-C/Ctrl-D cannot
   bypass their owner cleanup.
4. Add focused lifecycle, transport, and regression tests.
5. Run targeted tests, Pyright, the full suite, build, and clean-wheel smoke.

## Out Of Scope

- Cancellation of provider SDK calls that do not expose a cooperative
  cancellation API; NuSelf still owns and closes its surrounding resources.
- Changing daemon SIGINT/SIGTERM shutdown ordering, which already has a
  dedicated signal owner and ordered cleanup contract.

## Completion Evidence

Pending.
