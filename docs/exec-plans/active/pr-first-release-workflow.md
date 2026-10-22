# PR-first product release workflow

## Purpose / Big Picture

Replace the draft-before-merge release path with a version-update PR, a manual
human merge into main, an automatic exact-commit draft, and a separate manual
human Publish action. Keep main/latest publication and production CICD/Drone
unchanged. Implementation, verification, review fixes, updates to PR #3155 and
CI/review follow-up are authorized. A real release, remote tag operation, merge,
auto-merge, deployment or repository settings change is not.

## Progress

- [x] 2026-10-22 06:32 UTC: Read repository and subtree instructions, baseline,
  workflows, adjacent tests, and the frozen skills release reference.
- [x] 2026-10-22 07:14 UTC: Implemented PR-only preparation with behavioral TDD.
- [x] 2026-10-22 07:14 UTC: Implemented exact-main detection, merged PR
  provenance, immutable tags, readback and idempotent draft guards with TDD.
- [x] 2026-10-22 07:14 UTC: Preserved product/dependency notes at frozen sources
  and guarded/pinned published-release builds before image jobs.
- [x] 2026-10-22 07:14 UTC: Wired static CI tests, aligned docs and passed the
  focused suite, all top-level script regressions, Ruff and actionlint.
- [x] 2026-10-22 11:38 UTC: Independently reviewed PR #3155, fixed Commitizen
  source ranges, delayed draft credentials and Docker workflow trigger coverage.
- [x] 2026-10-22 11:38 UTC: Added real pinned-Commitizen and workflow regressions,
  fixed same-PR note omissions and exact-host HTTP fixtures; all 276 top-level
  script tests and 179 subtests passed, as did actionlint and architecture fixtures.
- [x] 2026-10-22 11:38 UTC: Passed the repository-wide lefthook gate with all
  tracked files; no unrelated formatting or source changes were introduced.
- [x] 2026-10-22 11:53 UTC: Addressed the remote review's missing AMD64 trigger
  for draft-workflow edits. Both workflow filters now cover every explicit
  packaging input; all 304 top-level script tests and 179 subtests passed.
- [ ] 2026-10-22 11:38 UTC: External acceptance: a human reviews and manually merges the PR, then
  separately verifies the actual release draft and publication. Those operations
  remain outside this task; current CI/review evidence is maintained on PR #3155.

## Surprises & Discoveries

- The frozen repository version is 3.0.0, independently of the existing remote
  v3.0.1 history. This change must not repair or operate that release.
- Before the parent handoff, upstream PR #3149 was merged separately. The local
  branch was refreshed to that main commit; the workflow diff stayed identical
  and all script regressions passed again. No existing release/tag was repaired.
- Preparation currently updates two npm packages and lock roots, the vendored
  engine version, and first-party pinned Compose images. It must preserve those
  actual surfaces, not introduce generic language/version discovery.
- Dependency notes support historical frontend lock paths, tag comparisons,
  registry publish-time fallback, author enrichment, sorting and truncation.
  That behavior must remain covered when extracted from the workflow.
- Commitizen 4.16.2 interprets positional ranges as versions, not arbitrary
  commit SHAs. Passing a SHA silently selected the subject-only fallback and
  lost breaking-change bodies; the regression now executes the real CLI.
- GitHub requires workflow-write authorization when delayed draft targets
  differ from the default branch's workflows. The repository token cannot have
  that permission; the draft-writing step needs the existing scoped PAT option.
- Selector inputs must also appear in the Docker workflow's PR path filters.
  Tests now read the real workflow and check every declared input is reachable.

## Decision Log

- Use small Python CLI helpers for local Git/version validation and GitHub REST
  calls; exercise Git with disposable real repositories and mock remote GitHub
writes explicitly. No release operation is used as a test.
- Treat GitHub User/Bot metadata as rejection evidence for known automation,
  never as proof of a physical human. Require an exact merged-to-main release PR,
  reject recorded auto-merge and bot mergers, and document the remaining manual
  gate and repository branch-rule responsibility without changing settings.
- Pass dispatch/event values through environment variables or JSON event files,
  never interpolate arbitrary inputs or release-note text into shell source or
  fixed GitHub output delimiters.
- Leave build-latest.yml and all production configuration unchanged. Pass an
  optional frozen source commit to the reusable image workflow only for release
  builds; preserve existing callers and image/registry defaults.
- Render Commitizen with `--start-rev` in a temporary local shared clone checked
  out at the frozen source, preserving that source's configuration and commit
  bodies without changing the caller's branch, refs or local edits. This is not
  a managed worktree and copies no local environment files.
- Expose the workflow-capable PAT only to draft writes. Keep read-only notes
  lookups on the repository token and retain all source/provenance/tag guards.

## Outcomes & Retrospective

Local implementation is complete. Eighteen successive RED/GREEN slices have
external task-scratch logs named `red-01-prepare.log` through
`red-18-initial-notes.log` and corresponding `green-*` logs. Final Python 3.11
verification after correcting the independent review's no-PR Commitizen
duplication and overlapping-entry findings: 24 release tests; all top-level script
pytest tests pass (243 tests and 166 subtests). The new regressions were observed
failing before the targeted corrections. Coverage now compares complete entries
with change category and scope rather than Markdown substrings. Focused Ruff
checks/formatting, the five affected
workflows under actionlint 1.7.12, and architecture fixture checks pass.

Product/dependency note coverage was retained: Commitizen plus fallback,
normalization and authors; README initial-release sections; frozen previous-tag
boundaries; locked MarkdownFlow comparisons, legacy frontend lock lookup,
registry-time fallback, sorting/deduplication and original detail/page limits.
The fallback additionally retains PRs omitted by Commitizen. Generic discovery
for absent Rust/PHP/TOML/root version-file surfaces and act-specific conveniences
were deliberately replaced by the actual product version-file allowlist, not
expanded into a cross-language framework. No tracked product version was bumped.

The authorized review follow-up passes all 304 top-level script tests and 179
subtests, including real Commitizen 4.16.2 tests for breaking-change bodies,
frozen configuration, tagged retries and distinct subjects sharing a PR.
Workflow tests cover delayed draft recovery and selector/trigger agreement;
HTTP writes remain mocked. Current remote CI/review evidence is tracked on
[PR #3155](https://github.com/ai-shifu/ai-shifu/pull/3155), independently of these
local results. Production release acceptance remains outside this task. Human
identity is a policy gate, not cryptographically attested by GitHub metadata;
known automation is rejected but unknown automation behind a User account cannot
be proven absent. A main push must end at the release PR's exact merge commit.
Historical workflows/releases are not rewritten. These limits are documented in
the canonical publication reference.

## Context and Orientation

The old `.github/workflows/prepare-release.yml` creates a draft before opening a
version PR. `.github/workflows/build-on-release.yml` currently trusts the release
tag and only warns about malformed versions. The reusable native image workflow
is `.github/workflows/build-docker-image.yml`. Durable publication contracts live
in `docs/references/docker-image-publication.md` and the engineering baseline.
`scripts/check_repo_harness.py` has a narrow historical frontend-path exception
for the existing dependency-note code; move that ownership with the code.

## Plan of Work

Use successive RED/GREEN vertical slices: PR-only preparation and version files;
main event detection and no-op/error cases; merged PR provenance; exact tag and
draft creation/readback/reruns; published-release validation and source pinning;
notes extraction and frozen boundaries; workflow/static CI and adjacent guards.
Update this living plan with execution evidence and remaining limits. Logs stay
outside Git in the task scratch directory.

## Concrete Steps

From the repository root, add one behavioral test, run it with the stdlib unittest
runner or pinned pytest, capture the intended failure, implement the smallest
slice, and rerun it and accumulated focused tests. Use the task tools virtualenv
when available. Use `python scripts/build_repo_knowledge_index.py` and
`python scripts/check_repo_harness.py` after documentation changes, and execute
focused release tests plus Docker selector/metadata regressions, Ruff and YAML /
actionlint checks when available. The parent owns the verified feature-branch
commit and PR handoff. Do not merge, enable auto-merge, dispatch release Actions
or use production tools.

## Validation and Acceptance

Preparation creates neither a Release nor a formal tag and explicitly hands off
manual merge. Only an increasing version on a valid main push can prepare a draft
at the exact event commit with merged PR provenance and consistent versions /
pinned Compose images. No-change and missing initial baseline skip; invalid or
decreasing versions fail closed. Conflicting tags, published releases or target
mismatches fail before writes. Same-source draft reruns are safe and never publish.
Published-release validation rejects mismatched source/version/tag/provenance
before builds and freezes the source used by image jobs. Product and MarkdownFlow
notes retain coverage and use the previous reachable version tag, excluding the
candidate tag and later main commits. Tests must execute real Git and public CLI
or actual workflow scripts, label GitHub API mocks, and run in static CI.

## Idempotence and Recovery

Never force or move a formal tag. Reread exact remote targets after writes. An
existing same-source tag and matching draft may be reused; mismatches or an
already public release require manual investigation, not overwrite. A tag left
by an interrupted draft attempt is recoverable by the same event/source rerun.
GitHub operations cannot be atomic across refs and releases; fail closed and
report partial state rather than attempting automatic repair or publication.

## Interfaces and Dependencies

Use Python 3.11 stdlib for the core guard CLI, JSON event files, Git full commit
SHAs, and GitHub REST with explicit JSON requests over HTTPS. Keep remote
read/write mocking isolated in tests. Use the existing PAT-or-GITHUB_TOKEN for
preparation PR creation (PAT allows the existing bot PR CI behavior) and draft
writes. Delayed drafts may need workflow-write authorization in addition to
contents write and PR read; the canonical publication reference documents the
PAT requirements and repository-token fallback limits. Publication continues via
the existing release.published workflow and inherited registry secrets.
