# Backlog

## Inbound collaboration request bridge

- Define the stable request contract for work addressed to `hermes-agent`.
  - Required fields: request id, source project, title, body, priority, status, updated timestamp.
  - Decide whether Agent Board entries or request records are the canonical trigger source.
- Choose the invocation mechanism.
  - Poll collaboration REST from a Hermes monitor.
  - Consume Agent Board search results.
  - Add a future webhook/event source from collaboration.
- Extend local deduplication and inbox state beyond the first JSON-backed milestone.
  - Track updated timestamps if collaboration request edits need to retrigger notifications.
  - Keep avoiding repeated notifications for unchanged requests.
  - Decide whether JSON-backed local inbox state should move into Hermes state DB when pending actions exist.
- Define the next user-facing approval behavior.
  - Start from the local pending inbox item created by `/collab monitor run inbound`.
  - Draft a local pending action without posting it.
  - Invoke a constrained Hermes prompt only after user approval.
- Define the safety boundary for writeback.
  - Keep collaboration writeback unavailable until an approval-gated action flow exists.
  - Require explicit approval before responding, closing, reassigning, changing priority, or sending notices.
- Add observability and acceptance checks.
  - Log bridge detections and skipped duplicates.
  - Smoke test: create request to `hermes-agent`, verify Hermes surfaces it once, approve a draft, then post response in a later write-enabled phase.
