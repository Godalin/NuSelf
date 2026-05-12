# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus
Polish the shared competitive discussion system so chat and background reflection continue to use the same strategy, with clear host-driven escalation and readable traces in the REPL and logs.

## Immediate Context

- Reflection scheduler and daemon startup are functioning.
- Reflection checks are now less noisy by default.
- Chat and reflection currently share the same persona primitives (`PersonaGraphDriver`, `PersonaTurnState`, persona definitions) but have different triggers and surfacing.
- The shared discussion service is already in place; the next work is polish, validation, and any remaining logging clarity.
- There is no fallback toggle for discussion entry; the host persona is the sole decision-maker for escalation in chat.
- Root `private/config.yaml` should be treated as the live user config file.

## Next Steps

1. **QA**: Run integration checks and manual REPL verification to confirm both paths use the shared system.
2. **Logging polish**: Tighten host decision and discussion trace rendering if any gaps remain in the interactive experience.
3. **Docs**: Keep README, README.zh-CN, and this file synchronized with the shared discussion design.

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
