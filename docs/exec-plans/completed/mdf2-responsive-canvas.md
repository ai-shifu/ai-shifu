---
title: Responsive canvases for newly generated MarkdownFlow 2.0 visuals
status: completed
owner_surface: learner
last_reviewed: 2026-10-20
---

## Purpose / Big Picture

Newly generated lesson visuals must remain compact in reading mode and use the
available canvas in listening and projection. A full-height white wrapper around
a short painted cover is not a full-stage composition. Preserve the reading
height corrections in markdown-flow-ui PRs #255 and #256 and the prompt correction
in markdown-flow-agent-py PR #51.

## Progress

- [x] 2026-10-20 CST: Confirmed clean, current main and inspected published prompt
  and renderer implementations and the three historical PRs.
- [x] 2026-10-20 CST: Updated the sandbox and listening prompt contracts.
- [x] 2026-10-20 CST: The four request-level tests pass; substituting the original
  prompts produces two expected failures. All 1,043 offline engine tests pass.
- [x] 2026-10-20 CST: Compared four synthetic reproduction cases, two runs each,
  before/after using the observed course model and temperature 0.3. Retained raw
  output, initial-candidate failures and one failed provider attempt.
- [x] 2026-10-20 CST: Verified 152 browser geometry records with the pinned 0.2.35
  renderer: 52 reading, 52 listening and 48 projection. Captured representative
  visual comparisons and verified a fullscreen exit restores the original size.
- [x] 2026-10-20 CST: Ruff, formatting, diff checks and repository harness pass;
  regenerated the plan index and document inventory.

## Surprises & Discoveries

The checked-in web dependency is 0.2.35, while the local installed copy is 0.2.24.
The existing arena independently pins 0.2.29 and drives the 1.0 engine. Neither is
evidence for this 2.0/pinned-renderer acceptance. The local backend environment
also lacks pydantic-ai. Use isolated, ignored acceptance dependencies.

The initial prompt revision generated extra visuals without a complete root in
two runs. Added explicit complete-root and authored-screen-count guidance, then
reran all eight candidate cases. The final runs each produced one complete visual.
One provider request failed without reported usage; a subsequent retry succeeded,
and the failed record remains available.

PR review identified that listening instructions also reach portable `generic`
and `none` render profiles. Moved the complete-canvas listening guidance into the
sandbox-only visual fragment; shared listening guidance now defers to the host.
The request tests explicitly reject leaked viewport/full-canvas requirements in
both portable profiles. The real generation/browser comparison above covers the
canvas revision before this wording relocation; the scoping follow-up is covered
by the repeated offline suite.

## Decision Log

- 2026-10-20: User selected new generation only. Do not rewrite stored HTML,
  change renderers, APIs, dependencies, model selection or database contracts.
- 2026-10-20: Retain the existing root template, em sizing, small padding and
  prohibitions on fixed root height, global centering and overflowing decorations.
- 2026-10-20: Put the main background on the root and permit growing inner layout
  regions without nested viewport minimums or fixed spacer content.

## Outcomes & Retrospective

Implementation and bounded local acceptance are complete.
The final eight outputs have painted root canvases in all tested modes. Across
24 reading checks, host and content heights differ by less than one pixel.
Across 48 presentation checks, canvas and viewport sizes match. All 152 measured
cases have no detected text/image boundary clipping or failed images.

At 1000px reading width, the original PR #255 and #256 fixtures occupy 240px and
283px respectively. The same new cover occupies 514px in reading and 720px in a
1280px-wide listening stage. Fullscreen expands the canvas and exit restores
1280 by 720. Four representative before/after screenshots were visually checked.

The private report and raw evidence are in the ignored local run directory
`artifacts/runs/mdf2-responsive-20261020/`. This is synthetic input generation
through Engine/GatewayModel/chat_llm with local trace/usage sinks, followed by
official component rendering. It is not a production trace replay or logged-in
full-course acceptance; TTS, production deployment, other models and device-level
readability remain outside this local test. Portrait small text reaches 10.2px.

## Context and Orientation

`src/api/flaskr/service/learn/agent/engine/prompts/html_display.md` owns sandbox
visual rules; `listen_mode.md` adds visual/narration pacing. `Engine` composes
these into requests. The host's unchanged markdown-flow-ui 0.2.35 relaxes root
viewport minimums only in reading mode; its presentation scaling retains them.

## Plan of Work

Make the root the actual canvas, restore the white-background explanation and
clarify the difference between root height and inner composition. Replace the
short-card cue with a complete low-density screen while preserving narration
exceptions. Exercise actual engine requests and inspect real generated output.

## Concrete Steps

Run the new visual contract tests, then the complete offline engine suite.
Retain baseline prompt copies and private evaluation artifacts under the ignored
`artifacts/runs/` tree. Compare the reported cover, a semiconductor question,
a timeline and a dense page, with frozen model/parameters/inputs per pair.
Render raw outputs without manual repair, using the exact 0.2.35 package.
Use isolated dependencies in the ignored run directory; the existing local
backend and frontend dependencies do not match the current repository pins.

## Validation and Acceptance

Reading reserves natural content height, without blank screen-sized tails.
Listening/projection fills the visible stage with the main canvas and balances
content instead of packing it into a top strip. All meaningful text and media
remain visible at 16:9, 4:3 and portrait sizes and across fullscreen round trips.
Intentional white designs and negative space are not failures. Preserve the
original PR #255/#256 compact-card fixtures and evaluate their reading behavior.
Run `tests/service/learn/agent/engine/`, Ruff for touched tests and
`python scripts/check_repo_harness.py`. Record model/browser evidence separately.

## Idempotence and Recovery

No production course or learner data is changed. Retain raw responses and inputs
before rendering; do not regenerate successful outputs after a rendering failure.
Rollback is reverting the two prompt changes. Do not commit, push or deploy
without the user's separate instruction.

## Interfaces and Dependencies

No interface or dependency changes. Validation uses the course's observed
`ark/deepseek-v4-1-flash-260910` route and temperature 0.3 when available through
the existing gateway. If unavailable, record the blocker without substituting a
different model and claiming equivalent acceptance.
