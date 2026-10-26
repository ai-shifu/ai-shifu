# Generated-slide timeline delivery

## Purpose / Big Picture

Allow learners to select already-generated lesson slides independently from
checkpoint restoration. Durable behavior and analytics live in
`docs/product-specs/learner-listen-playback.md`.

## Progress

- [x] 2026-09-26: Separated this scope from playback checkpoint stability.
- [x] 2026-09-26: Verified merged PR #2778 (`b061be121`) and successful
  backend, frontend, static, formatting and runtime-harness CI checks.
- [x] 2026-09-26: Confirmed the PR's recorded renderer/package/integration
  acceptance (68 cases) and prior listen-mode acceptance (102 cases).

## Surprises & Discoveries

The old playback plan still listed timeline implementation as pending despite
the merged, verified delivery. Its temporary dev pin is historical.

## Decision Log

- Separate logical-item checkpoint stability from slide navigation.
- Keep a visual page finder as an optional debt-tracker proposal.

## Outcomes & Retrospective

Timeline delivery is complete. This audit re-read merge/CI evidence; it did
not rerun real-browser acceptance or publish a component package.

## Context and Orientation

`ListenModeSlideRenderer` consumes the released `markdown-flow-ui` timeline and
tracks eligible exposure plus accepted navigation. The component owns selection.

## Plan of Work

The delivered change integrates the component timeline, maps the generation
lifecycle and adds fail-open analytics without changing saved checkpoints.

## Concrete Steps

For a regression, inspect renderer, package-contract and integration suites
under `src/web/src/app/c/[[...id]]/Components/ChatUi/`, run the focused cases,
and verify the released component pin before changing integration behavior.

## Validation and Acceptance

Only generated slides are selectable. Selection stops the previous audio,
waits for missing target audio and retains partially generated visuals.
Tests cover preview exclusion, event payloads and deduplicated exposure.

## Idempotence and Recovery

Keep checkpoint storage compatible. Revert application integration separately
from a library release; never replace a release pin with a dev pin on main.

## Interfaces and Dependencies

Depends on the published MarkdownFlow timeline API. Thumbnail previews and a
cross-device page finder are deferred, with design dependencies in the debt tracker.
