# Minimize the Explicit Ruff Policy

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

- [x] 2026-08-20 21:13 CST: Fast-forwarded a clean detached worktree to
  `origin/main` at `8bced2e70` and confirmed Ruff 0.16.3 is installed.
- [x] 2026-08-20 21:13 CST: Confirmed the configured baseline passes
  `ruff check .` and all 799 Python files pass `ruff format --check .`; the
  formatter reported this total directly for `.py`, `.pyi`, and `.ipynb`
  inputs at `8bced2e70`.
- [x] 2026-08-20 21:13 CST: Measured the stable `ALL`-rule gap and recorded the
  pull-request, testing, and exception policy in repository guidance.
- [x] 2026-08-20 21:25 CST: Generated the Cursor/Copilot mirrors and knowledge
  indexes; repository harness, Ruff, format, architecture, translation, JSON,
  YAML, frontend lint/format, and all other pre-commit hooks passed.
- [x] 2026-08-20 21:56 CST: Opened ready foundation PR
  [#2571](https://github.com/ai-shifu/ai-shifu/pull/2571) from
  `sunner/ruff-rule-minimization-foundation` to `main`.
- [x] 2026-08-20 22:04 CST: Opened ready D406 PR
  [#2572](https://github.com/ai-shifu/ai-shifu/pull/2572) from
  `sunner/ruff-d406` to the foundation branch. The global exception became one
  explained inline suppression, and the focused Flasgger schema test plus all
  repository pre-commit hooks passed.
- [ ] Merge foundation PR #2571, then merge or retarget D406 PR #2572 without
  combining its rule unit with its successor.
- [x] 2026-08-20 22:10 CST: Opened ready D407 PR
  [#2573](https://github.com/ai-shifu/ai-shifu/pull/2573) from
  `sunner/ruff-d407` to the D406 branch. Its one finding became the second code
  on the same explained inline suppression; the inherited Flasgger schema test
  and all repository pre-commit hooks passed.
- [ ] Merge or retarget D407 PR #2573 after its predecessors without combining
  it with the D405 rule unit.
- [x] 2026-08-20 22:16 CST: Opened ready D405 PR
  [#2574](https://github.com/ai-shifu/ai-shifu/pull/2574) from
  `sunner/ruff-d405` to the D407 branch. One ordinary finding was fixed; the
  Swagger finding became an inline suppression and one applied migration got
  an exact-file exception. The focused profile and Swagger tests plus all
  repository pre-commit hooks passed.
- [x] 2026-08-20 22:16 CST: Re-ran the stable `ALL` census on the D405 tip. It
  reports 31,224 findings and no remaining D405/D406/D407 findings outside the
  documented narrow exceptions.
- [ ] Merge or retarget D405 PR #2574 after its predecessors without combining
  it with the next rule unit.
- [x] 2026-08-20 22:22 CST: Opened ready UP040 PR
  [#2575](https://github.com/ai-shifu/ai-shifu/pull/2575) from
  `sunner/ruff-up040` to the D405 branch. The redundant ignore was removed;
  UP040 has zero findings under the configured Python 3.11 target and remains
  target-gated until the repository's minimum runtime reaches Python 3.12.
- [x] Merge or retarget UP040 PR #2575 after its predecessors without combining
  it with the next rule unit.
- [x] 2026-08-20 22:28 CST: Opened ready UP047 PR
  [#2576](https://github.com/ai-shifu/ai-shifu/pull/2576) from
  `sunner/ruff-up047` to the UP040 branch. The target-gated ignore was removed;
  the Python 3.11 check is clean, the one Python 3.12 migration site is audited,
  the 48-test learner-profile suite passes, and all repository pre-commit hooks
  passed.
- [ ] Merge or retarget UP047 PR #2576 after its predecessors without combining
  it with the next rule unit.
- [ ] Remove the target-gated UP046 global ignore. It has zero findings under
  the configured Python 3.11 target and two explicit Python 3.12 findings that
  should surface in the future runtime-upgrade PR instead of staying hidden.
- [ ] Re-run the census after each merged rule unit and choose the next smallest
  behaviorally safe unit.
- [ ] Collapse the explicit selection to `select = ["ALL"]` once every stable
  rule is either clean or represented by a necessary, documented exception.
- [ ] Move this plan to `docs/exec-plans/completed/` after the final stacked PR
  is merged and the full acceptance suite passes.

## Surprises & Discoveries

- Ruff's built-in default does not mean "all rules." Removing `[lint].select`
  today would discard most of the checks the repository deliberately adopted.
  Configuration size must not be reduced by silently reducing enforcement.
- `main` already contains a long sequence of one-rule pull requests through
  PR #2569. The current file selects broad prefixes when they are clean and
  spells out individual codes only when a broader prefix would expose debt.
- Running `ruff check . --select ALL --statistics` against the current tree
  reports 31,224 findings. Command-line selection supersedes global ignores,
  while configured per-file exceptions still apply. Running the same census
  with `--isolated` reports 42,444 findings because test, script, migration,
  and fixture exceptions are removed too.
- The largest stable-rule debts are COM812 (6,113), ANN001 (4,651), D103
  (2,836), ANN201 (2,277), DTZ001 (1,584), ANN202 (1,501), PLC0415 (1,234),
  PLR2004 (1,182), and SLF001 (830). These are not appropriate first stack
  items because they mix broad contract decisions with mechanical churn.
- D406 and D407 each have one finding: the `parameters:` key inside the
  `/api/user/send_sms_code` Flasgger YAML docstring. Rewriting it as a NumPy
  docstring section would corrupt the API specification, so the correct end
  state is global enforcement plus a narrow, explained suppression.
- FIX002 and TD003 report the same two TODOs. One is a real password-login
  rate-limit feature and one is a compatibility-removal checkpoint. Renaming
  them to evade lint would hide work, and implementing either is larger than a
  lint cleanup, so they are deliberately not the first rule unit.

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

## Outcomes & Retrospective

The foundation stage changes no runtime code and does not change Ruff's active
rule set. It establishes the continuation contract, baseline evidence, stacked
PR model, and AI-facing decision process. Record cumulative rule counts,
exception reductions, test results, and any revised prioritization here as the
stack progresses.

The D406 stage removes one global ignore and leaves one coded inline exception
on the Flasgger YAML docstring. `ruff check . --select D406` reports no
unsuppressed findings. The focused captcha-route suite passes 10 tests after
parsing the registered view's docstring and asserting its required request-body
schema; the repository Ruff, format, harness, developer-tool, and full
pre-commit gates also pass.

The D407 stage removes one more global ignore and adds D407 to that same inline
exception because its automatic dashed underline would also invalidate the
Swagger YAML. `ruff check . --select D407` reports no unsuppressed findings,
the inherited 10-test schema suite passes on the D407 tip, and the same full
repository gates pass.

The D405 stage removes the last global Swagger-docstring ignore. Of its three
findings, the ordinary profile `NOTE:` heading is fixed, the Swagger YAML stays
covered by the schema regression test and an inline D405 code, and the applied
no-op migration remains untouched behind an exact-file D405 exception. The
profile suite passes 15 tests, the Swagger suite passes 10 tests, and the full
repository gates pass.

The UP040 stage removes a preemptive exception with no implementation changes.
UP040 remains selected through the `UP` prefix but is dormant under the
repository's Python 3.11 target. It must not be forced with a Python 3.12 target
in local hooks or CI because Ruff's suggested PEP 695 syntax does not parse on
the supported runtime. The rule will activate naturally when the repository's
minimum runtime moves to Python 3.12.

The UP047 stage removes another preemptive exception without introducing Python
3.12-only syntax. UP047 is clean under the configured Python 3.11 target; an
explicit Python 3.12 audit records the single generic-function migration in the
learner-profile retry helper. Its 48-test service suite and the full repository
gates pass.

## Context and Orientation

Start with these files:

- `ruff.toml` is the repository-wide Ruff configuration consumed by
  `lefthook.yml` and `.github/workflows/lint.yml`.
- `AGENTS.md` owns repository-wide coding-agent rules.
- `docs/engineering-baseline.md` owns the detailed Ruff finding and rule-
  adoption workflow.
- `scripts/generate_ai_collab_docs.py` owns generated Cursor and Copilot
  mirrors; run it whenever shared AI guidance changes.
- `scripts/check_repo_harness.py` verifies instruction and generated knowledge
  surfaces.
- `src/api/AGENTS.md` and the nearest service `AGENTS.md` files constrain
  backend changes. Read the nearest file before editing each Ruff finding.
- `lefthook.yml` and `.github/workflows/lint.yml` pin Ruff 0.16.3 and run both
  check and format gates.

The baseline command for currently enforced rules is:

    ruff check .
    ruff format --check .

The reproducible stable-rule debt census is:

    ruff check . --select ALL --statistics
    ruff check . --isolated --select ALL --target-version py311 --statistics

The first command preserves configured per-file exceptions but intentionally
forces globally ignored and unselected rules into the report. The second
removes all repository configuration and exposes whether an exception can be
narrowed further.

## Plan of Work

1. Land a policy-only foundation PR containing this plan and the shared
   AI-facing Ruff workflow. Do not modify `ruff.toml` in that PR.
2. Re-run the `ALL` census on the foundation head and record drift from `main`.
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

The initial rule stack after the foundation is D406, D407, then D405. These
three remove global pydocstyle exceptions while retaining the one Swagger YAML
contract and immutable migration boundary explicitly.

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

- Ruff is pinned at 0.16.3 in `lefthook.yml`,
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
- Generated Cursor and Copilot instruction files depend on
  `scripts/generate_ai_collab_docs.py`; do not edit generated mirrors by hand.
- Stacked PR bases are GitHub branch dependencies. Keep each base branch alive
  until its direct successor is retargeted after merge.
