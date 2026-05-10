# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Make proactive multi-persona discussion feel alive: shared scratchpad, iterative rebuttal, and event-driven persona emergence.

## Immediate Context

- Current proactive persona flow is competitive and mostly single-pass: shared candidate input, heuristic selection, one round of contributions, then synthesis.
- `ReflectionScheduler` can already trigger competitive persona discussion for high-value candidates.
- `PersonaGraphDriver` and `ProactivePersonaDiscussion` are the main control points for evolving the discussion model.
- The first slice should add a shared discussion context and at least one rebuttal/synthesis round without breaking existing outbox delivery.
- Keep the change bounded so the current chat/runtime behavior stays stable.

## Next Steps

1. Define a shared discussion scratchpad structure for persona rounds.
2. Extend proactive persona debate to run at least one rebuttal round.
3. Allow the discussion to emit emergent temporary persona instances when a candidate warrants it.
4. Add tests that prove later personas can see earlier discussion context.
5. Keep the existing outbox and daemon delivery path unchanged.

## Not Now

- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Web or GUI interface work.
- Private memory schema migration.
- Dashboard-style or dependency-heavy terminal UI.
- Broad rewrite of the chat runtime persona system before the proactive discussion slice lands.

## Completion Criteria

- Competitive proactive discussions can share intermediate context across personas.
- At least one rebuttal or follow-up round can influence the final synthesis.
- A candidate can spawn a temporary persona-like role when the discussion warrants it.
- Existing daemon, chat, and outbox behavior remains stable.
- All new code passes `uv run pytest` and `uvx pyright`.
