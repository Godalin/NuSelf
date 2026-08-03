# Delivery Spec

## Purpose

Delivery presents an Inbox item through external channels. It owns adapter
selection, at-most-once attempt state, recovery, and operational audits. It
does not own user-attention status or source-domain content.

## Record Contract

Each `DeliveryRecord` references one Inbox item and stores a frozen ordered
adapter plan plus one state per adapter. Adapter states are `pending`,
`delivering`, `sent`, `failed`, or `uncertain`; aggregate record states are
`pending`, `sent`, and `failed`.

The Inbox item supplies title, summary, deep link, and originating runtime
context when delivery runs. Delivery records do not duplicate those fields.
A missing Inbox item is a failed invariant and causes no external effect.

## Pipeline

Delivery requests are idempotent by Inbox item ID. Before each external effect
the adapter state is durably changed to `delivering`; the known result is
persisted immediately afterward. Interrupted attempts become `uncertain` and
are not replayed automatically. A frozen adapter identity missing from current
configuration is recorded as failed.

The daemon scheduler polls pending Delivery records. CLI/REPL `inbox send`
uses the same composition and state machine. Delivery success never changes an
Inbox item to read, dismissed, or resolved.

## Adapters

Built-in adapters are `macos`, `email`, and `log`. macOS uses `osascript`; email
uses validated unified email configuration; log is the fallback when no
external adapter is enabled. Adapters receive an immutable Inbox item and
return only delivery success. They never write Inbox or source-domain state.
