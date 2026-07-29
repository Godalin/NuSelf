# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Give operators a safe, typed recovery surface for curator plans. Runtime and
CLI must share decoding/path rules; inspection must be payload-safe, and
discard must require an exact thread plus explicit destructive acknowledgement.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inspect memory CLI grouping, output contracts, and destructive conventions.
2. Extract one plan store shared by curator runtime and operator commands.
3. Add payload-safe `memory plan show <thread>`.
4. Add exact-thread `memory plan discard <thread> --force`.
5. Prove corrupt inspection fails safely and discard leaves cursor/candidates.
6. Run focused and full quality gates, commit by functional boundary, push,
   and confirm development-branch CI.

## Out Of Scope

- No plan, candidate, cursor, or MemoryEntry wire-schema change.
- No automatic plan repair or discard.
- No CLI exposure of action body, title, tags, or model reason.
- No cursor or candidate mutation during plan inspection or discard.
- No bulk/wildcard plan deletion.

## Completion Evidence

- Runtime currently owns plan path construction and decoding as private
  `MemoryCurator` methods, so CLI cannot inspect the same authoritative
  contract without duplication or constructing an agent.
- A corrupt plan safely aborts curation but the error does not provide an
  in-project repair command; operators must locate and edit private files.
- Existing memory commands are already grouped under
  `nuself.cli.commands.memory`; a nested `plan` group preserves that ownership.
- Chosen surface: payload-safe `show` plus exact-thread, force-gated `discard`.
- Plan action/output contracts now live in `memory/curator_contract.py`; typed
  plan storage and corruption handling live in `memory/curator_plan.py`.
  `curator.py` is reduced from 1031 to 694 lines and remains the orchestration
  boundary while retaining compatibility imports for existing callers.
- Runtime and CLI share `MemoryCuratorPlanStore`; no command constructs an
  agent merely to inspect control state.
- `memory plan show` prints only operational identity metadata and deterministic
  candidate handles. Tests prove title, body, tags, and model reason are absent.
- `memory plan discard` requires `--force`, deletes only the exact thread plan,
  and leaves cursor and candidates byte/record-equivalent.
- Missing and corrupt show operations return non-zero; corrupt diagnostics use
  the shared exception sanitizer and include fixed repair commands.
- Focused curator/CLI tests: 42 passed.
- Full suite: 2183 passed.
- Pyright: 0 errors, 0 warnings.
- Exception-presentation guard and `git diff --check` passed.

## Publication

Curator plan diagnostics, explicit repair, modularization, and local validation
are committed in `afd4e69`. Publication and final-push CI are the remaining
gates.

## Next Review Batch

After this boundary is complete, inspect cross-process curator locking so CLI
repair cannot race a daemon curation run.
