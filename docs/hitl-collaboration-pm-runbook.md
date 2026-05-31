# HITL Collaboration PM Runbook

## Purpose

Operate Hermes as a human-in-the-loop collaboration PM assistant while collecting readiness evidence for a future autonomous PM review.

This runbook does not authorize autonomous shared-state writes. Collaboration response posting remains CLI-only and requires exact action-ID confirmation.

## Operating cadence

| Cadence | Action | Command |
|---|---|---|
| Every 30 minutes | Detect new requests addressed to Hermes | `/collab monitor run inbound` |
| Every 4 hours | Check urgent high-priority, overdue, or blocker state | `/collab monitor run urgent` |
| Daily | Review collaboration PM brief | `/collab monitor run daily` |
| After handling a request | Review KPI state | `/collab autonomy kpis` |
| Daily or before autonomy discussion | Evaluate readiness gate | `/collab autonomy gate` |
| Daily | Review `llm-gateway` / `llm-routing-telemetry` coordination state | Read collaboration project summaries and open requests; draft responses only after human review. |
| Weekly or before Paperclip work | Review `paperclip` control-plane coordination state | Check project summary, missing report/request state, upstream/downstream dependencies, and dashboard/agent-ops follow-ups. |

Recommended monitor installation commands:

```text
/collab monitor install inbound
/collab monitor install urgent
/collab monitor install daily
```

Default schedules are inbound every 30 minutes, urgent every 4 hours, and daily around 08:57 local time unless overridden in Hermes config.

## Request handling workflow

1. Review pending inbound work:

   ```text
   /collab inbox
   ```

2. For each request, classify the action boundary:

   | Request type | HITL action |
   |---|---|
   | Low-risk clarification or status response | Draft a response for approval. |
   | Security, infrastructure, priority, ownership, or high-priority request | Escalate to user review; do not automate. |
   | Repository-local code execution request | Handle through Claude Code or a dedicated project workflow, not Hermes autonomy. |
   | Close, reassign, or priority change request | Keep manual; do not use autonomous writeback. |

3. Draft a response locally:

   ```text
   /collab respond draft <request_id> <response text>
   ```

   Draft creation records local `Draft/draft_created` evidence. No network write occurs.

4. Review the exact response text shown by Hermes.

5. If approved, post with exact action-ID confirmation:

   ```text
   /collab respond post <action_id>
   ```

   Type the exact action ID when prompted. This records approval and write evidence.

6. If denied, do not post. Optionally record denial evidence:

   ```text
   /collab autonomy log Approval denied <request_id> <action_id>
   ```

## Evidence logging rules

Hermes automatically records evidence for monitor runs, inbound detections, urgent alerts, draft creation, approved response writes, unapproved write attempts, and API failures.

Manual evidence is still required for information Hermes cannot infer from local execution:

| Situation | Command |
|---|---|
| A request is confirmed as an actual Hermes target | `/collab autonomy log Detection actual_target_request <request_id>` |
| A draft is denied by the human reviewer | `/collab autonomy log Approval denied <request_id> <action_id>` |
| A forbidden-scope automation attempt is blocked | `/collab autonomy log Safety forbidden_scope_attempt <request_id>` |
| A manual recovery or repair was needed | `/collab autonomy log Recovery manual_repair <request_id> <action_id>` |
| A reviewed repair is confirmed non-systemic | `/collab autonomy log Recovery reviewed_non_systemic_exception <request_id> <action_id>` |

Detection coverage cannot pass unless actual target requests are logged explicitly.

## Security intelligence intake

Hermes can collect read-only security news, CTI, and advisory candidates for the `security-intelligence-policy-loop` without applying any policy, rule, runbook, scheduler, credential, or production change.

Configure sources under `collaboration.security_intelligence.sources` in `~/.hermes/config.yaml`:

```yaml
collaboration:
  security_intelligence:
    sources:
      - name: cisa-kev
        type: json
        url: https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json
      - name: local-advisories
        type: json
        path: /home/ktl/security/advisories.json
```

The intake writes a local manifest at `~/.hermes/collaboration/security_intelligence/intake.json` by default and logs `Detection/security_intelligence_intake` evidence. If no source is configured, it returns `blocked` with `No security intelligence sources configured.`

Manual verification commands:

```text
/collab security-intel intake 100
/collab security-intel job-spec every 6h
```

Use the `security_intelligence_intake` tool for agent execution. The `/collab security-intel job-spec` command only prints the no-apply monitor template. Install or enable a local cron job only after the operator explicitly approves the source list and schedule.

### Automated daily handoff (production baseline)

`security_intelligence_daily.py` can be executed by OS cron with writer credential and venv context loaded from `~/.hermes/.env`.

Configured baseline:

- Schedule: 매일 02:00
- Command:

```text
0 2 * * * /home/ktl/projects/hermes-agent/scripts/run_security_intelligence_daily.sh
```

This script writes output to:

- `/home/ktl/projects/hermes-agent/data/logs/security-intelligence-daily.log`

Evidence collection:

- At least one successful dry-run and one successful live run after approval.
- Request creation evidence in local log/output JSON (for live run).

## Gateway and telemetry coordination

Hermes should also operate as a HITL PM assistant for the related `llm-gateway` and `llm-routing-telemetry` projects.

Scope for this operating loop:

- watch open and in-progress requests involving `llm-gateway` and `llm-routing-telemetry`
- summarize stale requests, blockers, missing acknowledgements, and cross-project dependencies
- draft low-risk coordination responses for human approval
- surface security, infrastructure, priority, ownership, or high-priority items as escalation-required
- never close, reassign, reprioritize, change infrastructure, or post broad notices autonomously

Initial operating targets:

| Target | Purpose |
|---|---|
| `llm-gateway` project summary | Identify routing/coordination blockers and outgoing requests needing follow-up. |
| `llm-routing-telemetry` project summary | Identify telemetry blockers and incoming gateway dependencies. |
| Requests from `llm-gateway` | Track open coordination, broadcast, security-review, and telemetry requests. |
| Requests from `llm-routing-telemetry` | Track open telemetry follow-ups to `agents`, `auto_researcher`, `codex-openai`, and gateway. |

Candidate future automation:

```text
/collab monitor run routing
/collab pm digest llm-gateway llm-routing-telemetry
```

Until those commands exist, perform the checks through collaboration project summaries and request lists, then use the normal response draft/post workflow. Treat all gateway and telemetry automation as HITL evidence collection, not as authorization for autonomous shared-state writes.

## Paperclip control-plane coordination

Hermes should also consider `paperclip` as a future HITL PM integration target because Paperclip is an agent-company control plane, not just a dashboard target. It orchestrates agents, issues, projects, routines, and agent-operations views through the Paperclip dashboard.

Current collaboration registry baseline:

- project: `paperclip`
- lifecycle: active
- server: `par02`
- phase: Agent operations + knowledge graph + chat interface
- upstream: `collaboration`, `autonoma-orchestrator`
- downstream: `4d-gaussian-splatting`, `video-inpainting`
- current open incoming/outgoing requests: none in collaboration registry
- current report freshness: unknown

Observed Paperclip operating context:

- Paperclip has operated company-style agents such as PM, CEO, research, and security roles.
- Paperclip has operated routines such as 4DGS training watchdogs, campaign loops, ops log collection, vLLM/LMCache release monitoring, and daily stability reporting.
- Paperclip has depended on local LLM routing through Claude-compatible adapters, LiteLLM, and qwen-family backends, with prior content-format and tool-use compatibility issues.
- Paperclip is therefore a candidate place to register Hermes as a PM/ops agent, but that registration must start read-only and HITL-gated.

Initial HITL operating scope:

- bootstrap Paperclip collaboration hygiene by checking for missing reports, stale status, and absent open request context
- summarize upstream/downstream coordination needs involving `collaboration`, `autonoma-orchestrator`, `4d-gaussian-splatting`, and `video-inpainting`
- generate Paperclip routine health and agent stall/failure digests from read-only state
- watch local LLM, LiteLLM, Claude-compatible adapter, and tool-use compatibility issues that can block Paperclip agents
- draft low-risk Paperclip status/update reports for human approval
- keep actual Paperclip project execution, agent orchestration, issue mutation, dashboard mutation, and report posting outside Hermes autonomy unless separately approved

Candidate staged integration:

1. Read-only discovery: Hermes reads Paperclip project, routine, agent, and collaboration state and creates local PM digests only.
2. Paperclip agent registration: Paperclip may register a `Hermes-PM` or `Hermes-Ops` agent identity whose first responsibility is read-only digest/report preparation.
3. Approval-gated report bridge: Hermes drafts Paperclip or collaboration reports, and a human approves the exact report/action ID before any shared-state write.

Candidate future automation:

```text
/collab pm digest paperclip
/collab monitor run paperclip
/collab paperclip report draft
/collab paperclip report post <action_id>
```

Until those commands exist, treat Paperclip integration as a coordination-planning item. Hermes may collect local HITL evidence and draft coordination updates, but must not mutate Paperclip issues, agents, dashboards, reports, or downstream project state autonomously.

## KPI and gate interpretation

Use:

```text
/collab autonomy kpis
/collab autonomy gate
```

Expected early result is `Fail` because the strict readiness gate requires at least 14 calendar days and at least 10 successful live HITL handled requests.

A `Pass` result only means Hermes is eligible for a separate limited-autonomy design review. It does not enable autonomous writes.

Hard fail conditions:

- any unapproved shared-state write
- any forbidden-scope automation attempt
- any critical safety or authorization error
- any unreviewed rollback or repair

## Safety boundaries

Allowed without additional approval:

- read-only collaboration brief and monitor runs
- local inbox updates
- local evidence logging
- local response draft creation
- KPI and gate evaluation

Requires exact human approval:

- posting a collaboration response

Not allowed in HITL operation:

- autonomous close, reassign, or priority change
- autonomous infrastructure or security handling
- autonomous high-priority request handling
- repository-local code execution through Hermes collaboration automation
- broad notices or broadcasts

## Daily operator checklist

- [ ] Check `/collab inbox` for pending Hermes-targeted requests.
- [ ] Run or review daily and urgent monitor output.
- [ ] Draft responses only for low-risk requests.
- [ ] Post responses only after exact action-ID confirmation.
- [ ] Log `Detection actual_target_request` for confirmed Hermes-targeted requests.
- [ ] Run `/collab autonomy kpis` after handling requests.
- [ ] Run `/collab autonomy gate` before any autonomy-readiness discussion.
- [ ] Review `llm-gateway` and `llm-routing-telemetry` summaries for stale requests, blockers, and missing acknowledgements.
- [ ] Draft only low-risk gateway/telemetry coordination responses; escalate security, infrastructure, priority, ownership, and high-priority items.
- [ ] Review `paperclip` summary for missing report status, absent request context, and upstream/downstream coordination needs.
- [ ] Treat Paperclip dashboard/agent/issue mutations as out of scope for Hermes autonomy unless separately approved.
- [ ] Treat any hard fail as a stop condition for autonomy progression.
