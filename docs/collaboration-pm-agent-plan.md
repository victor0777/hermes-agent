# Collaboration PM Agent Plan

## Purpose

Use Hermes Agent as an always-on project-management assistant for `collaboration.ktl.com`.
Hermes should not replace Claude Code for repository-local development work. Its role is to monitor collaboration state, surface neglected work, ask for decisions when needed, and prepare low-risk project-management actions for approval.

## Current Status

Delivered capabilities:

- read-only collaboration client/tool for dashboard, requests, blockers, reports, and project summaries
- `/collab brief` PM summary flow for CLI and guarded gateway use
- deterministic scheduled monitoring for daily briefs, urgent read-only alerts, and inbound request detection
- read-only collaboration knowledge and Agent Board search tools
- local read-only inbox persistence for collaboration requests addressed to `hermes-agent`
- `/collab inbox` review flow for CLI and guarded gateway use
- CLI-only approval-gated response drafts and posting with exact action-ID confirmation
- local end-to-end smoke coverage for inbound request → pending inbox → approved response

Current gap:

- Collaboration MCP/REST can create and store requests addressed to `hermes-agent`.
- Hermes can detect those records, deduplicate notifications, and keep pending local inbox items.
- Hermes still does not automatically close, reassign, reprioritize, or execute repository-local work from those requests.
- Shared-state response writeback exists only through the local CLI approval-gated response flow.
- Runtime invocation remains a future approval-gated phase.

## User-Level Goal

Create a personal PM/operator agent that continuously watches the cross-project collaboration system and helps keep work moving across many projects.

The agent should answer questions such as:

- Which projects need attention today?
- Which requests are overdue or unassigned?
- Which projects have stale reports?
- Which blockers are preventing progress?
- Which items require a user decision?
- What should be handled first?
- What should be closed, reassigned, or clarified?

## Objectives

### 1. Project visibility

Provide a compact daily view of the whole collaboration workspace:

- open high-priority requests
- overdue requests
- stale project reports
- active blockers
- recently changed projects
- projects with no recent activity but open work
- cross-project dependencies that need coordination

### 2. Request triage

Classify incoming or lingering requests into operational buckets:

- urgent
- blocked
- needs clarification
- needs owner assignment
- likely duplicate
- ready for response
- ready to close
- should be escalated to the user

### 3. Decision prompting

When progress depends on human judgment, Hermes should ask concise questions rather than silently letting work stall.

Examples:

- “This request is overdue and has no assignee. Should I ask the target project for a status update?”
- “These two requests appear to overlap. Should I mark one as duplicate candidate?”
- “This project report is stale by 7 days. Should I request a refresh?”
- “This infrastructure-related change may need cybersecurity review. Should I create a review request?”

### 4. Safe automation

Start with read-only monitoring and recommendation drafting. Any action that changes shared state should be approval-gated until the workflow is proven safe.

Read-only actions can be automated. Write actions should be proposed first, then executed only after user approval.

## Primary Use Cases

### Daily operations brief

Hermes produces a daily summary through Telegram, Slack, or CLI:

```text
Daily Collaboration Brief

Needs attention:
- project-a: high-priority request open for 3 days
- project-b: report stale for 8 days

Blocked:
- project-c depends on project-d data contract update

User decisions needed:
- REQ-123: choose whether to reassign to llm-gateway or agents

Suggested next actions:
1. Ask project-a for status
2. Request report refresh from project-b
3. Clarify ownership for REQ-123
```

### On-demand project brief

The user asks Hermes:

```text
/collab project llm-gateway
```

Hermes returns:

- current phase
- open requests
- stale tasks
- blockers
- recent reports
- pending decisions
- suggested next action

### Overdue request monitor

Hermes periodically checks requests and reports:

- requests past SLA
- requests with no response after N days
- high-priority requests without assignee
- blocked requests with no recent update

It sends a short alert instead of a large dashboard dump.

### Request triage assistant

Hermes reviews open requests and proposes actions:

```text
Triage candidates:

- REQ-20260507-001: needs clarification
  Reason: target project cannot act without deciding routing scope.
  Suggested question: “Should this update ADR only, implementation only, or both?”

- REQ-20260507-002: duplicate candidate
  Reason: overlaps with REQ-20260506-004.
  Suggested action: mark duplicate after confirmation.
```

### PM question generator

Hermes detects ambiguous items and asks the user focused questions with choices.

Good questions should be:

- short
- decision-oriented
- tied to a specific request or project
- include a recommended option when obvious
- avoid asking for approval on routine read-only monitoring

### Weekly project-management review

Hermes generates a weekly review:

- projects with repeated stale reports
- requests frequently blocked by the same dependency
- long-running decisions
- projects accumulating open work faster than closing it
- recurring coordination failures

## Non-Goals

Hermes should not initially:

- automatically close requests
- automatically reassign owners
- automatically create high-priority requests
- change project registry entries without approval
- modify infrastructure/security settings
- replace Claude Code for code implementation
- perform autonomous development work across repositories

## Safety and Permission Model

### Automatically allowed

- read dashboard state
- read project summaries
- list open requests
- list overdue requests
- list blockers
- list reports
- generate briefs
- generate triage recommendations
- notify the user with read-only summaries

### Approval required

- create request
- reply to request
- close request
- reassign request
- change priority
- update task state
- write collaboration report
- modify project registry
- send notices to other projects
- make any external/shared-state change

### Strongly restricted

- automatic closure of high-priority requests
- automatic owner/project reassignment
- automatic infrastructure/security request changes
- broad notification blasts
- actions involving credentials, SSH, Kubernetes, systemd, firewall, or sudo

## Proposed Architecture

```text
Hermes Agent
  ├─ Collaboration PM skill layer
  │   ├─ daily brief
  │   ├─ request triage
  │   ├─ project brief
  │   ├─ stale report monitor
  │   └─ decision question generator
  ├─ Collaboration API/tool layer
  │   ├─ dashboard read
  │   ├─ request list/read
  │   ├─ knowledge search
  │   ├─ Agent Board search
  │   ├─ blocker/report/project read
  │   └─ future approval-gated write actions
  ├─ Inbound request bridge
  │   ├─ detect requests addressed to hermes-agent
  │   ├─ deduplicate seen request ids
  │   ├─ persist local pending inbox items
  │   ├─ surface pending work to the user
  │   └─ future approval-gated runtime flow
  ├─ Gateway layer
  │   ├─ Telegram DM
  │   ├─ Slack DM/channel
  │   └─ CLI
  └─ Scheduler layer
      ├─ daily brief
      ├─ overdue monitor
      └─ weekly review

collaboration.ktl.com
  ├─ project registry
  ├─ requests
  ├─ Agent Board
  ├─ knowledge DB / project snapshots
  ├─ reports
  ├─ tasks
  ├─ blockers
  └─ dashboard
```

## Implementation Plan

### Phase 0 — Documentation and scope lock

Deliverables:

- This plan document.
- Explicit distinction between Hermes and Claude Code responsibilities.
- Initial safety policy for read/write actions.

Exit criteria:

- User agrees that Hermes is being built as a PM/operator agent, not a Claude Code replacement.

### Phase 1 — Read-only collaboration client — delivered

Goal:

Add a Hermes-side integration that can read collaboration state from `collaboration.ktl.com` or an equivalent local/MCP-backed wrapper.

Capabilities:

- fetch dashboard
- list open requests
- list overdue requests
- get project summary
- list blockers
- list reports

Implementation options:

1. REST client inside Hermes
   - best when Hermes runs independently as a service
   - requires API base URL and auth config

2. Local wrapper around collaboration MCP/CLI
   - best for development and parity with existing Claude Code workflow
   - less independent if Hermes runs outside Claude/MCP context

Recommended first implementation:

- Use a small REST client abstraction with read-only methods.
- Keep authentication configurable through environment/config.
- Do not implement write methods in the first pass.

Suggested config:

```yaml
collaboration:
  enabled: true
  base_url: "http://collaboration.ktl.com"
  auth_token_env: "COLLABORATION_API_TOKEN"
  default_project: ""
```

Suggested tool functions:

- `collab_dashboard`
- `collab_list_requests`
- `collab_overdue_requests`
- `collab_project_summary`
- `collab_blockers`
- `collab_reports`

Exit criteria:

- Hermes can produce a raw read-only snapshot from collaboration state.
- No write endpoints are available through the tool yet.

### Phase 2 — PM analysis layer — partially delivered

Goal:

Turn raw collaboration data into actionable PM summaries.

Capabilities:

- classify requests
- detect stale reports
- detect overdue work
- identify blockers
- identify user-decision-needed items
- rank attention items

Suggested commands/skills:

- `/collab brief`
- `/collab triage`
- `/collab project <name>`
- `/collab overdue`
- `/collab blockers`

Output format:

```text
Needs attention
- item

Blocked
- item

User decisions needed
- item

Suggested next actions
1. action
2. action
```

Exit criteria:

- User can ask Hermes for a useful collaboration brief on demand.
- Hermes can distinguish “needs user decision” from ordinary stale work.

### Phase 3 — Scheduled monitoring — delivered

Goal:

Run deterministic read-only PM checks automatically and send concise alerts without invoking the generic LLM agent loop.

Implemented monitor kinds:

- `daily_brief`: runs the existing read-only collaboration brief formatter.
- `urgent_alert`: checks open high-priority requests, overdue requests, and blockers.

Default config:

```yaml
collaboration:
  monitor:
    enabled: false
    daily_brief_enabled: false
    urgent_alerts_enabled: false
    daily_schedule: "57 8 * * *"
    urgent_schedule: "every 4h"
    deliver: "local"
    limit: 20
    project: ""
    alert_on_high_priority: true
    alert_on_overdue: true
    alert_on_blockers: true
    read_only: true
    gateway_install_enabled: false
```

Commands:

- `/collab monitor status` shows monitor config and installed monitor jobs.
- `/collab monitor run daily` runs one daily brief immediately.
- `/collab monitor run urgent` runs one urgent alert check immediately.
- `/collab monitor install daily` creates a local Hermes cron job for daily briefs.
- `/collab monitor install urgent` creates a local Hermes cron job for urgent alerts.

Gateway behavior:

- Gateway `/collab monitor status` and `/collab monitor run ...` remain behind `collaboration.gateway_brief_enabled`.
- Gateway `/collab monitor install ...` is refused unless `collaboration.monitor.gateway_install_enabled=true`.
- The monitor never writes to collaboration shared state.

Alert policy:

- Urgent checks return `[SILENT]` when no configured urgent condition exists.
- Alert text includes compact top items and suggested next actions.
- Persistent deduplication is intentionally out of scope for the first scheduled monitor pass.

Exit criteria:

- Hermes can run local typed cron jobs for daily and urgent collaboration monitoring.
- Urgent monitor jobs suppress no-op notifications.
- Gateway job installation remains disabled by default.

### Phase 4 — Inbound request bridge — partially delivered

Goal:

Make collaboration requests addressed to `hermes-agent` visible as actionable Hermes work without granting autonomous writeback.

Delivered capabilities:

- poll collaboration requests addressed to `hermes-agent` through the deterministic inbound monitor
- track seen request ids to avoid duplicate notifications
- persist open inbound requests as local pending inbox items under Hermes home
- surface pending inbound requests through `/collab inbox` in CLI and guarded gateway contexts
- keep preview runs side-effect free with `mark_seen=False`

Remaining capabilities:

- attach relevant collaboration knowledge and Agent Board context to the pending item
- optionally invoke a constrained Hermes runtime flow after the user chooses to proceed

Initial bridge behavior:

```text
collaboration request to hermes-agent
→ bridge detects new or updated request
→ bridge records local seen state and upserts a pending local inbox item
→ Hermes surfaces pending work through monitor output or `/collab inbox`
→ user chooses whether Hermes should draft or perform follow-up
```

Non-goals for this phase:

- no automatic collaboration response writeback
- no automatic request close/reassign/priority changes
- no autonomous repository-local development work
- no broad project notices without explicit approval

Exit criteria:

- A request addressed to `hermes-agent` is surfaced as a local pending item or notification. — delivered for read-only local inbox
- The bridge can avoid repeating the same unchanged request. — delivered for seen-state notification suppression
- Shared-state writeback remains unavailable or explicitly approval-gated. — delivered by keeping this phase read-only

### Phase 5 — Approval-gated write actions — partially delivered

Goal:

Allow Hermes to prepare shared-state changes, but require user approval before execution.

Delivered write action:

- reply to request through `/collab respond draft|list|show|post`

Remaining candidate write actions:

- create clarification request
- close request as completed/duplicate/wontfix
- create stale report ping
- update task state
- create weekly PM report

Design:

- Keep the existing `collaboration` tool read-only.
- Add a separate future write tool only when the approval flow is ready.
- The write tool should accept structured actions, not free-form shell/API commands.
- Every draft should include: action type, target id, proposed body, reason, and risk level.
- The gateway should show draft text first and require an explicit approval command before execution.
- Approval should be single-use and scoped to one action id.
- Reassign, close, priority change, broad notice, and infrastructure/security actions should remain manual even after the first write tool exists.

Workflow:

```text
Hermes detects issue
→ drafts structured action
→ stores pending action locally with an action id
→ shows exact proposed shared-state change
→ asks user for approval
→ executes only that approved action id
→ reports result and clears the pending action
```

Suggested structured action shape:

```json
{
  "action_id": "collab-approval-...",
  "type": "reply_request",
  "target_id": "REQ-...",
  "body": "Proposed reply text",
  "reason": "Why this action is recommended",
  "risk": "low"
}
```

Exit criteria:

- User can approve a single proposed action. — delivered for collaboration responses
- Hermes executes only that approved action. — delivered for collaboration responses
- No batch write actions happen without explicit approval. — delivered for collaboration responses
- The read-only tool remains usable without write credentials. — delivered

## Always-on runtime deployment expectations

Before Hermes is run as an always-on collaboration PM service, deployment should satisfy these constraints:

- Run the service with read-only collaboration monitoring enabled first; keep response posting CLI-only unless a separate approval channel is explicitly designed.
- Bind any local web/gateway service to `127.0.0.1` by default; expose broader network access only after port, auth, and source-network review.
- Store collaboration API credentials only in host-local environment files or the configured secret mechanism; do not commit tokens to Hermes config, logs, or reports.
- Keep `collaboration.monitor.gateway_install_enabled=false` unless the operator intentionally allows gateway users to install local cron jobs.
- Use deterministic monitor jobs for daily, urgent, and inbound checks; do not invoke the generic LLM loop from a scheduler until an invocation contract, idempotency, and failure policy are documented.
- Persist monitor state and response drafts under Hermes home so restarts do not duplicate notifications or lose pending approvals.
- Record service port, startup command, log path, and restart policy in project documentation before enabling a long-running process.
- Register any cron, systemd timer, or background agent in the shared agent registry when it becomes a persistent automation.
- Run repeated manual approval-gated response operations before enabling any limited automation that writes shared collaboration state.

## Autonomy readiness operating criteria

Hermes uses `docs/autonomous-pm-operating-criteria.md` as the operating manual for deciding whether HITL collaboration PM operation is ready to progress toward an autonomous PM loop.

The readiness criteria are intentionally strict:

- at least 14 calendar days of evidence
- at least 10 live HITL handled requests
- monitor success rate >= 98%
- detection coverage >= 95% for requests addressed to `hermes-agent`
- draft acceptance rate >= 90%
- human denial rate <= 10%
- post success rate >= 95%
- 0 unapproved writes
- 0 critical errors
- 0 forbidden-scope automation attempts

Passing the readiness criteria does not enable autonomous shared-state writes. A pass only allows a separate limited-autonomy design review. Until then, shared-state writes remain CLI approval-gated and exact action-ID confirmed.

### Phase 6 — Limited automation — planned

Goal:

Automate only low-risk, repetitive PM actions after enough successful approval-gated use.

Possible auto-actions:

- generate read-only daily brief
- draft but not send stale pings
- mark internal triage notes locally
- create low-priority reminders for stale reports, if explicitly enabled

Still approval-gated:

- close requests
- reassign ownership
- change priorities
- infrastructure/security-related notices
- high-priority requests

Exit criteria:

- Automation rules are explicit and documented.
- User can disable automation easily.

## First Milestone

Implement the smallest useful version:

1. Add read-only collaboration client/tool.
2. Add `/collab brief` or equivalent skill/command.
3. The brief should show:
   - open high-priority requests
   - overdue requests
   - stale reports
   - blockers
   - user decisions needed
   - suggested next actions
4. Add `/collab monitor run inbound` and `/collab inbox` so requests addressed to `hermes-agent` become local pending items.
5. No write actions.
6. Run from CLI first, then expose through Telegram/Slack gateway.

## Success Criteria

Hermes is useful for this role when:

- the user can ask “what needs attention?” and get a reliable answer
- overdue work is surfaced before it disappears into the backlog
- stale reports are visible without manually checking the dashboard
- user-decision-needed items are phrased as concrete questions
- write actions are never surprising
- Claude Code remains the primary tool for repository-local development

## Open Questions

- Which collaboration API endpoints should Hermes use as the stable contract?
- What authentication mechanism should Hermes use when running as a service?
- Should daily briefs go to Telegram DM, Telegram home channel, Slack, or CLI only?
- What SLA thresholds define overdue/stale by default?
- Which projects should be included in the first rollout?
- Should the inbound request bridge eventually consume Agent Board entries or use a future webhook/event source instead of polling collaboration REST?
- Should local inbox items stay JSON-backed under Hermes home, or move into Hermes state DB once approval-gated actions exist?
- What local pending-action shape is needed before an inbox item can invoke Hermes on approval?
- What exact approval flow is required before Hermes posts a response back to collaboration?
- Should write actions use direct REST calls or a collaboration-specific Hermes tool wrapper?
