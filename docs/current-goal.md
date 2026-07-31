# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — renaming persistent chat threads to conversations and tightening the
conversation critical path for v0.3.1.

## Objective

Make `conversation` the single name for a persistent, branchable discussion;
reserve `session` for one client runtime and `turn` for one interaction. Safely
migrate existing SQLite data, expose the terminology consistently, make
context-stage cost observable, and move compression after reply persistence
without weakening same-conversation ordering or crash safety.

## Ordered Steps

1. Define the conversation/session/turn boundary, storage migration, runtime
   correlation, compression, and observability contracts.
2. Update governing specifications before behavioral implementation.
3. Rename domain types, repositories, CLI, daemon protocol, scheduler resource
   keys, runtime context, records, tests, and documentation.
4. Add a schema migration that preserves existing conversation data.
5. Commit the completed reply before returning it; schedule compression on the
   same conversation resource and tolerate an uncompressed next turn.
6. Record bounded per-stage duration and context composition metadata without
   logging private content.
7. Run the full release gate, push once, and track final six-platform CI.

## Exclusions

- `session` remains the transient interactive-client concept.
- Reasoning work keeps its separate reason-domain identity in this goal.
- No provider-specific server-side session dependency or general context cache.
- No raw prompt, message, memory, or summary content in timing metadata.

## Completion Evidence

- Existing v0.3.1 conversation records survive migration byte-for-content.
- Public and internal persistent-chat terminology no longer uses `thread`.
- Same-conversation turns remain serialized and immediately durable on success.
- Compression no longer delays delivery of an already committed reply.
- Timing/context metadata is bounded, structured, and payload-safe.
- Focused concurrency, migration, interruption, and recovery tests pass along
  with the full local and six-platform CI gates.
