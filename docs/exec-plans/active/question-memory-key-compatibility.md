---
title: Align frontend memory key parsing with the teaching engine
status: active
owner_surface: learner
last_reviewed: 2026-10-23
canonical: false
---

# Align frontend memory key parsing with the teaching engine

## Purpose / Big Picture

An authored interaction such as `?[%{{你的性别是？}} 男 | 女 | 秘密]`
already works in the backend, but the frontend treats its variable declaration
as part of the first button and submits under `input`. Repair this disagreement
without introducing a new interaction surface or changing stored keys.

## Progress

- [x] 2026-10-23 11:31 UTC: Reproduced the mismatch with the exact locked
  `markdown-flow-ui@0.2.35` package and `markdown-flow==0.3.4`.
- [x] 2026-10-23 11:31 UTC: Compared the legacy parser, engine collection and
  substitution, rendered interaction, editor extraction and submission paths.
- [x] 2026-10-23 11:52 UTC: Aligned the shared frontend parser and component
  editor helpers; verified the published `remark-flow@1.3.5` package.
- [x] 2026-10-23 11:52 UTC: Replaced the application editor's independent
  character whitelist and normalized preview/onboarding keys with the helper.
- [x] 2026-10-23 11:52 UTC: Verified the original question, ASCII question marks, existing identifiers,
  real rendered controls, submission and backend memory persistence.
- [x] 2026-10-23 12:03 UTC: Opened library PRs and published the opt-in
  `markdown-flow-ui@0.2.36-dev.1` package for application-branch validation.
- [x] 2026-10-23 12:13 UTC: Installed the registry package in the application;
  its integrity matches npm and 26 key built artifacts match the verified build.
- [ ] 2026-10-23 12:13 UTC: Open the application's integration PR.
- [ ] 2026-10-23 12:10 UTC: After the component library's formal release, replace the application's
  development pin with the verified release before merging.

## Surprises & Discoveries

- The renderer bundles its own `remark-flow` parser. Updating only the app's
  top-level parser dependency does not fix the rendered buttons.
- Local `node_modules` was older than the lockfile. The original reproduction
  therefore used the exact published package with matching lockfile integrity.
- The backend's current engine accepts nonempty names matching `[^{}\s]+`.
  The frontend editor and parser used different character whitelists.
- The public MarkdownFlow variable specification currently allows only Unicode
  letters, numbers and underscores and forbids punctuation and marker padding.
  The selected AI-Shifu engine compatibility rule is broader; this task does
  not claim that the public standard already permits question-mark names.
- Legacy Python parsing additionally accepts some whitespace and malformed
  names that the engine does not admit. A closing `]` inside an interaction key
  terminates the interaction in both existing runtimes. These are separate
  syntax-boundary differences, not prerequisites for the question-mark repair.
- The user explicitly selected the existing 2.0 name rules as the frontend
  baseline and requested preserving the legacy backend's permissive behavior.

## Decision Log

- Preserve exact key identity, punctuation and case; never rename historical
  values or map a question key to a system profile field.
- Use one exported frontend name rule and extraction helper in `remark-flow`,
  consumed by the component editor and the application editor.
- Keep legacy backend whitespace and malformed-name compatibility unchanged.
  Align ordinary frontend authoring with the current 2.0 name rule instead of
  extending the grammar or migrating previously stored names.
- Preserve existing interaction delimiters, button values, selection modes,
  code fences and submission protocols.
- This repairs the existing named-interaction and preview paths. It adds no
  action, invocation path or analytics payload. Existing analytics remain
  independent of the operation, and question text must never be tracked.
- Never merge any repository into `main`. The component library's current
  release policy requires a maintainer merge followed by human confirmation
  of the exact version and `main` commit before a formal release.

## Outcomes & Retrospective

The parser repair is available as `remark-flow@1.3.5` and is reviewed in
[remark-flow PR #41](https://github.com/ai-shifu/remark-flow/pull/41).
The editor and bundled-renderer repair is prepared for `markdown-flow-ui@0.2.36`
in [UI PR #258](https://github.com/ai-shifu/markdown-flow-ui/pull/258).
The application branch pins the registry-published
`markdown-flow-ui@0.2.36-dev.1` package. Its parser, editor and renderer artifacts
are byte-identical to the verified build, and nine tests against the downloaded
package pass. The component library has not been formally released; replace
the development pin after that release before merging. No PR has been merged.

Validation includes 239 parser unit cases, 22 real Markdown pipeline cases,
the component library's full unit suite and built-renderer checks, all 3,300
application frontend tests, all 1,108 backend offline engine tests and a focused
54-case compatibility suite. Type checking, architecture boundaries, the
repository harness and the full pre-commit gate pass. A separate check compared
the frontend name/trim semantics against Python for every Unicode codepoint.

## Context and Orientation

- `src/web/src/components/shifu-edit/ShifuEdit.tsx` independently extracts names
  for recent variables and automatically unhiding variables used in preview.
- `remark-flow/src/interaction-parser.ts` interprets the interaction sent by
  both backend runtimes; its AST integration must preserve the same key.
- `markdown-flow-ui` embeds that parser and has its own editor validation,
  extraction, placeholder and syntax highlighting helpers.
- `src/api/flaskr/service/learn/agent/engine/script.py` owns current engine
  variable collection and substitution. `legacy_protocol.py` emits the
  interaction string that the browser consumes.

## Plan of Work

Fix the shared parser, consume its helper in both editors, and test a common
corpus against real frontend AST/rendering and backend memory processing.
Package the libraries and verify their actual built output, rather than
relying solely on source-level parser tests.

## Concrete Steps

1. Work on `sunner/question-memory-keys` from current remote `main` in each
   repository, preserving the user's existing library checkouts.
2. Implement shared name recognition and compatibility regressions.
3. Build the parser and component library, then test the app with those builds.
4. Run focused app tests, type/lint checks and repository harness checks.
5. Prepare ready PRs with accurate dependency and publication prerequisites.

## Validation and Acceptance

The original question must render exactly three buttons, submit the complete
question key and selected value, and survive a memory/session round trip.
ASCII and Chinese identifiers and existing display/value mappings must keep
their behavior. The editor must recognize and unhide a question key used in
the lesson. Tests must use the built renderer as well as the parser API.

## Idempotence and Recovery

No data migration is required. Keep package experiments outside versioned
dependency files until the corresponding versions are available. Generate all
lockfile changes with `npm install`; never hand-edit lockfiles. Library
worktrees are isolated under `/private/tmp/` and can be retained until the PRs
and integration are complete.

## Interfaces and Dependencies

The shared frontend helper exports name validation and expression matching,
plus `extractVariableNames(text: string): string[]`. The wire remains
`?[%{{key}} ...]` and `{[key]: values}`. Library release and application pins
must be coordinated; publishing a formal component-library release is a
separate, explicitly confirmed step under its repository policy.
