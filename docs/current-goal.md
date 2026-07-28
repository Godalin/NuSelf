# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. Memory curator, optimizer, and intake all use the shared
framework-native structured-agent boundary with no text response protocol.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- Curator and optimizer inject `StructuredAgent` with their exact output
  schema and use LangChain `SystemMessage`/`HumanMessage` prompts.
- Both accept only typed action batches from the shared runner before domain
  conversion and candidate dispatch.
- JSON instructions, fenced-text extraction, `model_validate_json`, parser
  helpers, `ChatLLM`, and `llm=` injection are removed from production paths.
- Existing strict schema, complete-batch rejection, cursor, auto-accept, and
  pending optimizer candidate semantics remain covered.
- Focused curator and optimizer tests: 44 passed.
- Final full tests: 1453 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

Push is authorized; completed review batches are published immediately after
their validated commit.

## Next Review Batch

Audit reflection scheduler generated-output boundaries.
