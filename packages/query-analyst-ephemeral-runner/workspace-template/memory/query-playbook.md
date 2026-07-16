# Query Playbook

This file is intentionally generic. Add only reusable procedures and source
locations that are safe for the machine where the runner operates.

## Task Checklist

- Restate the exact question.
- Record scope, filters, unit, denominator, and deduplication rule.
- Preserve the executed query or extraction script.
- Save compact result data and execution diagnostics.
- Cross-check totals or representative samples.
- Separate verified facts, assumptions, and limitations.

## Summary Template

```markdown
# Task Summary

## Question
## Sources
## Filters And Unit
## Verified Findings
## Validation
## Artifacts
## Limitations
## Follow-up Needed
```

## Memory Hygiene

- Keep task-specific figures in `outputs/<task_id>/`, not in this playbook.
- Store credentials only in an OS credential store or ignored environment file.
- Add a reusable rule only after it has been verified in an actual task.
