# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — simplify all cross-module interaction behind explicit APIs.

## Objective

Remove the confirmed module-boundary bypasses without introducing a service
bus, compatibility forwarders, or interface-per-method abstraction. Keep one
application composition path, move cross-domain policy out of repositories,
and pass narrow typed capabilities or immutable DTOs at real domain edges.

## Ordered Steps

1. Tighten application and process composition so initialized commands borrow
   one graph and do not reopen storage or repositories.
2. Replace raw data mutation with domain-contributed admin capabilities.
3. Replace graph-shaped conversation projection and reflection's concrete
   foreign dependencies with narrow DTO/Protocol inputs.
4. Move candidate/profile and memory/persona routing out of repositories and
   inject resolved model/config collaborators.
5. Type daemon task definitions without changing the single scheduler, remove
   private evaluation construction, and strengthen executable boundaries.
6. Update documentation, run complete local gates, commit in coherent slices,
   push once, and verify final CI.

## Exclusions

- No general-purpose dependency injection container or message bus.
- No duplicate legacy/facade construction path or compatibility shim.
- No abstraction for calls that stay entirely inside one domain.
- No redesign of storage schemas unless removal of a bypass requires it.

## Completion Evidence

- Feature adapters cannot obtain raw storage or construct domain repositories.
- Cross-domain production imports are DTOs or consumer-owned capabilities;
  repository implementations remain domain/application-private.
- Conversation projection uses a committed-turn DTO, reflection receives all
  foreign capabilities, candidate persistence owns no profile policy, and
  daemon tasks have one typed catalog.
- The audit backlog item is removed; Pyright, full pytest, build,
  clean-wheel smoke, and final six-platform CI pass.

## Previous Completed Evidence

The conversation/knowledge API refactor is complete in `377a65e`:

- `ApplicationGraph` owns a bounded, read-only conversation history service;
  reflection consumes immutable excerpts rather than conversation storage,
  state, locks, or schema.
- Completed turns cross into memory only through a generic durable observation
  API. Curator recovery, plans, locks, daemon scans, and manual updates are all
  observation-owned and no longer scan conversations.
- Schema v7 preserves unprocessed v6 evidence. The project-local database was
  migrated with its pre-v7 backup retained; `PRAGMA quick_check` returned
  `ok`, conversations remained readable, and old cursors became observations.
- Pyright completed with 0 errors and 0 warnings; all 2436 tests, lock check,
  sdist/wheel build, supported-Python clean-wheel install, import, and CLI
  smoke tests passed. Final remote CI remains the branch push gate.

## Previous Completed Evidence

The v0.3.1 persistent-conversation refactor is complete in `e656b19`:

- `conversation`, `session`, and `turn` now have distinct contracts; reason
  threads retain their separate `reason_id` identity.
- Neutral conversation state/storage is owned once by `ApplicationGraph`, so
  memory and reflection no longer import the chat agent implementation.
- Reversible schema v6 migration preserves records and rejects collection
  collisions atomically. The project authority migrated from v5 to v6 with a
  retained pre-migration backup and `PRAGMA quick_check = ok`.
- Replies commit and render before compression; daemon memory curation and
  compression share the conversation resource with curation ordered first.
- Turn completion records bounded stage durations and context counts without
  prompt, message, memory, or summary content.
- Pyright completed with 0 errors and 0 warnings; 2439 tests and both sdist and
  wheel builds passed. Final remote CI remains the release-branch push gate.
