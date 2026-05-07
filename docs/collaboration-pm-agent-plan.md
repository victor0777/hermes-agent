# Collaboration PM Agent Plan

## Purpose

Use Hermes Agent as an always-on project-management assistant for `collaboration.ktl.com`.
Hermes should not replace Claude Code for repository-local development work. Its role is to monitor collaboration state, surface neglected work, ask for decisions when needed, and prepare low-risk project-management actions for approval.

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
  │   ├─ project summary read
  │   ├─ blocker read
  │   ├─ report read
  │   └─ approval-gated write actions
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

### Phase 1 — Read-only collaboration client

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

### Phase 2 — PM analysis layer

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

### Phase 3 — Scheduled monitoring

Goal:

Run PM checks automatically and send concise alerts.

Schedules:

- daily morning brief
- periodic overdue monitor
- weekly project-management review

Recommended defaults:

- daily brief: once per morning
- overdue monitor: every 4–6 hours
- weekly review: once per week

Alert policy:

- Alert only on meaningful changes or high-priority stale items.
- Avoid repeating the same unchanged warning every interval.
- Include direct request/project identifiers.

Exit criteria:

- Hermes sends useful PM summaries without manual prompting.
- Repeated alerts are deduplicated or summarized.

### Phase 4 — Approval-gated write actions

Goal:

Allow Hermes to prepare shared-state changes, but require user approval before execution.

Candidate write actions:

- create clarification request
- reply to request
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

- User can approve a single proposed action.
- Hermes executes only that approved action.
- No batch write actions happen without explicit approval.
- The read-only tool remains usable without write credentials.

### Phase 5 — Limited automation

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
4. No write actions.
5. Run from CLI first, then expose through Telegram/Slack gateway.

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
- Should write actions use direct REST calls or a collaboration-specific Hermes tool wrapper?
