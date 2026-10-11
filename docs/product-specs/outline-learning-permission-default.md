---
title: Backend-owned outline learning permission default
status: implemented
owner_surface: shared
last_reviewed: 2026-10-11
canonical: true
---

# Backend-owned outline learning permission default

New outlines default to `trial` (free learning after login). The backend owns
this default for single creation, batch creation, and the initial chapter and
lesson created with a new course. An omitted or `null` permission uses the same
default. An explicitly selected `guest`, `trial`, or `normal` permission remains
authoritative. Existing outlines, copies, and imported explicit permissions are
preserved; no data migration is required.

The new-lesson dialog starts without a selected permission. Unless the teacher
explicitly selects a permission, the creation request omits `type` and the
backend applies its default. Inline creation and chapter creation also omit
`type`. Frontend outline state uses the created outline's returned `type` and
`is_hidden` values; existing settings display the saved permission. The default
is not exposed as course-detail metadata or duplicated in frontend state.

Deploy the backend together with, or before, the frontend so omitted permissions
use the intended default. Existing explicit creation permissions remain supported.

`guest` allows learning without login or purchase. `trial` requires login but
does not require purchase. `normal` retains the existing purchase restriction.
Preview permissions remain unchanged.

The existing `creator_outline_create` event continues to count successful
creation with `shifu_bid`, `outline_bid`, and `parent_bid`. The existing settings
save event still reports the saved permission. No event meaning, population,
trigger, deduplication, payload, or consumer changes. See the canonical
[authoring analytics contract](web-umami-contract-remediation.md#creator-authoring-interactions).
