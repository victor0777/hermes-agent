# Roadmap

## Collaboration PM / Hermes autonomy

- [x] Define Hermes as a collaboration PM/operator assistant rather than a Claude Code replacement.
- [x] Add read-only collaboration client and `/collab brief` workflow.
- [x] Add deterministic read-only collaboration monitors for daily and urgent checks.
- [x] Add read-only collaboration knowledge and Agent Board search tools.
- [x] Document the collaboration-triggered execution gap and next bridge milestones.
- [x] Design the first inbound collaboration request bridge for requests addressed to `hermes-agent`.
- [x] Surface inbound Hermes-targeted requests as local pending inbox items with deduplicated notifications.
- [x] Add an approval-gated flow for drafting and posting collaboration responses.
- [x] Define strict HITL-to-autonomous PM operating criteria and pass/fail readiness categories.
- [x] Add local autonomy evidence logging, KPI summary, and readiness gate commands.
- [ ] Collect HITL KPI evidence and run strict pass/fail readiness evaluation before any autonomous PM loop. ← **current**
- [ ] Design narrow limited-autonomy templates only after the readiness gate passes.

## Quality and operations

- [x] Keep collaboration writes disabled by default until the approval flow is implemented and validated.
- [x] Add end-to-end smoke coverage for “request to hermes-agent → surfaced pending item → approved response”.
- [x] Document runtime deployment expectations before running Hermes as an always-on service.
