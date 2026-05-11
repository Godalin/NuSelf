# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Unify all system configuration into a single `config.yaml` replacing scattered `.env`, `reflection_config.yaml`, and hardcoded defaults. Implement ConfigSystem loader with environment variable overrides and remove obsolete compatibility layers.

## Immediate Context

- New `ConfigSystem` class loads unified `config.yaml` with env variable overrides.
- Config hierarchy: env vars > `private/config.yaml` > `examples/private/config.yaml` (for tests) > hardcoded defaults.
- Reflection scheduling and persona discussion now only accept `ReflectionSettings` from `ConfigSystem`.
- Chat.py, llm.py, daemon/server.py now use ConfigSystem instead of scattered legacy config helpers.
- 545+ tests pass; need validation of config loading path.

## Next Steps

1. Run tests to validate ConfigSystem migration.
2. Update test fixtures to use `ReflectionSettings` and unified config helpers only.
3. Migrate email.toml config into config.yaml section.
4. Update CLI documentation to show config.yaml examples.
5. Remove stale references to `.env` and `reflection_config.yaml` in docs/tests.

## Not Now

- LangMem integration (Phase 4).
- Vector/hybrid indexes (Phase 3).
- Hot reload or live config updates.
- Config UI or interactive editor.

## Completion Criteria

- All core config reads use SystemConfig.
- Tests pass with new config system.
- Config file loading documented with examples.
- All new code passes `uv run pytest` and `uvx pyright`.
