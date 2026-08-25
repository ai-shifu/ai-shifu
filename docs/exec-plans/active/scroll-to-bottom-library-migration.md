# Scroll-to-bottom ownership migration

## Purpose / Big Picture

Move learner-page scroll-to-bottom presentation into the published
`markdown-flow-ui` package so the library owns the reusable behavior and
AI-Shifu only supplies its content ref, portal target, and layout context.

## Progress

- [x] 2026-08-24 11:00 UTC: Published `markdown-flow-ui@0.2.14` with public
  hook/button exports and working ESM/CJS package targets.
- [x] 2026-08-24 11:00 UTC: Replaced NewChatComp's generic scroll state,
  listeners, icon, and dedicated styles with the library API.
- [x] 2026-08-24 11:00 UTC: Passed focused Jest, TypeScript, lint, format,
  translation, harness, and architecture checks; missing ruff remains an
  environment-only dev-tool failure.
- [ ] Create ready PRs and complete CI/review follow-up.

## Surprises & Discoveries

- The existing package's CJS files used `.cjs.js` under `type: module` and
  preserved pnpm-resolved dependency paths, so a real packed consumer failed.
- The package emits `.cjs` files for CommonJS consumers; CSS is provided
  through the published CSS entry rather than runtime JS imports.

## Decision Log

- Use `useScrollToBottom` for target resolution, threshold state, follow mode,
  ResizeObserver, viewport changes, and reduced-motion scrolling.
- Use `ScrollToBottomButton` for the accessible icon button and optional portal;
  AI-Shifu supplies only host positioning classes and its localized label.
- Keep the lesson-feedback scrollability check local because it controls a
  separate feedback observer root, not scroll-button presentation.

## Outcomes & Retrospective

The library is now the owner of the generic behavior and the AI-Shifu page no
longer duplicates its algorithm. Remaining work is CI closure and browser-level
visual confirmation.

## Context and Orientation

The library branch is `sunner/migrate-scroll-down` in the markdown-flow-ui
worktree. The AI-Shifu branch uses a separate worktree at
`/private/tmp/ai-shifu-scroll-down` and consumes the released `0.2.14` pin.

## Plan of Work

1. Build and publish the library primitive and package entrypoint fixes.
2. Replace NewChatComp's generic scroll implementation while preserving
   feedback, print, listen/classroom/read mode, and mobile portal behavior.
3. Validate both repositories, create ready PRs, and close CI/review feedback.

## Concrete Steps

- Run library focused tests, build, pack, and ESM/CJS/type consumer imports.
- Run AI-Shifu focused Jest, type-check, lint, format, translations, harness,
  architecture, and dev-tool checks.
- Push branches, create ready PRs, inspect required checks and review threads.

## Validation and Acceptance

Acceptance requires a published release package whose packed ESM/CJS imports
expose `useScrollToBottom`, `ScrollToBottomButton`, and
`ScrollableMarkdownFlow`; AI-Shifu must pin that release and contain no old
generic scroll state, algorithm, icon, or dedicated style block.

## Idempotence and Recovery

The library release workflow is branch-scoped and version-validated. If a
release or CI run fails, inspect its logs and publish the next unused release
version; do not rewrite published versions or modify another worktree.

## Interfaces and Dependencies

- `markdown-flow-ui/scroll` and `markdown-flow-ui/renderer`:
  `useScrollToBottom`, `ScrollToBottomButton`,
  `ScrollableMarkdownFlow`.
- AI-Shifu `NewChatComp.tsx`: content ref, localized aria label, portal target,
  and host layout classes.
- AI-Shifu `module.chat.scrollToBottom`: localized accessibility label in all
  supported locales.
