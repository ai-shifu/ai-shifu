---
title: Line wrap toggle for code blocks in rendered Markdown
---

## Purpose / Big Picture

Long lines in a code block currently scroll sideways, which is awkward on
phones and in narrow lesson layouts. Give every rendered code block a button
that switches between scrolling and wrapping long lines. The choice applies to
all code blocks and is remembered in the browser.

## Progress

- [x] 2026-11-27: Implemented the toggle, the browser-stored preference and its
  host observer in `markdown-flow-ui` on branch `sunner/code-wrap-toggle`, with
  unit tests, localized labels for all eleven library locales and API docs.
- [x] 2026-11-27: Added the learner analytics observer in Cook Web and validated
  it against a local tarball of the library build.
- [x] 2026-11-27: Opened [library PR #325](https://github.com/ai-shifu/markdown-flow-ui/pull/325).
- [x] 2026-11-27: Pinned the `markdown-flow-ui` 0.3.14 release, which contains
  the toggle, in `src/web/package.json` with an npm-generated lockfile.
- [x] 2026-11-27: Opened [application PR #3440](https://github.com/ai-shifu/ai-shifu/pull/3440).
- [ ] Review CI on the application PR and merge.
- [ ] Open since 2026-11-27: Check the toggle in a published course page in
  reading, listening and classroom modes, and in a lesson PDF.
- [ ] Open since 2026-11-27: Confirm `learner_code_block_wrap_toggled` arrives
  in Umami with the expected payload after deployment.

## Surprises & Discoveries

- `ContentRender` exposes no component override, so a host cannot add a control
  to the code block header without DOM injection. The control therefore belongs
  in the library, next to the existing copy button.
- Importing `markdown-flow-ui/renderer` statically from `ChatUi` would pull the
  renderer into the bundle that `ChatUi` deliberately defers with dynamic
  imports. The analytics observer imports it on demand instead.
- On Windows, Jest's default `testMatch` finds no tests when the checkout path
  contains a dot directory such as `.claude`. Passing
  `--testMatch "**/*.test.{ts,tsx}"` works around this local-only issue.

## Decision Log

- The preference is one global choice shared by every code block, stored in
  `localStorage` under `markdown-flow-ui:code-wrap` by the library. Storage
  failures fall back to an in-memory choice for the page, and other tabs follow
  a change through the `storage` event.
- The default stays unwrapped, matching current behavior. Server rendering and
  hydration use the default and apply the stored choice right after hydration.
- The toggle is an icon button with `aria-pressed` and a localized accessible
  name from the library `locale`; Cook Web adds no i18n keys.
- The lesson PDF print rule that forces wrapping keeps overriding the toggle.
  The wrap button is hidden in lesson PDFs, like the copy button.
- The library observer does not say which button was pressed, so the Cook Web
  hook remembers the press target and skips regions marked
  `data-code-wrap-tracking-excluded`. Profile onboarding carries that marker
  because its dialog opens over a mounted lesson.
- Cook Web observes toggles through the library's `subscribeCodeWrapToggle`
  instead of a prop on every renderer host. Programmatic changes and changes
  from other tabs are not reported, so one press yields one event.

### Product analytics contract

Follow [the canonical analytics rules](../../references/frontend-product-analytics.md).

- Business question: Do learners use code block line wrapping, on which
  learning surface, and do they turn it on or back off?
- Metric: Weekly toggles and distinct eligible users by surface and chosen
  state. This measures use of a synchronous control; no exposure denominator or
  attempt/result pair is required.
- Event: `learner_code_block_wrap_toggled`, emitted after the preference has
  changed in response to a press of the code block wrap button.
- Population: Eligible guests and members in published course reading,
  listening and classroom modes, including follow-up answers shown there.
  Course previews are excluded, and so are surfaces outside the learner course
  page such as the authoring editor preview and Profile onboarding. Existing
  centralized analytics account exclusions continue to apply.
- Count/deduplication: One event per accepted button press. Renders, restoring
  the stored preference, and changes arriving from another tab emit nothing.
  Deliberate repeated presses count again; no persistent deduplication.
- Complete feature payload:
  `{ surface: 'course_read' | 'course_listen' | 'course_classroom',
  wrap_enabled: boolean }`. Both are low-cardinality non-personal values needed
  to compare surfaces and the chosen state. No IDs, code content, languages,
  titles, URLs or errors are included. Shared transport owns pseudonymous
  identity.
- Consumer: Aggregate weekly usage by surface and state in Umami. New additive
  event; no existing checked-in dashboard or query needs migration or backfill.
- Delivery: Shared `useTracking`; absent configuration, synchronous throws,
  rejected promises and a failed renderer import never affect the toggle.
- Verification: Assert the exact event and payload keys, each surface, preview
  exclusion, surface changes, unsubscribe on unmount and tracking failures.
  With the installed renderer, assert that a real press still wraps the code
  when tracking fails and that a press inside Profile onboarding emits nothing; use
  existing transport regressions for delivery and account exclusion policy.

## Outcomes & Retrospective

Local validation on 2026-11-27:

- Library: 91 unit files / 3,133 tests passed and the package built.
- Application, with the published `markdown-flow-ui` 0.3.14 installed from
  npm: 308 Jest suites / 3,963 tests, type checking and lint passed.

## Context and Orientation

The library renders fenced code through `CodeBlock`, which owns the header with
the language name and copy button. The preference store lives in
`src/lib/codeWrapPreference.ts` in the library and is exported from
`markdown-flow-ui/renderer`. In Cook Web, `ChatUi` hosts the learner reading,
listening and classroom modes and knows whether the page is a preview, so it
mounts `useCodeWrapToggleTracking` from
`src/web/src/hooks/use-code-wrap-toggle-tracking.ts`.

## Plan of Work

Ship the control and preference in the library, then consume the published
build in Cook Web and add the learner analytics observer.

## Concrete Steps

1. Merge the library branch and publish a build that contains the toggle.
2. Pin that version in `src/web/package.json` and generate the lockfile with
   `npm install` in `src/web`.
3. Run the focused hook test, the full Jest suite, type checking, lint and the
   pre-commit gate.
4. Open the application PR and inspect CI before merging.

## Validation and Acceptance

- Every code block shows a wrap button beside the copy button. Pressing it
  wraps long lines in all code blocks; pressing again restores scrolling.
- After a reload, code blocks keep the last chosen state.
- Copying a wrapped code block yields the original lines without added breaks.
- A learner press emits one `learner_code_block_wrap_toggled` event with the
  current surface and state; a course preview emits none.

## Idempotence and Recovery

The change is additive. Reverting the library pin removes the button; revert
the application hook together with the pin, because the hook needs the library
export to type-check. A stored preference left in a browser is
ignored by library versions without the feature.

## Interfaces and Dependencies

- `markdown-flow-ui/renderer` exports `subscribeCodeWrapToggle`,
  `getCodeWrapPreference`, `setCodeWrapPreference` and `CODE_WRAP_STORAGE_KEY`.
- Cook Web depends on the first of these and on the shared `useTracking` path.
