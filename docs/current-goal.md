# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Configuration system for tuning proactive reflection scheduling and other high-level parameters. Allows users to adjust reflection frequency, daily caps, thresholds, and moderator policies without code changes.

## Immediate Context

- `ReflectionScheduler` currently has fixed hardcoded parameters (interval, daily_cap, cooldown, jitter, quiet_hours).
- Users cannot easily adjust reflection aggressiveness or tune policy thresholds.
- Configuration needs to be file-based (TOML in `private/reflection_config.toml`), loaded on daemon startup, and applied to the scheduler and related components.
- 522 tests pass, pyright clean; reflect/proactive modules have passing tests.

## Next Steps

1. Design configuration schema (TOML format): scheduler params (interval, daily_cap, cooldown, jitter, quiet_hours), gate thresholds, moderator policies.
2. Implement `ReflectionConfigLoader` in `src/nuself/config_reflection.py` to read and parse TOML.
3. Update `ReflectionScheduler` constructor to accept a config object and apply parameters.
4. Update daemon `LifecycleManager` to load and pass config when instantiating scheduler.
5. Add fixtures for test configs and unit tests for loader and scheduler binding.
6. Update `README.md` and `README.zh-CN.md` with config usage example and available parameters.
7. Commit feature code and docs separately.

## Not Now

- Global unified config system (focus on reflection config first).
- Hot reload or live update of config.
- Config UI or interactive editor.
- Config schema versioning or migration logic.
- Encrypted credential storage in config.

## Completion Criteria

- `private/reflection_config.toml` is read on daemon startup.
- `ReflectionScheduler` uses config parameters instead of hardcoded values.
- Custom config adjusts reflection frequency in tests.
- All new code passes `uv run pytest` and `uvx pyright`.
- `README.md` and `README.zh-CN.md` include configuration section with example.
