# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

In progress — remove flat production modules from the package root.

## Objective

Move every substantive `src/nuself/*.py` module to its real owner package,
using precise single-word filenames. Migrate all callers without package-root
facades, aliases, or forwarding modules; leave only `nuself/__init__.py` at the
source root.

## Next Steps

1. Move LLM endpoints into `agent`, clock/handles into `runtime`, and private
   filesystem primitives into `storage`.
3. Move evaluation into `evaluation` and release gates into testable `scripts`
   tooling rather than the production wheel.
4. Audit imports and built contents, run full gates, commit coherent batches,
   return this file to Idle, and stop.

## Exclusions

- Preserve configuration schemas, scope resolution, endpoint behavior,
  evaluation results, filesystem security, CLI behavior, and release checks.
- Do not split cohesive implementations merely to shorten files.
- Do not add package-root re-exports, compatibility modules, or generic
  `common`, `helpers`, `utils`, or `model` owners.

## Last Verification

- Initial audit found eight substantive root modules: `clock`, `config`,
  `eval`, `handles`, `llm`, `private_fs`, `release_gate`, and `scope`.
- Each has a concrete existing or minimal owner: runtime, config, evaluation,
  agent, storage, or scripts. No root module needs to remain a public facade.
- Config/Scope batch: settings and scope resolution now live in the empty-root
  `config` package. Full Pyright reports 0 errors and 0 warnings; 145 focused
  configuration, readiness, lifecycle, and composition tests pass.
