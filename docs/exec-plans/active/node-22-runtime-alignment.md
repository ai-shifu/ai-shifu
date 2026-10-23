---
title: Align Node 22 runtimes across MarkdownFlow consumers
status: active
owner_surface: cross-surface
last_reviewed: 2026-10-23
canonical: true
---

# Align Node 22 runtimes across MarkdownFlow consumers

## Purpose / Big Picture

Use Node 22.23.4, the latest official 22.x release verified on 2026-10-23,
for AI-Shifu and the MarkdownFlow ecosystem's Node build and maintenance paths.
Align direct Node type declarations with major version 22. Deliver changes
through independent pull requests; merging and deployment remain human actions.

## Progress

- [x] 2026-10-23 UTC: Verify the official release index and inspect current
  AI-Shifu runtime, Docker, CI, manifests, and MarkdownFlow repositories.
- [x] 2026-10-23 UTC: Preserve existing AI-Shifu Node 22.23.4 image/runtime pins
  and upgrade the remaining Node 20 dependency-bump workflow.
- [x] 2026-10-23 UTC: Regenerate direct Node 22 type dependencies and lockfiles
  with Node 22.23.4 and its bundled npm 10.9.9.
- [x] 2026-10-23 UTC: Pass all 3,260 AI-Shifu frontend tests, TypeScript,
  production build, repository harness, developer-tool check and all-file hooks.
- [x] 2026-10-23 UTC: Validate sibling libraries and both playground builds;
  reproduce legacy playground type/lint failures on its unchanged main baseline.
- [ ] 2026-10-23 UTC: Read back the independent pull requests and their remote
  validation results; no merge or deployment is part of this work.

## Surprises & Discoveries

AI-Shifu already pins Node 22.23.4 in its frontend engine, Dockerfiles and
primary CI jobs. Its MarkdownFlow UI dependency-bump workflow still used Node
20. Local sibling checkouts may lag remote main, so each library's current
remote default branch determines the actual changes.

## Decision Log

- Preserve the existing production Node image digest and CA trust fixes.
- Update build tooling without changing published library versions or consumer
  compatibility requirements solely because CI uses a newer runtime.
- Use isolated checkouts and the hash-verified official Node binary for
  validation; preserve existing developer checkouts and global Node settings.
- Leave historical execution records and disabled workflow backups unchanged.
- Preserve library consumer engine ranges; a development runtime update does
  not narrow the library's supported consumer versions.

## Outcomes & Retrospective

AI-Shifu's local production build, all 267 frontend test suites and repository
gates pass on Node 22.23.4. Sibling library checks and both playground builds
also pass. The legacy playground retains three pre-existing TypeScript errors
and an ESLint stack overflow, reproduced with its original Node 20 types on
unchanged main. Docker is unavailable locally, so no container build is claimed.
The independent pull requests record each repository's complete evidence.

## Context and Orientation

AI-Shifu's current runtime is declared in `src/web/package.json`; production
and development Dockerfiles already match it. The remaining workflow is
`.github/workflows/bump-markdown-flow-ui.yml`. Relevant sibling repositories
are `markdown-flow-ui`, `markdown-flow-agent-ui`, `markdown-flow-agent-py`, `remark-flow`,
`markdown-flow-playground`, and `markdown-flow-agent-playground`. Pure Python
or documentation repositories without Node build paths need no runtime edit.

## Plan of Work

Inspect live default branches, update outdated runtime pins and direct Node
types, regenerate lockfiles through npm, then run each repository's appropriate
checks under Node 22.23.4. Keep each repository's change focused on this upgrade.

## Concrete Steps

Use the official Node 22.23.4 archive after checking its SHA-256 against the
official release sums. Generate lockfiles with `npm install --package-lock-only
--ignore-scripts`. Validate AI-Shifu with frontend checks, the repository
harness, the developer-tool doctor and all-file lefthook gates. Validate library
builds and tests using their existing scripts and current repository rules.

## Validation and Acceptance

Active Node build paths must select 22.23.4. Dependency-bump operations must
generate lockfiles with the same Node/npm as application builds. Direct Node
type declarations must use major version 22 with matching npm-generated locks.
Record any existing failures separately from upgrade regressions. Read back
each pull request and CI result before claiming remote validation succeeded.

## Idempotence and Recovery

Dependency installation is repeatable from committed manifests and lockfiles.
Revert the focused runtime/type updates to restore prior configuration. No
running environment, release tag or production deployment is changed here.

## Interfaces and Dependencies

No application API, event, environment variable, or library export changes.
The selected toolchain is Node 22.23.4 with bundled npm 10.9.9. Library test
frameworks and deployment base-image consumers retain their existing ownership.
