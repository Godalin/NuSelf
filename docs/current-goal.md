# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Make proactive multi-persona discussion feel alive: moderator-guided free-form rebuttal, shared scratchpad, and event-driven persona emergence.

## Immediate Context

- Current proactive persona flow is competitive and still more round-shaped than conversational.
- `ReflectionScheduler` can already trigger competitive persona discussion for high-value candidates.
- `PersonaGraphDriver` and `ProactivePersonaDiscussion` are the main control points for evolving the discussion model.
- The next slice should add a moderator persona / host prompt that nudges convergence without forcing a tight round count.
- Keep the change bounded so the current chat/runtime behavior stays stable.

## Next Steps

1. Add a moderator persona / host prompt that nudges personas toward convergence.
2. Loosen the maximum discussion budget so backend reflection can keep talking longer when needed.
3. Keep the shared scratchpad and emergent persona support in place.
4. Add tests that prove later personas can see earlier discussion context and moderation cues.
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
- A moderator persona / host prompt can nudge personas toward convergence.
- Discussion can continue until it converges or hits a loose cap.
- A candidate can spawn a temporary persona-like role when the discussion warrants it.
- Existing daemon, chat, and outbox behavior remains stable.
- All new code passes `uv run pytest` and `uvx pyright`.
