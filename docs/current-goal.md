# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — unify post-chat completion projection.

## Objective

Give CLI and daemon Chat one application service for projecting a committed
turn into Memory, without allowing secondary projection failure to replace an
already persisted assistant reply.

## Next Steps

1. Specify the shared completion boundary and adapter-owned follow-up policy.
2. Add a single-word application completion module and compose its Service.
3. Route one-shot and daemon Chat through it; keep synchronous versus
   scheduled curation/compression decisions in their adapters.
4. Test projection failure, successful follow-up identity, and suspension.
5. Run full validation and merge through a short-lived PR.

## Exclusions

- Moving reply persistence out of `ConversationGraphRuntime`.
- Making curation or compression synchronous in daemon Chat.
- Making one-shot Chat depend on the daemon scheduler.
- Treating observation persistence as successful when it failed.

## Completion Evidence

- CLI and daemon call the same completion Service after a committed result.
- Observation failure emits a typed degradation and does not replace reply.
- Daemon schedules curation only when an observation exists and always retains
  its independent compression policy.
- Full tests, Pyright, builds, and CI pass.
