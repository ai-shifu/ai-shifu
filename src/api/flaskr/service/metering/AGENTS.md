# Backend Service: metering

This module owns usage recording, usage reporting routes, and normalization
constants for billable LLM and TTS activity.

Entry files in this directory: `routes.py`, `recorder.py`, `consts.py`,
`models.py`.

## Do

- Normalize usage types, scenes, and billable flags in the shared consts and
  recorder helpers before persisting records.
- Keep recorder helpers as the single place that translates runtime events
  into persisted metering rows.
- Preserve reporting filters and date parsing behavior exposed through the
  metering routes.

## Avoid

- Do not let callers write metering rows directly when recorder helpers
  already own the normalization contract.
- Do not introduce new usage-scene semantics without updating both const
  normalization and reporting expectations.
- Do not change billable defaults or record structure without checking
  downstream finance or quota consumers.

## Tests

`cd src/api && pytest tests/service/metering/ -q`
