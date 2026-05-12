# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus
Redesign the proactive reflection and chat persona flows so multi-persona discussion is a shared, observable capability: a single competitive discussion strategy should be reusable from both background reflection and interactive chat, exposing per-person discoveries and a moderator conclusion when appropriate.

## Immediate Context

- Reflection scheduler and daemon startup are functioning.
- Reflection checks are now less noisy by default.
- Chat and reflection currently share the same persona primitives (`PersonaGraphDriver`, `PersonaTurnState`, persona definitions) but have different triggers and surfacing. The near-term goal is to converge their discussion orchestration so the same competitive-style discussion can be invoked from either path.
- Root `private/config.yaml` should be treated as the live user config file.

## Next Steps

 1. **Converge**: Define a single competitive discussion strategy that both `reflection` and `chat` can call (shared API/service).
 2. **Host-driven activation**: Remove special-purpose numeric thresholds as the main trigger; let the host persona (the active persona in chat) decide when to escalate into a multi-persona discussion.
 3. **Immediate visibility**: For interactive chat, emit immediate REPL-level logs when a multi-persona discussion is started: trigger reason, per-person contributions, and the host persona's synthesis/summary.
 4. **Refactor**: Factor `ProactivePersonaDiscussion` into a reusable service interface (adapter pattern) so both reflection and chat can call the same implementation.
 5. **Back-compat**: Keep current reflection behavior working while incrementally switching chat to call the shared discussion service; add config flags to toggle new behavior.
 6. **Tests**: Add unit and integration tests covering chat-triggered discussion, log emissions, and shared-service correctness.
 7. **Docs**: Update README and `docs/current-goal.md` to document the shared discussion design and migration plan.
 8. **QA**: Run integration checks and manual REPL verification to ensure logs and behavior match expectations.

## Not Now

- New reflection strategies (Phase 4).
- LLM-less reflection (Phase 3).
- Hot reload of reflection config.

## Completion Criteria

- Daemon logs show reflection checks running continuously.
- When API key missing, system logs clear warning.
- Failed candidates logged with reason (empty context, low score, etc).
- At least 1 test validates end-to-end daemon reflection cycle.
