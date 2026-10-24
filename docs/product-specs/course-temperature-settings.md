---
title: Internal Course Temperature Settings
status: implemented
owner_surface: shared
last_reviewed: 2026-10-08
canonical: true
---

# Internal Course Temperature Settings

Teaching and follow-up temperatures are server-owned course runtime settings.
They are absent from every course settings interface, frontend response type,
course detail response, and documented save/preview request schema.

`GET` and `POST /api/shifu/shifus/<shifu_bid>/detail` do not return
`temperature` or `ask_temperature`. Saving settings ignores these legacy input
fields, preserving the stored teaching and follow-up values. First-time drafts
keep the existing internal defaults: teaching `0.3`, follow-up `0.0`.

`POST /api/shifu/ask/preview` ignores a legacy `ask_temperature` override and
reads the current draft's stored follow-up temperature. Explicit zero and
two-decimal values retain their precision; an absent stored value uses `0.0`.
There is no browser-owned copy of the temperature value.

Existing database values, draft history, publication, copying, and learning
execution keep their current temperature behavior. No data migration or reset
is required. The intentional public API change retires temperature overrides
and response fields; existing clients may keep sending the fields harmlessly
while upgrading to omit them.

Course backup files retain their existing temperature fields. This explicit
compatibility exception preserves export/import portability and non-default
generation behavior across deployments. CLI, demo import, and other internal
configuration workflows keep their existing format and behavior.

The OpenAI-compatible model gateway has a separate provider protocol, not a
course configuration contract. Its standard sampling options remain supported.

No analytics event is added: this removes configuration controls and transfers
existing preview configuration ownership to the backend. The existing settings
save event family retains its trigger and payload.
