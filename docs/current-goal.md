# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — provenance chain and memory-formation observability.

## Objective

Establish a resolvable conversation/reason → memory → reflection provenance
chain, emit one structured event whenever durable memory is formed, and show a
safe evidence/decision explanation in reflection notifications.

## Next Steps

1. Specify stable evidence references, projection ownership, and rendering.
2. Connect chat and reason evidence through memory observations and traces.
3. Propagate validated evidence into reflection traces and notifications.
4. Add compatibility and integrity coverage, then update user documentation.
5. Run the full validation matrix, review the diff, and merge a feature PR into
   `dev/v0.4.x`.

## Exclusions

- Do not persist or expose hidden model chain-of-thought.
- Do not fabricate provenance for legacy records whose sources cannot resolve.
- Do not make logging, trace, or notification projection failure roll back an
  already committed domain artifact.
- Do not change source documents or their read-only ownership.

## Completion Evidence

- New chat and reason observations retain a resolvable source artifact and
  produce a linked memory trace when curation creates or updates memory.
- New reflections cite only validated context references; their traces and
  notification bodies render the same bounded evidence and decision chain.
- Every committed memory formation emits one structured memory log event with
  safe IDs/action/type/source metadata and no private body text.
- Focused integration tests, the complete unit suite, Pyright, documentation
  checks, and diff review pass in the feature PR.
