# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

In progress — group runtime infrastructure by owned capability.

## Objective

Replace the flat Audit, Event, Job, Log, and Feature runtime files with compact
owned subpackages, split the oversized log store, and migrate every caller
without compatibility forwarding modules.

## Next Steps

1. Move Job and Event contracts into `runtime/job` and `runtime/event`.
2. Replace top-level `logs.py` and scattered log files with `nuself/log` owners.
3. Move Feature policy and execution into `runtime/feature`.
4. Audit remaining flat files, run full gates, commit each complete boundary,
   return to Idle, and stop.

## Exclusions

- Preserve runtime behavior, persisted and wire schemas, event names, log
  locations, public CLI behavior, and exception semantics.
- Do not add generic `model.py` files where a more precise owner name exists.
- Do not retain old-path aliases, forwarding modules, or import shims.
- Do not move single-owner domain or adapter behavior into runtime.

## Last Verification

- Baseline: Pyright 0 errors, 0 warnings; 2394 tests passed; package build
  succeeded before this goal. A direct strict check of `logs.py` plus the
  complete runtime package also reports 0 errors and 0 warnings.
- Audit package: Pyright 0 errors, 0 warnings; 279 focused audit and boundary
  tests passed; no old Audit source path remains.
