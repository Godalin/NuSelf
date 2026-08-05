# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — modularizing structured Tool effects.

## Objective

Represent Tool side effects as orthogonal decorator declarations composed in
one ToolSpec and interpreted by one execution runtime. Approval is the first
suspending interaction effect; observation and audit are projection effects,
while read/write remains an execution classification.

## Next Steps

1. Define the Tool effect model, phases, and generic continuation protocol.
2. Migrate decorators and FeatureExecutor to composable effect declarations.
3. Replace approval-specific Agent, daemon, Conversation, and CLI state with
   generic Tool effect request/resolution and turn continuation contracts.
4. Cover effect composition, exact checkpoint resume, projections, restart and
   cancellation cleanup, and service-only Tool boundaries.
5. Run full verification, commit in stages, and return to Idle.

## Exclusions

- Do not move terminal, daemon, LangGraph, or storage behavior into decorators.
- Do not expose repositories or bypass domain services from Tool functions.
- Do not use logs as executable effect requests or resolutions.
- Do not retain parallel approval-only and generic effect protocols.

## Completion Evidence

- ToolSpec contains a canonical collection of independently declared effects.
- One interpreter executes interaction gates and projection effects in defined
  phases without decorators owning runtime behavior.
- Agent/daemon/CLI transport generic Tool effect requests and resolutions;
  approval-specific cross-layer state and ContextVars are absent.
- Conversation continuation is generic and cannot bypass unfinished-turn
  protection without a matching saved Agent continuation.
- Full pytest, Pyright, and `git diff --check` pass.
