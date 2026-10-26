---
title: Make course actions understandable to first-time teachers
status: active
owner_surface: shared
last_reviewed: 2026-10-26
---

# Course action copy

## Purpose / Big Picture

Make the course card actions and their existing dialogs understandable to first-time teachers. The approved Chinese menu labels are stored in shared translations. Explain learner activation, discount codes, authoring collaboration, and personal archiving at the point of use.

## Progress

- [x] 2026-10-26 19:50 CST: Inspected the current UI, translations, and backend semantics; agreed on short menu names with the user.
- [x] 2026-10-26 19:53 CST: Fetched origin/main and created a focused task branch in the current checkout.
- [x] 2026-10-26 20:20 CST: Implemented menu descriptions, dialog copy, and corresponding strings in all eight locales.
- [x] 2026-10-26 20:35 CST: Passed 90 focused tests, type checking, lint, translations, architecture, and the all-files gate; captured 39 screenshots with demonstration data.
- [x] 2026-10-26 20:35 CST: Prepared a grouped screenshot gallery for user review.
- [x] 2026-10-26 20:55 CST: Applied the requested tooltip presentation, added its analytics contract and focused regression coverage, and cancelled the optional preview login setup.
- [x] 2026-10-26 21:10 CST: Applied the follow-up labels, removed menu dividers, clarified account/nickname formatting, hid the locked course field, and enabled mixed phone/email lists through the existing API.
- [x] 2026-10-26 21:30 CST: Passed 90 focused frontend tests and type checking; the independent nickname-preservation fix is available as PR #3192 with 781 backend tests.
- [x] 2026-10-26 21:35 CST: Refreshed and inspected all 39 screenshots and passed the final repository all-files gate.
- [ ] Await user feedback on the updated implementation.

## Surprises & Discoveries

- Discount codes can reduce the price partially or fully; they do not always grant a free course.
- Archiving is scoped to the current user's list and does not change course publication or learner access.
- Pending collaborator removals must be described as pending until saved.
- Existing successful activations are reported as failures by the import endpoint, so a failed attempt must not imply the learner lacks access.

## Decision Log

- Preserve existing API request schemas and permissions. Split mixed phone/email rows into the existing typed activation requests and retain all per-account results. Existing operation requests stay unchanged. Tooltip help adds the `creator_course_action_help_view` event under its documented privacy and deduplication contract.
- Keep discount-code result/clipboard workflow changes outside this first copy iteration.
- Use fixture API responses with the real local frontend to capture confirmation, failure, and success states without changing real learner access.

## Outcomes & Retrospective

Implemented the approved short labels, contextual tooltip explanations, precise action buttons, pending collaborator removal wording, and personal archive semantics. All eight locales preserve key and ICU argument parity. The local gallery covers the menu, activation in both account modes, confirmation and result states, discount-code options and management, collaboration, archive and restore, and small-window scrolling. User acceptance remains pending; no production deployment or main-branch merge has occurred.

## Context and Orientation

Course list and menu: `src/web/src/app/admin/page.tsx` and `components/ShifuCard.tsx`. Learner activation: `src/web/src/components/order/ImportActivationDialog.tsx`. Discount code creation: `src/web/src/app/admin/orders/CreatorRedemptionCodeDialog.tsx`. Collaboration: `src/web/src/components/shifu-setting/ShifuPermissionDialog.tsx`. Canonical strings live under `src/i18n/`.

## Plan of Work

Update existing labels and add concise contextual help. Preserve the distinction between learner access and authoring collaboration. Rename the course tabs to match their actual archived filters. Maintain locale key and interpolation parity. Verify the changed surfaces and save screenshots of their important states.

## Concrete Steps

1. Update source components and shared translations.
2. Run focused Jest tests, translation checks, formatting, lint, type checking, and repository harness checks.
3. Start the local frontend, supply demonstration API data, and capture screenshots in `output/playwright/course-actions/`.
4. Inspect the screenshots, repair layout or copy issues, and prepare a screenshot gallery.

## Validation and Acceptance

The course tabs use the approved Active/Archive labels without changing the archived filter. The menu uses the four approved short labels without dividers; hovering or keyboard-focusing an item shows its description in a tooltip. Each dialog explains the result before submission. Shared-code quantity means total uses; single-use quantity means separate codes. Pending removals remain pending until saved. Archiving clearly explains its personal scope. Screenshots show the actual components and cover the four entries and their important existing states.

## Idempotence and Recovery

All source changes are isolated on a feature branch. Fixture requests are limited to the local screenshot session. Repeating captures has no effect on real accounts. No production deployment or main-branch merge is part of this task.

## Interfaces and Dependencies

No API schema, permission, dependency, or timestamp contract changes. Tooltip help and mixed learner activation have additive frontend analytics contracts in `docs/product-specs/course-action-help.md` and `docs/product-specs/course-activation-import.md`. Existing i18n keys remain stable; new help keys and interpolation arguments must be present in every supported locale.

The independent nickname behavior fix is [PR #3192](https://github.com/ai-shifu/ai-shifu/pull/3192). This UI patch keeps its nickname help neutral about existing account values and does not include that backend change.
