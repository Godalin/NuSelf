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

1. **QA**: Run integration checks and manual REPL verification to confirm both chat and reflection use the shared discussion system end-to-end.
2. **Docs**: Keep README, README.zh-CN, current-goal, and the new CLI behavior spec synchronized with the shared discussion design.

### Recently Done

- Fixed duplicated status tag in `reflection list` output.
- Redesigned `reflection show` discussion trace as grouped per-turn persona utterances.
- Wrote `docs/cli-behavior-spec.md` as the system-wide CLI/REPL/logging behavior contract.
- Fixed `reflection list` to show only `persona_discussion` outcomes by default; replaced `--include-started` with `--include-all` to reveal scheduler internals.
- Established `docs/spec/` as the authoritative behavioral spec directory; codified "design before implement" and "no spec drift" constraints in AGENTS.md.

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
