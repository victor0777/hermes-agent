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
- [ ] Treat any hard fail as a stop condition for autonomy progression.
