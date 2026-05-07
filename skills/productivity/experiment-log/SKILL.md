---
name: experiment-log
description: Record experiment results into docs/findings.md, docs/diaries/, and update docs/roadmap.md checkboxes in one step.
---

# Experiment Log Skill

Use this skill when an experiment, evaluation, or exploratory task has just been completed and the results need to be documented.

This skill updates up to three files in a single pass. All three follow the project documentation conventions. Only update files that exist — skip any that are missing.

## Step 1: Gather context

Before writing anything, collect these from the conversation or working directory:

- **Title**: short label for the experiment (used as heading)
- **Objective**: what was being tested
- **Method**: config changes, commands run, dataset used
- **Result**: quantitative outcome (metrics, error messages, timing) — be specific
- **Takeaway**: what this means for next steps
- **Roadmap task**: which task in roadmap.md this relates to (if any)

If any of these are unclear, ask one clarifying question before proceeding.

## Step 2: Append to `docs/findings.md`

Add a new entry **at the bottom** of the file:

```markdown
## YYYY-MM-DD: {Title}
**Context**: {Objective — what task or question prompted this}
**Finding**: {Result — quantitative facts, not opinions}
**Impact**: {Takeaway — how this affects the project going forward}
```

## Step 3: Append to `docs/diaries/YYYY-MM-DD.md`

Create the file if it doesn't exist. Append a new task section:

```markdown
## Task N: {Title}
- **Goal**: {Objective}
- **Approach**: {Method}
- **Result**: {Result — success/failure, quantitative}
- **Duration**: {approximate time if known}
- **Next**: {what to do based on this result}
```

Increment the task number based on existing tasks in the file.

## Step 4: Update `docs/roadmap.md`

If the experiment corresponds to a roadmap task:
- Mark it `[x]` if completed
- Move the `← **current**` marker to the next uncompleted task
- Do NOT add new tasks or change task descriptions

## Rules

- Use today's date (YYYY-MM-DD format)
- Never overwrite existing entries — always append
- Keep each entry self-contained (readable without other context)
- If the experiment failed, document it — failed experiments are valuable findings
- Numbers over adjectives: "mAP dropped 3.2% (41.7 → 38.5)" not "performance decreased"
