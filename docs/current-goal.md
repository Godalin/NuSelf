# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. The Unix socket request/response adapter has been extracted from the
daemon process runner.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- `daemon/socket_server.py` owns the typed Unix server state, bounded frame
  read/write, request decoding, registry invocation, protocol/IO/unexpected
  exception translation, and response-delivery observation.
- The socket adapter depends only on structural `DaemonRequestState`; it does
  not import `DaemonState` or the daemon process runner.
- `daemon/server.py` selects the adapter while retaining socket path, loop,
  signal, worker, and cleanup ownership. It no longer implements or re-exports
  request transport or registry dispatch.
- Transport, activity, and business-handler tests import and patch their actual
  owning modules instead of relying on accidental server exports.
- `daemon/server.py` decreased from 582 to 459 lines.
- Focused transport/server/instance/payload/activity tests: 70 passed.
- Final full tests: 1270 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Continue daemon lifecycle composition review or resolve the REPL presentation
contract.
