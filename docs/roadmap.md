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
- [ ] Evaluate limited automation only after repeated successful approval-gated operation. ← **current**

## Quality and operations

- [ ] Keep collaboration writes disabled by default until the approval flow is implemented and validated.
- [ ] Add end-to-end smoke coverage for “request to hermes-agent → surfaced pending item → approved response”.
- [ ] Document runtime deployment expectations before running Hermes as an always-on service.
