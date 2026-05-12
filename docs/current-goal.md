# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus
Redesign the proactive chat-and-reflection flow so ideas can surface inside the main chat process, trigger an explicit multi-persona discussion there, and then flow into memory through the chat path. The same competitive discussion strategy should be reusable from both background reflection and interactive chat, with visible per-person discoveries and a moderator conclusion when appropriate.

## Immediate Context

- Reflection scheduler and daemon startup are functioning.
- Reflection checks are now less noisy by default.
- Chat and reflection currently share the same persona primitives (`PersonaGraphDriver`, `PersonaTurnState`, persona definitions) but have different triggers and surfacing.
- The near-term goal is to let the host persona inside chat decide when to escalate into a multi-persona discussion, show the idea and debate result immediately in the REPL, and then let the chat/memory pipeline decide what should become durable memory.
- Root `private/config.yaml` should be treated as the live user config file.

## Next Steps

1. **Host-driven chat**: Let the chat host persona decide when to escalate into a multi-persona discussion, without depending on a separate numeric trigger gate.
2. **Immediate visibility**: Show the idea, multi-persona exchange, and host synthesis in the REPL as soon as chat escalates.
3. **Memory path**: Route the resulting discussion through the chat memory pipeline so useful outcomes can become durable memory.
4. **Shared service**: Refactor `ProactivePersonaDiscussion` into a reusable service interface that chat and reflection can call.
5. **Compatibility**: Keep current reflection behavior working while incrementally switching chat to the shared discussion path.
6. **Tests**: Add unit and integration tests covering chat-triggered discussion, logging, and memory routing.
7. **Docs**: Keep README, README.zh-CN, and this file synchronized with the shared discussion and memory flow.
8. **QA**: Run integration checks and manual REPL verification to confirm the chat route feels natural.

## Not Now

- New reflection strategies (Phase 4).
- LLM-less reflection (Phase 3).
- Hot reload of reflection config.

## Completion Criteria

- Daemon logs show reflection checks running continuously.
- When API key missing, system logs clear warning.
- Failed candidates logged with reason (empty context, low score, etc).
- At least 1 test validates end-to-end daemon reflection cycle.
