---
title: Tab hint completion in MarkdownFlow interactions
---

## Purpose / Big Picture

Allow learners to accept a MarkdownFlow input hint with Tab, edit it, and submit
it explicitly. Cover course reading, listening, Profile onboarding and their
previews, while preserving ordinary follow-up inputs and other forms.

## Progress

- [x] 2026-10-30: Implemented and locally validated Tab completion in the shared
  component library and its application hosts.
- [x] 2026-10-30: Merged [library PR #296](https://github.com/ai-shifu/markdown-flow-ui/pull/296)
  and published official 0.3.6 from `9e2fc020e5a53c889724e8fa9c0209eec76d7aae` through
  [the release workflow](https://github.com/ai-shifu/markdown-flow-ui/actions/runs/40999805214).
- [x] 2026-10-30: Pinned 0.3.6 with an npm-generated lockfile and verified a clean
  installation, 13 focused Jest suites / 280 tests, types, lint and production build.
- [x] 2026-10-30: Passed the repository-wide pre-commit gate, including source
  formatting, lint, translations, harness and architecture checks.
- [x] 2026-10-30: Reproduced classroom completions being counted as listening
  usage, restricted listening eligibility and added mode-switch regressions.
  Verified standalone previews complete hints with no analytics observer.
- [x] 2026-10-30: Integrated main at `ae176d93aa1f78acb4efaf6cf7dd815d8c66f115`,
  preserving its remark-flow 1.4.3 pin and override cleanup while keeping
  markdown-flow-ui 0.3.6. Regenerated the lockfile with npm and clean-installed it.
- [x] 2026-10-30: Added real installed-Slide integration coverage for Tab
  completion, listening analytics, preview exclusion and explicit submission.
- [ ] 2026-10-30: Review application CI and merge the integration PR.

## Surprises & Discoveries

- The upgraded bundled CodeMirror uses the browser `Window` constructor. The
  native ESM/CJS editor smoke fixture omitted it from its JSDOM globals, producing
  deferred measurement exceptions despite passing assertions. Including `Window`
  in the existing globals list removes those diagnostics in both smoke cases.
- Next rewrites generated `.next/types` files during builds. Run the standalone
  type check after the build rather than concurrently.
- Main independently upgraded markdown-flow-ui to 0.3.5 and remark-flow to
  1.4.3 in PR #3238. Resolve the overlapping manifest/lockfile changes from that
  upstream baseline, then upgrade only markdown-flow-ui to 0.3.6 with npm.

## Decision Log

- Only an unmodified, non-repeated Tab in a focused, completely empty, editable
  input with a non-blank hint accepts that entire hint. Preserve whitespace in
  the hint and in existing input. Shift+Tab, modifiers, IME and key code 229 do
  not accept it. Keep focus and place the caret at the end; never submit.
- Enable completion in MarkdownFlow interactions. Standalone MarkdownFlowInput
  requires an explicit acceptance callback, so ordinary follow-up inputs retain
  native Tab behavior. No backend, syntax or answer-schema changes are needed.
- Observer callbacks receive no authored text and cannot prevent completion.
- Classroom mode retains hint completion but is excluded from the listening
  usage metric. Only `variant='listen'` outside previews emits `course_listen`.
- Validate a local npm tarball inside AI Shifu before merging the library.
  Temporary filesystem dependency references must not enter a PR.

### Product analytics contract

Follow [the canonical analytics rules](../../references/frontend-product-analytics.md).

- Business question: Do learners adopt Tab hint completion, and on which surface?
- Metric: Weekly accepted completions and distinct eligible users by surface.
  This measures use, not answer correctness or a conversion rate; no exposure
  denominator or attempt/result pair is required for this synchronous action.
- Event: `learner_interaction_placeholder_accepted`, emitted after accepting the
  input state update, before any later explicit answer submission.
- Population: Eligible guests and members in published course reading/listening
  and learner Profile onboarding. Exclude classroom mode, course previews, admin
  Profile previews, print rendering, readonly/history and disabled inputs.
  Existing centralized analytics account exclusions continue to apply.
- Count/deduplication: One event per accepted non-repeated keydown. Renders,
  held-key repeats and Tab on nonempty input emit nothing. Clearing the input
  and deliberately accepting again is another use; no persistent deduplication.
- Complete feature payload: `{ surface: 'course_read' | 'course_listen' |
  'profile_onboarding' }`. This is a low-cardinality non-personal enum needed
  to compare entry surfaces. No IDs, titles, hints, answers, variable names,
  URLs or errors are included. Shared transport owns pseudonymous identity.
- Consumer: Aggregate weekly usage by surface in Umami. New additive event;
  no existing checked-in dashboard or query needs migration or backfill.
  The classroom exclusion enforces this original population before rollout;
  event name, payload and downstream consumers are unchanged.
- Delivery: Shared `useTracking`; absent configuration, synchronous throws and
  rejected promises never affect filling, editing or submitting an answer.
- Verification: Assert exact event and payload, eligible and excluded hosts,
  repeat use versus rerender, observer failures and sensitive-field absence;
  use existing transport regressions for delivery and account exclusion policy.

## Outcomes & Retrospective

The application consumes the published `markdown-flow-ui@0.3.6` release. The
manifest, lockfile root, resolved package and clean-installed package all match
0.3.6. The lockfile uses the official registry tarball and its integrity, with no
local file dependency or dev version pin. Source and runtime validation are
complete; application PR review and CI remain the rollout gate.

Validation on 2026-10-30:

- Library: 89 unit files / 3,081 tests, 532 built-package tests and 83 Chromium
  browser stories across ContentRender and Slide passed, together with build,
  public export checking, lint and formatting.
- Application: clean `npm ci` and 13 focused Jest suites / 280 tests passed,
  covering completion/edit/submit, historical answer replay, renderer version
  checks, ESM/CJS editor loading, Slide package contracts and analytics.
- Type checking, lint, production build, touched-file formatting, repository
  harness, architecture boundaries and diff whitespace checks passed.
- Review follow-up: classroom eligibility and mode-switch tests reproduced two
  failures before the guard fix. Afterward, 13 focused suites / 284 tests and
  type checking passed, including a standalone-preview case with no observer.
- After integrating main: all 280 frontend suites / 3,590 tests and all 2,836
  offline MarkdownFlow backend tests passed. Production build, standalone type
  checking, lint and clean dependency installation also passed. Backend engine
  and browser-harness sources remain identical to upstream main.

## Context and Orientation

The library owns controlled interaction input state in CustomVariable and the
shared MarkdownFlowInput. Multi-select uses its own textarea. ContentRender,
MarkdownFlow and Slide must forward the optional notification without text.
AI Shifu hosts reading in ContentBlock, listening in ListenModeSlideRenderer,
and Profile questions in ProfileOnboardingConversation. Its admin reuses the
Profile renderer, so analytics must be enabled by the learner host explicitly.

## Plan of Work

Consume the component-library implementation and forward its optional completion
observer through reading, listening and learner Profile hosts. Add privacy-safe
analytics, preserve preview behavior, and verify the published artifact using
existing application regression and build checks.

## Concrete Steps

1. Install the exact published 0.3.6 release and generate the lockfile with npm.
2. Forward the completion observer through reading, listening and Profile hosts,
   enabling analytics only for eligible learner surfaces.
3. Run focused regression tests, type checking, lint, production build,
   repository harness, architecture boundaries and the pre-commit gate.
4. Open the application integration PR and inspect CI before merging.

## Validation and Acceptance

Cover text-only, single-select plus text, and multi-select plus text. Verify full
hint insertion, edit/submit, selected-value preservation, focus and caret, normal
Tab after filling, clearing/refilling, restored answers, changing questions,
rerenders and all guarded inputs. Verify ordinary follow-up inputs remain native.
Test analytics at its producers and the shared transport, including failures.
Local failures must be fixed or explicitly recorded; never claim a published
release or deployed behavior based solely on local checks.

## Idempotence and Recovery

Use `npm ci` to reproduce the committed dependency tree. Keep dependency pins at
published release versions and never commit temporary local tarball references.
Roll back this integration as a whole if necessary so the completion observers,
analytics producers and library version retain one compatible contract.

## Interfaces and Dependencies

- `MarkdownFlowInputProps.onAcceptPlaceholder?: (value: string) => void` enables
  standalone completion and delegates controlled state to the host.
- `onPlaceholderAccepted?: () => void` on interaction/render/flow/slide props
  reports accepted use without text. Existing props and submission payloads stay
  compatible; callbacks are optional and isolated from the main operation.
- The final application dependency must be an exact published release version;
  lockfiles are generated using npm in their owning package directories.
