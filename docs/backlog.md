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

## Security Intelligence Intake

- [x] Add read-only security news/CTI/advisory intake for the virtual project security loop.
  - Implements `collect_security_intelligence()` in `tools/collaboration_autonomy.py`.
  - Supports configured RSS/Atom, JSON, and local file sources.
  - Writes a local intake manifest under Hermes home by default: `collaboration/security_intelligence/intake.json`.
  - Records local autonomy evidence event `Detection/security_intelligence_intake`.
  - Returns `blocked` with an explicit blocker when no sources are configured.
  - Exposes `security_intelligence_intake` as a collaboration tool.
  - Adds `/collab security-intel intake [limit]` for manual read-only collection.
  - Adds `/collab security-intel job-spec [schedule]` for no-apply monitor spec review.
  - Provides `security_intelligence_monitor_job_spec()` as a no-apply monitor job template; installing/enabling a scheduler remains an explicit operator action.
- [ ] Configure actual CTI/security advisory sources for the par02 Hermes runtime.
  - Candidate source examples: CISA KEV JSON, vendor RSS feeds, GitHub security advisory feeds, or local curated advisory files.
  - Do not enable policy/rule/runbook application from this intake without a separate apply approval gate.
  - Require explicit approval before responding, closing, reassigning, changing priority, or sending notices.
- Add observability and acceptance checks.
  - Log bridge detections and skipped duplicates.
  - Smoke test: create request to `hermes-agent`, verify Hermes surfaces it once, approve a draft, then post response in a later write-enabled phase.

## Paperclip PM/ops agent integration

- Define the Paperclip integration contract for registering Hermes as a PM/ops agent.
  - Candidate identities: `Hermes-PM` or `Hermes-Ops`.
  - Initial capability scope: read-only project, agent, routine, issue, and report-state inspection.
  - Explicitly exclude Paperclip issue mutation, agent orchestration, dashboard mutation, report posting, and downstream project writes until separately approved.
- Design a read-only Paperclip PM digest.
  - Summarize Paperclip report freshness, absent request context, upstream/downstream blockers, routine health, and agent stall/failure signals.
  - Include local LLM, LiteLLM, Claude-compatible adapter, and tool-use compatibility regressions when they block Paperclip agents.
  - Keep digest output local unless a human approves a report bridge action.
- Design an approval-gated Paperclip report bridge.
  - Draft Paperclip or collaboration reports with stable action IDs.
  - Reuse exact action-ID approval before any shared-state write.
  - Record local autonomy evidence for draft, approval, write, failure, and safety events.
- Define acceptance checks before implementation.
  - Read-only digest can be generated without mutating Paperclip or collaboration state.
  - Denied report drafts leave no shared-state writes.
  - Approved report posts are idempotent and traceable by action ID.
  - Any attempted dashboard, issue, agent, priority, ownership, or downstream mutation is treated as out of scope and escalated.

## Routing and telemetry PM coordination

- Add a read-only gateway/telemetry coordination digest.
  - Track open requests between `llm-gateway`, `llm-routing-telemetry`, `agents`, `auto_researcher`, and `codex-openai`.
  - Summarize stale requests, missing acknowledgements, blocker state, owner handoffs, and due dates.
  - Keep output local unless a human approves a collaboration response draft.
- Track context-guard telemetry integration as a coordination item.
  - Source request: `REQ-20260509-001` from `llm-gateway` to `llm-routing-telemetry`.
  - PM concern: ensure Layer 1/2 context guard canary telemetry gets ingested into weekly reports or dashboards before Layer 3 rolling digest decisions.
  - Watch for required dimensions and metrics: project, host, lane, backend profile, tool, rule ID, action, compression counts, saved bytes/tokens, and false-positive notes.
- Track compression telemetry and continuation-guard requests as coordination items.
  - `REQ-20260507-001`: `llm-gateway` → `llm-routing-telemetry`, context compression `PostToolUse` JSONL ingest/reporting; currently first-response overdue.
  - `REQ-20260427-007`: `llm-gateway` → `auto_researcher`, operator continuation marker injection, progress-detection rules, and telemetry events; currently overdue.
  - `REQ-20260427-015`: `llm-gateway` → `auto_researcher`, transcript-size guard and continuation telemetry; currently overdue.
  - `REQ-20260427-006`: `llm-routing-telemetry` → `agents`, llm-gateway founding split announcement and migration coordination; treat as background context unless owner asks for Hermes help.
- Define Hermes PM handling behavior for cross-project requests.
  - Identify overdue or missing-ack requests and prepare coordination summaries for the user.
  - Draft follow-up text only when the request is low-risk and the owner/project boundary is clear.
  - Do not close, acknowledge, assign, reprioritize, or post cross-project responses without exact human approval.
- Define candidate commands after runbook validation.
  - `/collab pm digest llm-gateway llm-routing-telemetry`
  - `/collab monitor run routing`
  - `/collab coordination draft <request_id>`
- Define acceptance checks before implementation.
  - Digest generation must not mutate collaboration request state.
  - Hermes may suggest acknowledgement or follow-up text, but posting requires exact action-ID approval.
  - High-priority, security, infrastructure, ownership, or priority-change items are escalated rather than automated.
