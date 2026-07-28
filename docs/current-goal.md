# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Eliminate direct caught-exception rendering across the whole codebase.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Classify every remaining direct exception-text use.
2. Separate diagnostic projection from control-flow classification.
3. Define one repository-wide caught-exception rendering rule.
4. Migrate agent, persona, reflection, reason, notification, daemon, and config.
5. Add an architecture test that prevents local rendering from returning.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Original exception objects, explicit causes, retry decisions, and fallback
  eligibility remain authoritative.
- Successful domain strings and subprocess control fields are unchanged.
- Raw exception text may exist only inside the shared safe renderer itself.

## Completion Evidence

- All caught exceptions used for output, fallback, wrapping, tool results,
  metadata, evaluation failures, or persisted status now pass through
  `diagnostic_exception_message(...)` or the sanitized compact-chain helper.
- LLM availability and SQLite compatibility classification use
  `safe_exception_message(...)`, so broken renderers cannot replace control
  flow while original exception objects remain authoritative.
- Subprocess stderr/stdout selected for reason PDF diagnostics is sanitized
  before persistence.
- Agent tools, persona graph/discussion/tools, reflection scheduler/service,
  reason prompt/output, notification evaluation, daemon payload/client, config
  warnings, and storage classification were migrated together.
- The repository-wide AST architecture test rejects direct `str(...)` or
  f-string rendering of any named caught exception.
- Source search finds no direct exception rendering outside the shared
  diagnostic implementation.
- Focused cross-domain and architecture suites: `355 passed`.
- Full test suite: `1646 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `6bfb515`.

## Next Review Batch

Review whether diagnostic metadata values beyond exception text need typed
privacy classification after caught-exception rendering is globally enforced.
