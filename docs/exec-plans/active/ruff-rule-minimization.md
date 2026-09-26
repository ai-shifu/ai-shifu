# Ruff rule minimization

## Purpose / Big Picture

Make the repository's Ruff policy broad in enforcement and small in
configuration. The end state should express the accepted stable Ruff rule set
with the fewest possible `select`, `ignore`, and `per-file-ignores` entries,
without deleting checks merely to make the file shorter. Code should satisfy a
rule whenever the rule improves or safely constrains the project; exceptions
should be narrow, documented, and intrinsic to the affected surface.

The work lands as stacked pull requests. One pull request owns one Ruff rule
unit: normally one rule code, or an inseparable pair that reports the same
construct and requires the same change. Each rule pull request contains only
the implementation changes, regression coverage, Ruff policy change, and this
plan's progress update for that rule.

## Progress

- [x] 2026-09-26: Reconciled merged rule units against the main baseline; the dated journal preserves per-rule commits and regression evidence.
- [ ] Re-run the census after each merged rule unit and choose the next smallest
  behaviorally safe unit.
- [ ] Collapse the explicit selection to `select = ["ALL"]` once every stable
  rule is either clean or represented by a necessary, documented exception.
- [ ] Move this plan to `docs/exec-plans/completed/` after the final stacked PR
  is merged and the full acceptance suite passes.

## Surprises & Discoveries

The target is broad useful enforcement with narrow justified exceptions. Flasgger docstrings are executable YAML, applied migrations are immutable, and the supported Python 3.11 target excludes PEP 695 rewrites. A shared semantic setting can change another rule census without adopting that rule. Old counts in the journal must not choose the next unit.

## Decision Log

- 2026-08-20: Interpret "minimal Ruff rules" as minimal explicit policy while
  preserving the broadest useful enforcement. The target is `select = ["ALL"]`
  with necessary exceptions, not an unconfigured Ruff invocation that checks
  only Ruff's smaller built-in default set.
- 2026-08-20: Use a policy-only foundation PR based on `main`. Every rule PR is
  based on the preceding rule branch and names that predecessor in its body.
  As a predecessor merges, retarget or rebase the next PR without combining
  its rule unit with another.
- 2026-08-20: A rule unit defaults to one Ruff code. Multiple codes may share a
  PR only when they flag exactly the same construct, have the same fix and
  exception boundary, and separating them would create a configuration-only
  intermediate state with no independently meaningful behavior.
- 2026-08-20: Lint passing is not behavior coverage. Any semantic rewrite must
  add or identify a focused regression test that fails for the risky behavior.
  Purely structural or suppression-narrowing changes still need the closest
  contract test plus the repository Ruff, format, and harness gates.
- 2026-08-20: Use inline `# noqa: CODE` only for one intentional construct and
  accompany it with a plain-English reason. Use `per-file-ignores` only when a
  file or file class exists specifically to exercise a conflicting pattern or
  is immutable history. A global ignore is the last resort for a repository-
  wide contract that fundamentally conflicts with a rule.
- 2026-08-20: Do not edit applied Alembic migrations to satisfy style rules.
- 2026-08-21: A shared Ruff semantic setting required by one rule may also
  remove false positives from another still-ignored rule. Record that census
  effect explicitly, but do not treat the second rule as adopted until its own
  independent rule PR removes its exception and passes its acceptance suite.

## Outcomes & Retrospective

Foundation and the recorded rule units are merged. The final fresh census, remaining rule work and ALL-policy acceptance are still open; this cleanup changes no lint configuration or runtime code. Completed delivery evidence is in `docs/history/ruff-rule-minimization-through-2026-09-26.md`.

## Context and Orientation

Read the current `ruff.toml`, root `AGENTS.md` and `docs/engineering-baseline.md`. The dated journal retains earlier rule counts and outcomes. Use a new census from the current branch/base for continuation; do not reuse an old findings count as current state.

## Plan of Work

1. Read the delivered foundation and merged-unit journal; start from the current configuration.
2. Re-run the `ALL` census on the current head and record drift from `main`.
3. Choose the smallest rule unit whose correct fix is clear. Prefer removing a
   global ignore, then enabling a currently unselected rule with few findings,
   before undertaking high-count architectural rules.
4. Inspect every finding, its nearest `AGENTS.md`, owning code, call sites, and
   tests. Classify each finding as code defect, safe modernization, intentional
   protocol/framework shape, fixture, or immutable history.
5. Add or strengthen focused tests before the risky implementation rewrite.
   Confirm the test protects behavior rather than merely restating source text.
6. Apply the narrowest implementation fix. Use suppressions only according to
   the hierarchy in the Decision Log.
7. Change `ruff.toml` for exactly that rule unit, run the rule-specific command,
   then the configured Ruff and format baselines, targeted tests, and the
   relevant wider gates.
8. Update this plan and create a ready PR whose base is the previous stack
   branch. Keep the PR title, body, base branch, and verification readback
   accurate after every push.
9. Repeat until all stable rules are clean or necessarily excepted, then replace
   the explicit selection list with `select = ["ALL"]` in its own final policy
   PR and run the full repository gate.

## Concrete Steps

For each rule unit `CODE`:

1. Create `sunner/ruff-<code-lowercase>` from the current stack tip.
2. Run `ruff rule CODE` and `ruff check . --select CODE`.
3. List every finding and map it to owning tests before editing.
4. Add or identify the behavior/contract regression tests.
5. Make the implementation and exception changes with no unrelated cleanup.
6. Run:

       ruff check . --select CODE
       ruff check .
       ruff format --check .
       python scripts/check_repo_harness.py

7. Run targeted tests for every touched runtime surface. Run the full backend
   suite for shared helpers, cross-service changes, or broad mechanical edits.
8. Run `python scripts/check_dev_tools.py`, then
   `lefthook run pre-commit --all-files` before committing.
9. Inspect staged and unstaged diffs, commit with the exact `Changed:` and
   `Benefit:` body required by `AGENTS.md`, push, and create a ready PR based on
   the preceding stack branch.
10. Record the PR URL, base/head, findings removed, remaining exceptions, and
    test results in this plan.

The initial D406/D407/D405 sequence is already delivered; see the journal. Choose the next unit only after the fresh census.

## Validation and Acceptance

Every rule PR must satisfy all of the following:

- Its diff against the immediate stack base contains one rule unit only.
- `ruff check . --select CODE` passes, accounting only for documented narrow
  exceptions that the PR deliberately retains.
- `ruff check .` and `ruff format --check .` pass repository-wide.
- Focused tests cover the behavior or contract at risk; lint output alone does
  not count as test coverage.
- `python scripts/check_repo_harness.py` passes whenever instructions, plans,
  scripts, or generated knowledge files change.
- `python scripts/check_dev_tools.py` confirms the local gate exists, and
  `lefthook run pre-commit --all-files` passes before commit.
- The ready PR clearly names its predecessor, rule code, behavior changes,
  exceptions, targeted tests, and broader verification.
- GitHub CI is green or any baseline/external failure is reproduced and
  documented without weakening Ruff policy.

The overall goal is accepted when:

- all stable Ruff rules are enforced through `select = ["ALL"]` except for a
  minimal, documented set of intrinsic conflicts;
- global ignores have no single-call-site or single-file exceptions;
- per-file and inline suppressions are narrow, coded, and justified;
- the full backend and repository harness suites pass on the final stack tip;
- repository AI guidance tells future agents how to resolve findings without
  weakening the policy; and
- every rule unit remains independently reviewable in the GitHub stack.

## Idempotence and Recovery

Census commands and checks that explicitly use check-only modes are read-only
and safe to rerun. Tests can change external state, and
`lefthook run pre-commit --all-files` runs formatters and fixers that can rewrite
the worktree; safeguard unrelated changes and review the resulting diff before
running either. Ruff fixes must not be run repository-wide without first
limiting the rule and reviewing the proposed diff. If a formatter or hook
rewrites unrelated files, restore only that generated churn and preserve
user-owned changes.

Each stack branch is independently recoverable. If a rule PR is rejected,
retarget its successor to the last accepted predecessor and rebase or cherry-
pick only the successor's own rule commit. Never squash distinct rule units
together. If `main` advances, fetch it and update only the foundation or the
earliest unmerged branch first, then replay successors in order.

## Interfaces and Dependencies

- Ruff is pinned at 0.16.5 in `lefthook.yml`,
  `.github/workflows/lint.yml`, `docs/engineering-baseline.md`, and
  `scripts/check_dev_tools.py`, with the contributor install command mirrored
  in `INSTALL_MANUAL.md`. The doctor verifies the binary on `PATH`, so a Ruff
  upgrade must update all five locations together. Upgrade work is
  separate because changing the rule inventory while shrinking policy would
  make the census non-reproducible.
- `ruff.toml` is a shared contract for local hooks and CI. A rule is not adopted
  until both paths use the same checked-in configuration.
- Flasgger consumes route docstrings as YAML after the `---` marker; pydocstyle
  fixes must not rewrite YAML keys as prose sections.
- Applied Alembic revisions are immutable even when a style rule flags them.
- Keep the Copilot entry point limited to navigation rather than duplicating
  shared rules.
- Stacked PR bases are GitHub branch dependencies. Keep each base branch alive
  until its direct successor is retargeted after merge.
