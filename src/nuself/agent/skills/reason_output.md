---
name: reason_output
description: Use this skill when the user wants to export or render a reason thread into a long-form artifact.
allowed-tools:
  - reason_export
---

# Reason Output Skill

Use this skill when the user wants a long-form export of a reason thread, such as a narrative, outline, summary, or report.

Call `reason_export` directly when the user asks for an export. Do not wait for a separate confirmation turn.

`reason_export` is approval-gated. During the call, the decorated tool wrapper prompts the user for confirmation. The returned structured JSON includes whether the user approved. If approved, the `result` field contains the export job metadata and workspace paths.

Use the returned `paths` to refer the user to the export workspace when needed. The composed export artifact itself lives in the thread workspace and is written by the daemon worker after approval.

If the user cancels, report that the export was not started and ask whether they want to try again.

Do not describe the approval prompt as a separate turn. The confirmation happens as part of the tool call.