# Backend Service: metering

This module owns usage recording and normalization constants for billable LLM
and TTS activity. It exposes no HTTP routes; usage rows are read by billing,
the dashboard and creator analytics, each behind its own permission checks.

Entry files in this directory: `recorder.py`, `consts.py`, `models.py`,
`api.py`.

## Do

- Normalize usage types, scenes, and billable flags in the shared consts and
  recorder helpers before persisting records.
- Keep recorder helpers as the single place that translates runtime events
  into persisted metering rows.
- Add any new HTTP reporting route behind an explicit operator or course
  permission check; usage rows span every learner and course.

## Avoid

- Do not let callers write metering rows directly when recorder helpers
  already own the normalization contract.
- Do not introduce new usage-scene semantics without updating both const
  normalization and reporting expectations.
- Do not change billable defaults or record structure without checking
  downstream finance or quota consumers.

## Tests

`cd src/api && pytest tests/service/metering/ -q`
