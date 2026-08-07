# Inbox Spec

## Purpose

Inbox is NuSelf's durable user-attention domain. It answers one question:
"what does the system currently want the user to notice or act on?" It is not
an internal event bus, a job queue, or a copy of another domain's records.

## Item Contract

Each `InboxItem` contains a stable ID, `kind`, source-domain ID, title, summary,
optional deep link, creation time, runtime context, idempotency key, and an
attention status. The source domain remains authoritative for full content and
business transitions.

Statuses are `pending`, `read`, `dismissed`, and `resolved`:

- `pending`: not acknowledged;
- `read`: viewed but still actionable;
- `dismissed`: explicitly ignored;
- `resolved`: the user or source domain completed the matter.

Inbox mutations never mutate Reflection or Reason implicitly. Domain actions
remain available through their owning service APIs.

## Publishers

- Every newly published Reflection creates one `kind=reflection` item.
- Every non-`no_change` Reason step creates one `kind=reason_step` item when it
  contains a question, new finding, new pending item, terminal recommendation,
  or other meaningful progress.
- Future domains publish through `InboxService.add`; they do not access Inbox
  storage directly.

Publishing is idempotent. One source-domain occurrence maps to one Inbox item.
Inbox stores the user-facing title/body snapshot needed for direct display
plus source identity, not the complete source-domain record. A producer must
not replace meaningful user-facing content with a generic lookup instruction.

## Commands

`nuself inbox` and `:inbox` list pending items. The command family owns
`list`, `show`, `read`, `dismiss`, `resolve`, `send`, `watch`, `clear`, and
`stats`. There is no nested Notification command family.

`send` requests or continues Delivery for one Inbox item; it does not resolve
the item. Successful external delivery and user acknowledgement are separate
facts.
