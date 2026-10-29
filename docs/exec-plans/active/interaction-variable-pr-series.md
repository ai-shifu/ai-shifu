---
title: Integrate standard interaction bindings
status: active
owner_surface: learner
last_reviewed: 2026-10-29
---

# Integrate standard interaction bindings

## Purpose / Big Picture

Support `?[{{answer}} A | B]` as the standard authored interaction binding in
AI-Shifu. Existing percent-prefixed content remains compatible. Keep the
current question, storage, callback and analytics contracts, and make one small
integration PR for human review. Agents never merge into main.

The user approved and merged remark-flow #43, markdown-flow-ui #291 and Python
#82. Python #80 was closed without merging; its additional name/document parser
work and the old oversized application #3221 are not reconstruction bases.

## Progress

- [x] 2026-10-29: Verified Python #82's human merge at c32482b and started
  sunner/integrate-standard-interaction-bindings from application main 2bcab437.
- [x] 2026-10-29: The user explicitly authorized UI 0.3.4 from main at
  b04b26a877d32021bf45d3e57ad53fca0b306e9a. Publish run 40841207577 succeeded;
  the official registry and clean installed package match that commit.
- [x] 2026-10-29: Prepared native leading-binding collection and tool hints,
  preserving old-memory exclusion, admission and serialized answer identities.
- [x] 2026-10-29: Kept Python 0.4.2's required APIs and added the small shared
  parser adaptation used by Profile validation, learning and history readers.
- [x] 2026-10-29: Pinned UI 0.3.4 and remark 1.4.2, including the existing
  override, through an npm-generated lockfile and clean npm ci.
- [x] 2026-10-29: Updated canonical guidance and all eight default onboarding
  examples; existing saved author content and historical fixtures stay intact.
- [x] 2026-10-29: Frontend full suite passes: 278 suites, 3,556 tests. The
  targeted renderer/consumer tests, typecheck and lint also pass.
- [x] 2026-10-29: Restored the renderer's explicit rejection of multiline
  generated options after enabling multiline authored binding parsing. All
  380 targeted package, learning and Profile failure regressions pass.
- [x] 2026-10-29: Toolchain doctor and all-file hooks pass. The dependency-pinned
  backend gates pass: 2,746 native library tests and 1,910 learning/Profile tests.
- [x] 2026-10-29: Independent frontend and backend review completed. The fenced
  example regression is fixed and reverified; no actionable finding remains.
- [x] 2026-10-29: Created focused application PR #3238 against main.
- [ ] Finish the current-head CI/review after the literal-opener correction.
- [ ] Wait for the user's review; do not merge, deploy or start further work.

## Surprises & Discoveries

Both course and Profile execution use the native MarkdownFlow engine. The
external Python 0.4.2 package still supplies required normalization and parsing
APIs. The reviewed Python #82 source lacks some of those already-used modules,
so swapping the package would introduce an unrelated compatibility rollback.
Keep the pin and adapt only its leading-binding detector at the existing
interaction-rendering owner; reuse the rest of the package's parser.

The existing lockfile generator also recalculates 25 dev/devOptional flags.
A second generation with no installed dependency tree produces the same bytes;
other dependency versions do not change. Do not hand-edit the generated lock.

Local Python had pydantic-ai-slim 2.43.0 while requirements pins 2.53.0. Validate
with the pinned version rather than weakening historical session assertions.

Independent review found that removing a fenced example could join surrounding
text into an apparent standard binding. Recognize these bindings in the original
source instead; retain the legacy declaration path and cover old-memory access.

PR review identified that a literal unfinished `?[` could swallow a later real
binding during scanning. Mask only those literal openers before the new binding
scan. The regressions fail before the fix (9 failures) and pass afterward (38
tests), including accepted answers, save/restore and memory isolation.
The full native and learning/Profile gates and all-file hooks pass after this
correction; independent review confirms offsets and original boundaries remain.

## Decision Log

- Use current main, not #3221, as the application base.
- Preserve the current name grammar and native Markdown question boundaries.
  Do not add image/reference/resource parsing changes or captured fixture grids.
- Only an existing parsed question's leading standard binding declares a new
  answer key. Ordinary and nonleading references grant no new write permission.
  Legacy explicit percent declarations retain their established behavior.
- Collected answers remain excluded from old memory and recall until genuinely
  answered; pending answers, save/resume, replay and named writes share the
  existing contracts. No DTO, schema, key migration or new event is introduced.
- Keep the current serialized control representation for existing clients.
  New author examples and templates use the standard notation.
- Keep markdown-flow==0.4.2. One subclass in interaction_rendering.py overrides
  only its leading detector, using the native marker reader; all consumers use
  that owner. Newline-safe source parsing must not admit multiline typed option
  displays/values that the renderer cannot carry.
- Use only the officially published UI 0.3.4 and remark 1.4.2. No Webpack,
  Turbopack, Jest resolver or parser alias bridge is needed.
- Profile validation and historical matching compare equivalent parsed bindings;
  different keys and option contracts must still be rejected.
- Default locale templates change notation only. Do not rewrite saved courses,
  questionnaires or historical compatibility fixtures.
- Existing interaction analytics remain on the same action and payload paths.
  No new tracking data is collected for the source spelling.
- The UI release was explicitly approved; no Python release, application merge
  or deployment is authorized by this work.

## Outcomes & Retrospective

Implementation and local validation are complete with the reviewed UI artifact
and the current Python API baseline. Final PR verification remains. The delivery
stops at a reviewable application PR.

## Context and Orientation

The native declaration and substitution code is in engine/script.py; tool hint
parsing is in engine/tools.py. Both reuse engine/variable_names.py. The existing
portable interaction_rendering.py owns the pinned-parser adaptation. Course and
Profile hosts consume the same native engine and normalized answer key.

Frontend consumers already forward the renderer's canonical variableName. The
integration changes dependencies and regression tests rather than their request
mapping. The official UI source is b04b26a; its registry version is 0.3.4.

## Plan of Work

Finish the current integration only. Validate all changed producer/consumer
contracts together, open a non-draft PR against main, handle worthwhile in-scope
review feedback and leave the merge/deployment decision to the user.

## Concrete Steps

Run the toolchain doctor and all-file hooks. Freeze sources, then run native
engine, learning and Profile regressions with requirements-pinned Python 0.4.2
and pydantic-ai-slim 2.53.0. Run clean-install frontend tests, typecheck and lint
under Node 22.23.4. Check architecture and repository documentation harnesses.
Keep PR title/body aligned with the final implementation and verification.

## Validation and Acceptance

Cover standard and legacy bindings, ordinary references that grant no permission,
old-memory isolation, options and text hints, actual named-answer writes,
save/restore/replay, Profile validation and existing serialized controls.
Frontend tests execute the installed public renderer; mock host tests verify
learning/preview/Profile payloads and navigation. Historical prompt fixtures stay
unchanged; the prompt hash guard explicitly permits only the three changed
binding/reference instruction resources.

After each push, wait five minutes before refreshing feedback. End only when
all applicable exact-head checks are terminal and no new valid feedback is
unclassified. Quota-limited AI checks are not approvals.

## Idempotence and Recovery

Package versions are immutable; reuse the approved UI release and never republish
it. Keep the Python pin unchanged. A future deployment must ready every compatible
API instance before enabling the new authoring UI. The API preserves old wire
controls for existing clients. Do not treat a source PR as a completed rollout.
After standard authored content is used, rollback must retain syntax support.

## Interfaces and Dependencies

Application dependencies: markdown-flow 0.4.2, markdown-flow-ui 0.3.4 and
remark-flow 1.4.2. New syntax uses the same native named-answer and memory policy
interfaces. There are no new service boundaries, storage fields or event payloads.

Approved UI publication evidence:
https://github.com/ai-shifu/markdown-flow-ui/actions/runs/40841207577.
