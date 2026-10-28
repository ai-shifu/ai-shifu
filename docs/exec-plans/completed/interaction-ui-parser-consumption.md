---
title: Consume the compatible interaction parser in rendered UI
status: completed
owner_surface: frontend
last_reviewed: 2026-10-28
---

# Consume the compatible interaction parser in rendered UI

## Purpose / Big Picture

Both `?[{{goal}} A | B]` and `?[%{{goal}} A | B]` must render A/B and
submit the named `goal` answer through the actual UI package in learning,
preview and Profile flows. Direct parser tests alone do not establish that
the rendered component consumes that parser.

## Progress

- [x] 2026-10-28 12:34 UTC: Reproduced an unnamed bare binding in the installed
  `markdown-flow-ui@0.3.3` renderer and its real `onSend` callback.
- [x] 2026-10-28 12:46 UTC: Identified the two vendored parser factory entries
  and verified a compatible factory bridge with Webpack resolution.
- [x] 2026-10-28 13:06 UTC: Verified the Turbopack relative-request alias in a
  real browser; both markers render A/B and the bare answer submits `goal`.
- [x] 2026-10-28 13:21 UTC: Verified the same bridge in a production build and
  connected shared canonical mappings to Next and Jest.
- [x] 2026-10-28 13:32 UTC: Real-package callback/replay regressions, all 3,558
  frontend tests on Node 22.23.4, type checking, lint and architecture checks
  passed. Actual application development routes and shared i18n also passed.
- [x] 2026-10-28 13:35 UTC: Regenerated documentation indexes; development-tool
  verification and all repository pre-commit gates passed.

## Surprises & Discoveries

- The published UI contains `remark-flow@1.4.1` under `dist/node_modules`.
  An npm override updates the dependency tree without replacing that code.
- The preserved vendor entries export a CommonJS `__require` factory. Aliasing
  them directly to the public parser entry breaks their import contract.
- Turbopack does not match the absolute vendor-file alias used by Webpack.
  Its exact relative requests must be derived from the same canonical entries.
- Turbopack alias targets are relative to the application directory, even when
  its explicit watch root encloses that directory. Keep the repository watch
  root separate from this mapping; keep the bridge target application-relative
  and preserve the application's existing workspace-root inference.
- The UI library's formal workflow requires a confirmed commit on `main`.
  This task forbids merging to `main`; application delivery must not depend
  on bypassing that workflow or committing a prerelease dependency.

## Decision Log

- Keep the released UI pin and consume the already published parser 1.4.2
  through a versioned application resolver bridge.
- Centralize the two vendor entry definitions. Derive Webpack/Jest absolute
  file mappings and Turbopack relative-request mappings from those entries.
- Preserve the `__require` interface and resolve the public parser from an
  application module outside the vendor tree. Do not edit installed packages
  or mutate an internal plugin array.
- Test actual renderer callbacks and replay, not a mock or direct parser only.
- Escaped physical newlines inside a destination remain non-image notation.
  The browser and production Python parser retain the real interaction;
  MarkdownIt's different acceptance is not the product contract. See
  [CommonMark destinations](https://spec.commonmark.org/0.31.2/#link-destination).
- The syntax alias uses the existing interaction and analytics paths. No event
  name, payload, eligibility or submission contract changes.

## Outcomes & Retrospective

The application bridge and repository verification gates passed. Both forms render A/B, submit
`goal` and replay the answer through the actual released renderer. Development
and production browser checks use the same helper and bridge; unrelated direct
parser imports remain unchanged.

The corrected upstream UI is tracked in
[markdown-flow-ui PR #291](https://github.com/ai-shifu/markdown-flow-ui/pull/291).
Its formal publication is a separate release process. Remove the application
bridge only after a released UI package passes these installed-bundle tests
with the mappings disabled. No main-branch merge or formal UI publication is
part of this application integration.

## Context and Orientation

The installed UI's `_virtual/index.es.js` and `_virtual/index.cjs` import the
corresponding `dist/node_modules/remark-flow/dist/index` factory files.
`src/web/next.config.ts` configures development and production bundlers; Jest
uses `src/web/jest-resolver.cjs` for the same canonical resolution. Definitions
live in `src/web/src/config/markdown-flow-parser-aliases.cjs`; the factory is
`src/web/src/lib/markdown-flow-parser-bridge.cjs`. The real renderer regression
lives in `src/web/src/__tests__/markdown-flow-variable-bindings.test.tsx`.
The original syntax delivery is recorded in
`interaction-variable-syntax.md`.

## Plan of Work

Prove the factory adapter in isolated Next development and production fixtures.
Then integrate shared mappings into application configuration and retain a
regression that fails with the unadapted released UI. Verify existing learning,
preview and Profile submission coverage before making the change reviewable.

## Concrete Steps

1. Capture the old renderer's empty `variableName` for a bare binding.
2. Bridge both preserved module formats to the pinned public parser.
3. Prove real browser rendering and submission under both Next bundlers.
4. Wire Next and Jest to the shared definitions and run focused and full gates.
5. Record upstream UI PR #291 as the destination for eventual bridge removal.

## Validation and Acceptance

Both marker forms must show A/B, submit `variableName: "goal"` and the selected
value, and replay the submitted answer correctly. Invalid destination line
breaks must retain named controls. Direct parser imports must remain ordinary
public imports. Type checking, lint, frontend tests, architecture validation and
repository checks must pass. CI and review follow-up for the resulting head
remain tracked on PR #3221; this implementation plan covers the local consumer
integration and its observable acceptance.

## Idempotence and Recovery

The bridge and mappings are ordinary versioned application files. Reverting
their commit restores existing resolution; no package mutation, schema change
or data migration is involved. Keep the actual-package regression when the
bridge is removed for a future release.

## Interfaces and Dependencies

Keep `markdown-flow-ui@0.3.3` and `remark-flow@1.4.2` release pins. Preserve the
vendor `__require` factory, `ContentRender` props and `OnSendContentParams`.
Backend parser release 0.4.9 and stored answer identities remain unchanged.
