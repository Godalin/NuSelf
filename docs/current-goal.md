# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus
Redesign the proactive reflection and chat persona flows so they share one competitive discussion system. Background reflection and interactive chat should both be able to call the same discussion strategy, with visible per-person discoveries and a moderator conclusion when appropriate.

## Immediate Context

- Reflection scheduler and daemon startup are functioning.
- Reflection checks are now less noisy by default.
- Chat and reflection currently share the same persona primitives (`PersonaGraphDriver`, `PersonaTurnState`, persona definitions) but have different triggers and surfacing.
- The near-term goal is to improve the shared competitive discussion system itself so both chat and background reflection can use it consistently.
- Root `private/config.yaml` should be treated as the live user config file.

## Next Steps

1. **Shared service**: Refactor `ProactivePersonaDiscussion` into a reusable service interface that chat and reflection can call.
2. **Host-driven activation**: Let the host persona in chat participate in the decision to escalate into a multi-persona discussion.
3. **Immediate visibility**: Keep the discussion trace readable in the REPL and logs for both chat and reflection.
4. **Compatibility**: Keep current reflection behavior working while incrementally switching both entry points to the shared discussion path.
5. **Tests**: Add unit and integration tests covering shared discussion behavior and log emission.
6. **Docs**: Keep README, README.zh-CN, and this file synchronized with the shared discussion design.
7. **QA**: Run integration checks and manual REPL verification to confirm both paths use the shared system.

## Not Now

- New reflection strategies (Phase 4).
- Memory-routing changes for chat discussion outcomes.
- LLM-less reflection (Phase 3).
- Hot reload of reflection config.

## Completion Criteria

- Daemon logs show reflection checks running continuously.
- When API key missing, system logs clear warning.
- Failed candidates logged with reason (empty context, low score, etc).
- At least 1 test validates end-to-end daemon reflection cycle.
