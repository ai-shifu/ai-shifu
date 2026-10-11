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

The authoring course-detail response exposes `default_learning_permission` from
the same backend default used to create outlines. The new-lesson dialog reads
that value for its initial selection. An unchanged selection is omitted from
the creation request; an explicit teacher override is submitted as `type`.
Inline creation and chapter creation also omit `type`. Frontend outline state
uses the created outline's returned `type` and `is_hidden` values.

The metadata field is additive. Deploy the backend together with, or before,
the frontend. When metadata is absent, the frontend can still omit `type` and
accept the returned permission; it must not invent a local default.

`guest` allows learning without login or purchase. `trial` requires login but
does not require purchase. `normal` retains the existing purchase restriction.
Preview permissions remain unchanged.

The existing `creator_outline_create` event continues to count successful
creation with `shifu_bid`, `outline_bid`, and `parent_bid`. The existing settings
save event still reports the saved permission. No event meaning, population,
trigger, deduplication, payload, or consumer changes. See the canonical
[authoring analytics contract](web-umami-contract-remediation.md#creator-authoring-interactions).
