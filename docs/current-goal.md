# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Milestone 8 (Lightweight Multi-Agent Selves) is complete. All bounded personas, routing, synthesis, durable instruction memory, and synthesizer-as-voice work is done.

The next open question is whether to break the Not Now boundary for proactive reflection (Milestone 10), continue with memory system polish, or move toward the first usable interface polish (Milestone 13).

## Immediate Context

- Persona activation, routing, and synthesis are fully wired.
- Synthesizer generates the user-facing response on activated turns.
- Persona instructions can be stored and loaded from durable memory.
- Evaluation harness with golden fixtures and offline scoring exists.
- Thread management (create, rename, branch, archive, open) is complete.
- All existing tests pass and pyright reports zero errors.

## Next Steps (TBD)

Pending direction. Options:

1. **Break Not Now boundary**: Start Milestone 10 (proactive reflection scheduler, idea candidates, relevance gate, notification outbox).
2. **Memory system polish**: Add vector/hybrid/graph indexes, advanced retrieval, or memory system hardening.
3. **Interface polish**: Improve CLI UX, REPL experience, or error handling for Milestone 13.
4. **Architecture cleanup**: Refactor boundaries, remove dead code, or improve test coverage in under-tested areas.

## Not Now

- Full multi-persona orchestration beyond the current bounded skeleton.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Proactive reflection or notification work.
- Web or GUI interface work.
- Private memory schema migration.
- Dashboard-style or dependency-heavy terminal UI.

## Completion Criteria

- Direction chosen and documented in this file.
- Implementation follows the chosen direction.
- All operations are type-checked and tested.
- README TODOs track completed progress, while this file stays limited to the active goal.
