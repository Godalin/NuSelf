# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Redesign the proactive reflection dialogue so multi-persona discussion feels closer to a real live debate, with visible per-person discoveries and a moderator conclusion after sufficient depth.

## Immediate Context

- Reflection scheduler and daemon startup are functioning.
- Reflection checks are now less noisy by default.
- Multi-persona discussion still uses a bounded randomized debate flow, so it needs a redesign to better expose live back-and-forth reasoning.
- Root `private/config.yaml` should be treated as the live user config file.

## Next Steps

1. **Design**: Define a more realistic multi-persona debate format with shared transcript visibility
2. **Expose**: Make `reflection show` surface the full persona discussion in a readable structure
3. **Moderate**: Let the moderator summarize and conclude only after enough discussion depth
4. **Tune**: Replace hard-coded participant counts with config-driven or adaptive participation rules
5. **Validate**: Add tests that assert the discussion trace is preserved and readable

## Not Now

- New reflection strategies (Phase 4).
- LLM-less reflection (Phase 3).
- Hot reload of reflection config.

## Completion Criteria

- Daemon logs show reflection checks running continuously.
- When API key missing, system logs clear warning.
- Failed candidates logged with reason (empty context, low score, etc).
- At least 1 test validates end-to-end daemon reflection cycle.
