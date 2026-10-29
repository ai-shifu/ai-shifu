---
title: Compatible interaction variable markers
status: completed
owner_surface: backend
last_reviewed: 2026-10-27
---

# Compatible interaction variable markers

## Purpose / Big Picture

Accept both `?[%{{key}} A | B]` and `?[{{key}} A | B]` as the same named
interaction. Keep `{{key}}` outside a leading interaction binding as a read.
Preserve option parsing, opaque key names, memory admission and fresh-answer
semantics across the Python library, remark parser and native 2.0 engine.

## Progress

- [x] 2026-10-27 21:14 CST: Inspected current parsers, marker boundaries and
  named-answer producers/consumers; refreshed origin/main before implementation.
- [x] 2026-10-27 21:21 CST: Verified and published the Python and remark
  dependency fixes as markdown-flow 0.4.3 and remark-flow 1.4.2.
- [x] 2026-10-27 21:18 CST: Updated native collection, substitution protection
  and interaction hints; added named-answer and literal-boundary coverage.
- [x] 2026-10-27 21:21 CST: Integrated exact release pins; 2,853 backend and
  67 frontend tests passed, including native engine and affected host contracts.
- [x] 2026-10-27 21:21 CST: Prepared focused dependency PRs and the application
  change for review; recorded validation and publication evidence below.

## Surprises & Discoveries

- The frontend parser is owned by `remark-flow`, also consumed by
  `markdown-flow-ui`; changing only application parsing would leave rendering
  inconsistent.
- The published Python dependency is newer than its main branch. Preserve the
  currently pinned release's ancestry when preparing the compatibility fix.
- Native memory admission currently recognizes only percent declarations;
  merely changing option parsing would silently discard bare-marker answers.

## Decision Log

- The percent prefix is optional only for the leading variable in `?[...]`.
  Global reference/assignment grammar remains unchanged.
- Reuse existing named-answer UI and submission paths. This syntax correction
  introduces no new user action or analytics event/schema; existing interaction
  tracking keeps its current trigger, population and payload.
- Do not merge any pull request into main. Keep dependency delivery and the
  application change reviewable on feature branches.

## Outcomes & Retrospective

Both spellings now bind the same named answer across production parsing,
browser rendering and native 2.0 execution. Real image labels cannot introduce
controls or bare collection declarations; unfinished and undefined image
notation retains its existing renderable behavior. No database or answer
migration was needed. The implementation is ready for review and is not
merged or deployed.

Validation passed: 2,853 backend tests (complete offline engine suite plus
affected Profile/course hosts), 67 frontend tests, 1,188 Python library tests,
647 remark unit tests and 55 real remark pipeline tests. Library build and
lint gates passed. Repository pre-commit checks passed after regenerating and
staging the new plan's documentation indexes. The Python library used its
required mypy 1.18.2 source runtime because the local compiled extension
stalled; no checks or rules were disabled.

## Context and Orientation

`src/api/markdownflow/engine/script.py` owns collection and memory projection.
`engine/tools.py` reads authored choices and text hints. The portable
`markdown-flow` Python package owns production 1.0 parsing; `remark-flow` owns
browser parsing. App pins live in `src/api/requirements.txt` and
`src/web/package.json` plus its generated lockfile.

## Plan of Work

Fix both published parser libraries with focused regression coverage. Teach
the native engine to treat leading bare markers as collection declarations,
preserve them during host substitution and exclude stale memory. Update model
guidance and canonical contracts together. Consume verified package builds and
exercise parsing through named-answer submission and engine persistence.

## Concrete Steps

1. Prepare isolated dependency checkouts and tests without editing installed
   shared packages.
2. Implement context-limited binding recognition in the native engine.
3. Publish validated dependency builds from feature branches and update pins.
4. Run the complete offline engine suite, affected host/frontend tests and
   repository gates; open focused pull requests.

## Validation and Acceptance

Both spellings must produce the same binding, ordered option values, selection
mode and text input. Real engine answers survive serialization and produce a
memory update. Earlier values cannot fill a new binding. Ordinary references,
escaped/literal examples, invalid markers and non-leading markers keep their
existing behavior. Run `python -m pytest tests/markdownflow/ -q`, affected
Profile/course tests, frontend compatibility tests, dependency gates and the
repository harness/architecture checks.

## Idempotence and Recovery

No database migration or stored-data rewrite is required. Keep the old percent
form valid. Package versions are immutable; confirm registry availability before
updating exact pins, and regenerate lockfiles using npm commands only.

## Interfaces and Dependencies

Question specs, event payloads, named-answer request DTOs and persisted key
identity stay unchanged. Only the authored leading marker spelling expands.
Dependency delivery:

- [remark-flow PR 43](https://github.com/ai-shifu/remark-flow/pull/43): release
  1.4.2, verified in npm and installed by the app; markdown-flow-ui shares the
  exact override. [Publish run](https://github.com/ai-shifu/remark-flow/actions/runs/40509850053).
- [markdown-flow-agent-py PR 81](https://github.com/ai-shifu/markdown-flow-agent-py/pull/81):
  release 0.4.3, stacked on PR 80's currently published 0.4.2 source rather than
  the obsolete main branch. [Publish run](https://github.com/ai-shifu/markdown-flow-agent-py/actions/runs/40511227502).
