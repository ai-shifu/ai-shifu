---
title: Urdu product locale
status: active
owner_surface: cross-surface
last_reviewed: 2026-09-27
canonical: false
---

# Urdu product locale

## Purpose / Big Picture

Add Pakistan Urdu (`ur-PK`, اردو) throughout AI-Shifu using the current Chinese
shared JSON values as the translation source. Learners and teachers can select
Urdu, retain the preference, and use an RTL interface and localized API errors.
Authored course content keeps its own language.

## Progress

- [x] 2026-09-27 UTC: Read the locale delivery checklist and inspect current contracts.
- [x] 2026-09-27 UTC: Translate and review the complete Chinese JSON inventory.
- [x] 2026-09-27 UTC: Connect runtime, email, legal configuration and analytics contracts.
- [x] 2026-09-27 UTC: Verify focused frontend/backend checks and browser behavior.
- [x] 2026-09-27 UTC: Complete all-files repository gates and prepare the ready PR.
- [x] 2026-09-27 UTC: Publish ready PR #2988.
- [x] 2026-09-27 UTC: Review Chinese-source accuracy and correct 382 strings across 35 files.
- [x] 2026-09-27 UTC: Extend the arena renderer, RTL propagation and locale regression checks to Urdu.
- [x] 2026-09-27 UTC: Synchronize PR #2989's 376 retired keys and two empty namespaces to Urdu after the remote branch rebase.
- [ ] 2026-09-27 UTC: Complete review feedback and verify hosted CI acceptance.

## Surprises & Discoveries

The initial shared local dependency directory was older than the lockfile.
After installing the pinned `markdown-flow-ui@0.2.29`, its locale contract confirms
Urdu support. Extend the existing bridge without changing its version. Keep the
chat input direction tied to the host interface locale.
Existing onboarding assistant prompt maps need the existing locale backfill.
Browser smoke caught the login page overwriting the persisted guest preference
with browser language on reload. Its fallback now uses the current bootstrap
language; an explicit account language retains precedence.
The accuracy follow-up found role reversals, noun/action confusion, literal meal
translations for daily plans, amount/count confusion, incorrect comparison
boundaries and financial meanings. Template/placeholder checks did not detect
these. Reverse translation was used only as a diagnostic; remote unavailability
limited its coverage, so it cannot establish full linguistic acceptance.

## Decision Log

- Use `ur-PK` as the canonical Urdu locale, with base-language normalization for
  `ur`, `ur_IN` and other Urdu variants.
- Reuse the existing `user_language_selected` event and its safe locale enum.
  Extend acceptance coverage and its supported-locale documentation.
- Show the existing Urdu-translated English fallback notice for legal documents.
  Add optional Urdu URLs without inventing approved legal translations.
- Start shared translations from Chinese. Use machine translation only as a
  draft, preserve syntax and placeholders, and review terminology and key flows.

## Outcomes & Retrospective

The current 56-file Urdu inventory preserves the 3,895 source keys after PR
#2989 removed 376 unused keys and two empty namespaces. Surviving Urdu values
are preserved during that synchronization. Focused
frontend tests (280) and backend tests (99) pass. Type checking,
translation parity/usage, architecture checks, a production build and all-files
pre-commit gates pass. Browser smoke confirms selection, RTL layout, preference
retention after login-page reload and the Urdu-labeled English legal fallback.
The local cross-origin API configuration prevents live authentication and email
delivery testing; rendering and email contracts have focused regression coverage.
Hosted CI acceptance remains open. Deployment and per-installation onboarding
backfills are outside this task.
The follow-up accuracy review corrected 382 values without changing keys or
runtime interfaces. It combines an inventory-wide terminology, numeric and
technical-token audit with bilingual review of key flows and production call
sites. Real i18next/ICU, locale/legal and backend email/billing translation checks
pass (15 frontend tests, 58 backend tests). Terminology and meaning constraints
are recorded in the Urdu section of the canonical i18n guide. This is an agent
accuracy review, not native-speaker linguistic certification.
Review follow-up extends the arena's frozen locale contract to `ur-PK`, preserves
RTL in reading/slides/HTML sandboxes, and checks Urdu library controls without a
dependency change. Its 11 renderer boundary tests, 24 frozen-metadata tests and
18 browser locale cases pass. The broader engine test file has four existing
observer-fixture failures (`tool_calls_are_output` is not accepted by the mocks);
the same four failures reproduce with the pre-change test file. They are outside
the locale work and are not corrected here.

## Context and Orientation

Shared translations and RTL metadata live in `src/i18n/`. Frontend language
normalization and preference persistence use `src/web/src/i18n.ts`. API errors
load shared JSON through `src/api/flaskr/i18n.py`. Runtime legal URLs cross the
backend config route, billing DTO, frontend environment and store contracts.

## Plan of Work

Complete `src/i18n/ur-PK/` with identical keys and technical syntax. Register
Urdu and RTL, extend explicit locale contracts, verification email direction,
output language names and translated billing search. Cover normalization,
selection analytics, preference persistence, RTL propagation, ICU formatting,
API loading and legal URL round trips. Document environment rollout limitations.

## Concrete Steps

1. Translate Chinese values, review product terms, and regenerate locale metadata.
2. Update all explicit producers and consumers for `ur-PK`.
3. Use the existing onboarding backfill with `--locale ur-PK`; document preview
   and apply commands, without changing any installation's saved data here.
4. Run parity/usage, focused Jest/pytest, type-check, lint, build, browser smoke,
   harness and all-files hooks. Create the focused ready PR after checks.

## Validation and Acceptance

All Chinese files/keys and ICU arguments have corresponding Urdu values. Urdu
selection emits the existing exact allowlisted event, survives analytics failure,
and persists across reloads. HTML and shared controls are RTL. Course language
remains separate from the Urdu library controls and the host composer.
Emails have Urdu text and RTL HTML with verification digits isolated LTR.
Runtime legal URLs include Urdu and blank values keep the labeled English
fallback. Backend errors and generated output use the registered Urdu language.

## Idempotence and Recovery

The existing onboarding backfill previews without writes, preserves existing
translations, and uses the normal concurrent-save guard. A repeated application
is a no-op. JSON metadata generation is deterministic. No database migrations or
deployment writes are part of this change.

## Interfaces and Dependencies

Follow [the locale checklist](../../references/i18n.md) and
[language-selection analytics](../../product-specs/language-selection-analytics.md).
Keep MarkdownFlow dependencies pinned. Run the existing onboarding backfill in
each upgraded environment before exposing the new language to learners.
