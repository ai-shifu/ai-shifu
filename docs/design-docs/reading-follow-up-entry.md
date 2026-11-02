---
title: Reading follow-up entry
status: implemented
owner_surface: learner-web
last_reviewed: 2026-11-02
canonical: true
---

# Reading follow-up entry

Reading mode provides one active follow-up entry at a completed persistent
content-element end. Desktop hover selects immediately. Mobile scrolling selects
the lowest fully visible end after settling, and a short tap changes that point.
Swipes, long presses, selections and multi-pointer gestures do not open questions.
The entry has stable reserved space and a 44 px mobile touch target. Semantic
buttons retain keyboard access to every eligible boundary.

Opening inserts an inline question surface at that end, for desktop and mobile.
Close preserves the mounted draft and question/answer history. Continue collapses
and focuses the next course element. Drafts, open conversations and streaming
answers lock automatic selection. Historical questions can be reopened in place.
There is no persistent bottom follow-up action or visible scope explanation.

A text element may contain several Markdown paragraphs. The supported cutoff is
the actual saved element end, not an arbitrary internal HTML paragraph. Text
requests opt into the complete current lesson prefix through that end, excluding
future elements. See [context contract](../references/follow-up-classroom-context.md).
Live voice, listening/classroom and print retain their existing context contracts.

## Analytics

The additive `learner_read_follow_up_opened` event counts deliberate accepted
opens, grouped by `surface=desktop|mobile` and `entry=boundary|history`.
`learner_read_follow_up_closed` counts accepted dismissals, grouped by the same
surface and `method=close|continue`. Weekly product reports compare aggregate
counts; these are neither an exposure denominator nor per-request conversions.

Published learners, including eligible guests, are included. Preview, print,
listen/classroom, disabled and stale targets are excluded. Global transport
account exclusions remain active. An already-open same-anchor invocation is
idempotent; rerenders do not emit, and reopening is a new accepted action.

Only the documented flat enums are delivered: no content, anchor or resource
IDs, titles, URLs, pointer coordinates or errors. useTracking owns delivery;
synchronous or asynchronous tracking failures cannot change the user action.
Existing `learner_follow_up_submit` and Live event contracts are unchanged; no
repository-owned dashboard requires migration. Focused controller tests verify
exact payloads, exclusions, deduplication, privacy and fail-open behavior; shared
transport tests verify the final delivery schema.
