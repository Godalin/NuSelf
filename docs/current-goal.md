# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Fix background reflection system to properly generate proactive ideas. Ensure daemon threads start correctly and reflection candidates are generated with high-quality insights.

## Immediate Context

- ConfigSystem unified and merged to main.
- Daemon server correctly starts 3 background threads: memory_curator, reflection_scheduler, notification_delivery.
- IdeaCandidateGenerator may be failing silently (catches RuntimeError/ValueError/JSONDecodeError).
- Possible root causes:
  1. API key not configured → uses LocalFallbackLLM (low-quality output)
  2. Memory/threads/sources empty → `context.is_empty()` → no candidates
  3. Default LLM initialization fails → silent catch
  4. Thread startup error not logged → threads die silently

## Next Steps

1. **Diagnose**: Add logging to daemon thread startup and reflection cycle execution
2. **Fix API Key Handling**: Ensure API key is always available (error earlier if missing)
3. **Add Fallback Strategy**: When LocalFallbackLLM is used, provide visible warning in logs
4. **Improve Error Reporting**: Log failures in reflection, not silently catch them
5. **Validate Context Collection**: Ensure memory/threads/sources are being read correctly

## Not Now

- New reflection strategies (Phase 4).
- LLM-less reflection (Phase 3).
- Hot reload of reflection config.

## Completion Criteria

- Daemon logs show reflection checks running continuously.
- When API key missing, system logs clear warning.
- Failed candidates logged with reason (empty context, low score, etc).
- At least 1 test validates end-to-end daemon reflection cycle.
