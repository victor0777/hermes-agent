# Findings

## 2026-05-08 — Collaboration visibility now reaches a local inbox but not execution

### Context

Hermes now has read-only collaboration tools for dashboard/request state, knowledge DB search, Agent Board search, and inbound request monitoring.

### Finding

A collaboration request can be addressed to `hermes-agent`, and Hermes can detect it through the inbound monitor, suppress duplicate notifications with local seen state, and persist it as a pending local inbox item for `/collab inbox` review. The bridge still does not convert that request into shared-state writeback, request closure/reassignment, priority changes, or repository-local agent-loop execution.

### Impact

Other projects can leave work for Hermes Agent through collaboration and have it appear in a local read-only inbox, but Hermes will not automatically answer or act on that work until an approval-gated action flow is implemented. Existing collaboration monitors remain deterministic read-only checks, not a generic autonomous request worker.
