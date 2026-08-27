# MarkdownFlow Scroll Controls

## Purpose / Big Picture

Upgrade Cook Web to `markdown-flow-ui@0.2.15` and let the library own the
scroll-to-bottom behavior in the learner read-mode conversation and the
profile-onboarding conversation. Users should get the same visibility,
accessibility, reduced-motion, and click-to-bottom behavior in both surfaces
without duplicate host-side scroll state machines or automatic content follow.

## Progress

- [x] 2026-08-27 12:12 CST: Refreshed `origin/main`, created local branch
      `sunner/use-markdown-flow-scroll-controls`, and confirmed the worktree is
      clean.
- [x] 2026-08-27 12:20 CST: Upgraded the exact MarkdownFlow UI dependency and
      verified the package and lockfile tuple.
- [x] 2026-08-27 12:24 CST: Replaced both host-owned scroll implementations with
      `ScrollToBottomControl`.
- [x] 2026-08-27 12:28 CST: Added shared localization, locale routing, and focused
      regression tests.
- [x] 2026-08-27 12:42 CST: Completed automated validation and learner browser
      acceptance, recorded the authenticated profile-browser limitation, and
      prepared this plan for `docs/exec-plans/completed/`.
- [x] 2026-08-27: Explicitly disabled `followNewContent` in both consumers to
      preserve the existing user-controlled scrolling behavior during content
      generation.

## Surprises & Discoveries

- The learner surface owns a visible button plus target resolution, scroll
  listeners, and resize observation. Its independent lesson-feedback observer
  root must remain after the button logic moves to the library.
- Profile onboarding has no visible button today, but it owns an imperative
  `scrollIntoView` effect. The library control must target only the inner
  question viewport so the surrounding dialog or page never moves.
- The root layout already imports `markdown-flow-ui/dist/markdown-flow-ui.css`,
  so the new scroll subpath needs no additional stylesheet import.
- npm `10.9.2` still rewrites optional dependency `dev` metadata during `ci` in
  this lockfile. The final diff must restore those unrelated fields after the
  install while preserving the MarkdownFlow UI pin, tarball, and integrity.

## Decision Log

- Decision: Use the lightweight `markdown-flow-ui/scroll` export in both
  surfaces.
  - Why: It provides the complete control without routing through the renderer
    bundle.
- Decision: Keep the profile-onboarding viewport and memoized renderer instead
  of replacing them with `ScrollableMarkdownFlow`.
  - Why: The existing viewport owns `aria-busy`, overscroll, scrollbar gutter,
    and responsive padding that should not move behind an opaque wrapper.
- Decision: Store the shared label under `common.core.scrollToBottom` in all
  five locales.
  - Why: The control is shared by learner chat and profile onboarding rather
    than owned by a single chat module.
- Decision: Pass `followNewContent={false}` from both host surfaces.
  - Why: Before this migration, content growth only updated button visibility;
    scrolling happened after an explicit user action. The library default is
    automatic follow, so the host must preserve its existing product behavior
    explicitly.
- Decision: Leave PR #2657 and `/private/tmp/ai-shifu-scroll-down` untouched,
  and keep this work local without commits, pushes, or a new PR.
  - Why: The requested delivery is an isolated local implementation from the
    latest main branch.

## Outcomes & Retrospective

- Cook Web now pins `markdown-flow-ui@0.2.15` exactly, with lockfile changes
  limited to the root pin and the package version, tarball, and integrity.
- Learner read mode and profile onboarding both delegate scroll visibility,
  listeners, accessibility, and reduced-motion behavior to
  `ScrollToBottomControl`. The learner keeps its feedback-only observer root;
  profile onboarding keeps its memoized renderer and scrolls only its local
  viewport. Both explicitly disable automatic following while content grows.
- Focused coverage passed for the two surfaces and locale mapping. The full
  frontend run passed 179 suites and 1,585 tests, along with type-check, lint,
  changed-file formatting, and the production build. Translation parity and
  usage, language metadata, architecture boundaries, repository harness,
  development-tool validation, the complete lefthook pre-commit suite, and
  diff whitespace also passed.
- Browser acceptance on the learner page confirmed the Chinese accessible
  label, visibility away from the bottom, click-to-bottom hiding, and
  reappearance after user-initiated upward scrolling. Desktop and narrow
  viewport screenshots are stored under `output/playwright/`.
- The profile-onboarding route redirects to login in both isolated and existing
  browser contexts, so its live authenticated dialog could not be exercised
  without fabricating credentials. Its local viewport target, initial follow,
  content-version updates, label, layout, and assistant-view hiding are covered
  by focused host-contract tests; Arabic and Thai routing and labels are covered
  by locale and translation checks.

## Context and Orientation

- `NewChatComp` owns the learner read-mode conversation, its bottom anchor, and
  the current custom button.
- `ProfileOnboardingConversation` owns the scrollable profile-question viewport
  and the current imperative bottom-anchor effect.
- `resolveMarkdownFlowLocale` maps application locales to the library's locale
  union.
- Shared user-facing strings live under `src/i18n/<locale>/common/core.json`.

## Plan of Work

1. Upgrade the exact frontend dependency with the repository-required Node and
   npm versions, then inspect the lockfile for unrelated churn.
2. Wire `ScrollToBottomControl` into the learner and profile-onboarding
   surfaces while removing only the superseded host scroll code.
3. Add five-language labels, extend locale mapping, regenerate types, and add
   focused tests around each host/library interface.
4. Run focused and full checks, exercise both controls in a browser, and record
   evidence before completing this plan.

## Concrete Steps

1. Run npm `10.9.2` under Node `22.16.0` with a task-specific cache to install
   exact `markdown-flow-ui@0.2.15` without lifecycle scripts.
2. In learner read mode, pass the existing viewport and end refs and preserve
   the desktop/mobile positioning and page-fallback behavior through library
   props. Remove the custom state, listeners, icon, and SCSS.
3. In profile onboarding, add a viewport ref and use it as the explicit local
   scroll target. Enable initial scrolling and pass `items.length` as the
   content version without an end ref.
4. Add `common.core.scrollToBottom`, support Arabic and Thai MarkdownFlow
   locales, regenerate typed keys, and update tests.
5. Run repository checks and browser acceptance, then regenerate the knowledge
   index after moving this plan to completed.

## Validation and Acceptance

- Both surfaces render `ScrollToBottomControl` from the scroll subpath with a
  localized accessible label.
- Learner desktop and mobile layouts retain their current offsets and portal
  behavior; listen and classroom modes do not render the control.
- Profile onboarding scrolls only the question viewport, does not follow
  generated content automatically, and hides with the question view when the
  assistant view is open.
- English, French, Chinese, Arabic, and Thai translations remain in parity;
  Arabic and Thai resolve to native MarkdownFlow locales.
- Focused Jest tests, full Jest, type-check, lint, formatting, production build,
  translation checks, architecture checks, repository harness, lefthook, and
  `git diff --check` pass.
- Learner browser checks confirm control visibility and click-to-bottom
  behavior. Focused tests cover mobile positioning, localized labels, disabled
  automatic follow, and profile onboarding's internal-only scroll target and
  assistant-view hiding; the authenticated profile dialog was not exercised in
  the browser.

## Idempotence and Recovery

- Re-running the exact npm install should leave the dependency files unchanged.
- Generated i18n and knowledge artifacts must be deterministic; review their
  diffs after every generator run.
- If a validation tool rewrites unrelated tracked files, stop and restore only
  that tool-owned incidental change without touching user work or the protected
  temporary worktree.
- No remote state is changed, so the local branch can be inspected or discarded
  independently after handoff.

## Interfaces and Dependencies

- Dependency: exact `markdown-flow-ui@0.2.15`.
- Library interface: `ScrollToBottomControl` from `markdown-flow-ui/scroll`.
- Shared translation interface: `common.core.scrollToBottom`.
- Locale interface: `MarkdownFlowLocale` gains application routing for
  `ar-SA` and `th-TH`, including `ar` and `th` aliases.
- No backend, database, or network API contracts change.
