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
- [x] 2026-08-20 22:36 CST: Opened ready UP046 PR
  [#2577](https://github.com/ai-shifu/ai-shifu/pull/2577) from
  `sunner/ruff-up046` to the UP047 branch. The last target-gated PEP 695 ignore
  was removed; the Python 3.11 check is clean, both Python 3.12 migration sites
  are audited, 674 focused billing/history tests pass with 10 skips, and all
  repository pre-commit hooks passed.
- [ ] Merge or retarget UP046 PR #2577 after its predecessors without combining
  it with the next rule unit.
- [x] 2026-08-20 23:16 CST: Opened ready PLW0603 PR
  [#2579](https://github.com/ai-shifu/ai-shifu/pull/2579) from
  `sunner/ruff-plw0603` to the UP046 branch. All 25 findings across 13
  state-writing sites were replaced with stable extensions, typed state
  owners, or explicit accessors; no PLW0603 suppression remains. The full
  backend suite passes 3,008 tests with 17 skips, and all repository
  pre-commit hooks pass.
- [ ] Merge or retarget PLW0603 PR #2579 after its predecessors without
  combining it with the next rule unit.
- [x] 2026-08-20 23:42 CST: Opened ready G004 PR
  [#2580](https://github.com/ai-shifu/ai-shifu/pull/2580) from
  `sunner/ruff-g004` to the PLW0603 branch. All 195 findings across 44 backend
  files now use parameterized logging, with no G004 suppression. An AST audit
  proved that the conversion made no other production-code changes; 25 focused
  tests and the full backend suite pass 3,009 tests with 17 skips, and all
  repository pre-commit hooks pass.
- [x] 2026-08-20 23:42 CST: Re-ran the stable `ALL` census on the G004 tip. It
  reports 31,058 findings and no G004 findings.
- [ ] Merge or retarget G004 PR #2580 after its predecessors without combining
  it with the next rule unit.
- [x] 2026-08-21 00:20 CST: Opened ready D205 PR
  [#2581](https://github.com/ai-shifu/ai-shifu/pull/2581) from
  `sunner/ruff-d205` to the G004 branch. All 262 findings across 66 tracked
  Python files now have separated summaries; a semantic audit found no
  non-docstring AST changes and proved all 112 touched Swagger YAML bodies are
  unchanged. The repository-wide Swagger regression test, full backend suite,
  and all pre-commit hooks pass.
- [x] 2026-08-21 00:20 CST: Re-ran the stable `ALL` census on the D205 tip. It
  reports 30,901 findings across 40 rules and no D205 findings.
- [ ] Merge or retarget D205 PR #2581 after its predecessors without combining
  it with the next rule unit.
- [x] 2026-08-21 00:45 CST: Opened ready D107 PR
  [#2582](https://github.com/ai-shifu/ai-shifu/pull/2582) from
  `sunner/ruff-d107` to the D205 branch. All 123 findings across 57 Python
  files now document the state, payload, dependency, or setup established by
  each constructor. A semantic AST audit found no behavior change after
  normalizing docstrings and one no-op `pass`; 166 focused tests, the full
  backend suite, and all pre-commit hooks pass.
- [x] 2026-08-21 00:45 CST: Re-ran the stable `ALL` census on the D107 tip. It
  reports 30,778 findings across 39 rules and no D107 findings.
- [ ] Merge or retarget D107 PR #2582 after its predecessors without combining
  it with the next rule unit.
- [x] 2026-08-21 01:09 CST: Opened ready D105 PR
  [#2583](https://github.com/ai-shifu/ai-shifu/pull/2583) from
  `sunner/ruff-d105` to the D107 branch. All 155 findings across 37 Python
  files now document each magic method's observable protocol. A semantic AST
  audit found no executable change after removing docstrings; 224 focused
  tests, the full backend suite, and all pre-commit hooks pass.
- [x] 2026-08-21 01:09 CST: Re-ran the stable `ALL` census on the D105 tip. It
  reports 30,623 findings across 38 rules and no D105 findings. E501 remains at
  613 findings, so the documentation cleanup transfers no line-length debt.
- [ ] Merge or retarget D105 PR #2583 after its predecessors without combining
  it with the next rule unit.
- [x] 2026-08-21 01:40 CST: Opened ready TC003 PR
  [#2584](https://github.com/ai-shifu/ai-shifu/pull/2584) from
  `sunner/ruff-tc003` to the D105 branch. Of 100 findings across 86 files, 95
  genuinely annotation-only imports in 81 files moved behind `TYPE_CHECKING`;
  five Pydantic DTO modules retain runtime `datetime` imports through a shared
  Ruff runtime-evaluation contract. The import AST audit, 261 focused tests,
  full backend suite, script entry points, and all pre-commit hooks pass.
- [x] 2026-08-21 01:40 CST: Re-ran the stable `ALL` census on the TC003 tip. It
  reports 30,518 findings across 37 rules and no TC003 findings. The Pydantic
  runtime model also removes four TC002 false positives while TC002 remains a
  separate global exception; deleting one unused fake clock removes one
  ANN001 finding, and every other rule count is unchanged.
- [ ] Merge or retarget TC003 PR #2584 after its predecessors without combining
  it with the next rule unit.
- [x] 2026-08-21 02:00 CST: Prepared the TC002 stage on
  `sunner/ruff-tc002`, stacked on TC003. All 134 annotation-only third-party
  imports across 113 files moved behind `TYPE_CHECKING`. An import AST audit
  matched every removed runtime import to its type-only replacement and found
  no other executable changes; 908 focused tests and the full backend suite
  pass.
- [x] 2026-08-21 02:00 CST: Re-ran the stable `ALL` census on the TC002 tip. It
  reports 30,384 findings across 36 rules and no TC002 or TC003 findings. The
  134-finding reduction is exact; ANN001, E501, and PLR0911 remain unchanged.
- [x] 2026-08-21 02:06 CST: Opened ready TC002 PR
  [#2585](https://github.com/ai-shifu/ai-shifu/pull/2585) from
  `sunner/ruff-tc002` to the TC003 branch after all repository pre-commit hooks
  passed.
- [ ] Merge or retarget TC002 PR #2585 after its predecessors without combining
  it with the next rule unit.
- [x] 2026-08-21 02:34 CST: Prepared the D100 stage on `sunner/ruff-d100`,
  stacked on TC002. Added ownership- or behavior-focused module docstrings to
  414 Python files and removed one unreferenced zero-byte test placeholder. A
  semantic AST audit found no executable changes; entry-point tests, script
  help commands, architecture fixtures, and the full backend suite pass.
- [x] 2026-08-21 02:34 CST: Re-ran the stable `ALL` census on the D100 tip. It
  reports 29,968 findings across 35 rules and no D100 findings. D100 falls by
  all 415 findings; deleting the empty module also removes one CPY001 finding,
  while ANN001, D101-D103, E501, and PLR0911 remain unchanged.
- [ ] Open the ready D100 PR against the TC002 branch after the repository gates
  pass, then merge or retarget it after its predecessors without combining it
  with the next rule unit.
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
- PLW0603's full-suite verification exposed a pre-existing test class that
  permanently replaced `dao.init_redis` during collection. Fixture-scoped
  injection now owns that test double, so collecting an unrelated test can no
  longer alter the production DAO module for the rest of the process.
- G004's full-suite verification exposed a config fallback test that treated a
  mocked logger's first positional argument as the final rendered message. The
  test now verifies the constant message template and interpolation argument,
  so it protects the parameterized logging contract instead of requiring eager
  formatting.
- Correcting D205 structure made pydocstyle recognize sections that malformed
  summaries had hidden. This exposed D200, D410, D411, D413, and D417 findings
  from rules already selected by the repository; satisfying them in the D205
  stage preserves the existing lint baseline rather than adopting another rule
  unit.
- The repository has 114 source-defined Swagger docstrings. Three existing
  learner-route specifications contain invalid YAML; the new parser test
  freezes their exact identities without changing them in this rule PR, while
  rejecting any additional unparseable specification.
- D203 and D213 are necessary explicit conflict exceptions rather than clean
  rules. Selected alone, they report 293 and 656 findings respectively;
  selected with D211 or D212, Ruff emits an incompatibility warning and ignores
  D203 or D213. Removing the explicit ignores would shrink the file only by
  making every normal run noisy and relying on implicit conflict resolution.
- Adding the final D107 docstring to the no-op Langfuse client made its old
  `pass` statement redundant under the already-selected PIE790 rule. Removing
  that no-op preserves the configured baseline and runtime behavior; it does
  not adopt a second rule unit.
- The first D105 pass introduced four E501 findings through long protocol
  summaries. Shortening those summaries without weakening their observable
  contracts restored E501 to 613, making the final census a pure 155-finding
  reduction instead of moving debt between rules.
- TC003's unsafe fixer correctly identified annotation-only imports but could
  not see four obsolete tests monkeypatching module-level `datetime` names that
  production never read. The focused suites exposed the fake seams; removing
  those patches while retaining their real `now_utc` injection made the tests
  describe the actual clock contract.
- TC002's unsafe fixer moved all 134 findings without exposing a hidden runtime
  dependency. Two modules without postponed annotations used quoted or local
  annotations, while SQLAlchemy model classes used for executable query
  construction stayed available at runtime. The exact import-movement audit
  makes that boundary explicit.
- RUF001 is not the next safe exception-removal stage: its 162 findings are
  deliberate full-width Chinese punctuation in customer messages, TTS boundary
  patterns, and tests that freeze those language semantics. Replacing them with
  ASCII punctuation would change product and speech behavior merely to shorten
  configuration.
- D100 included one zero-byte, unreferenced `test_rag.py` placeholder. Removing
  it was more honest than inventing a module purpose and also removed one
  CPY001 finding; every documented module otherwise differs from its parent
  only by the first docstring statement.
- The next numerically smaller candidate, PLR0911, spans 72 complex control-flow
  functions across authentication, billing, payment, permissions, and Alembic
  infrastructure. It is not a safe mechanical unit: adopting it requires
  behavior-specific decomposition rather than result-variable or threshold
  workarounds, so TC003 was the smaller reviewable exception-removal stage.
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
- 2026-08-21: A shared Ruff semantic setting required by one rule may also
  remove false positives from another still-ignored rule. Record that census
  effect explicitly, but do not treat the second rule as adopted until its own
  independent rule PR removes its exception and passes its acceptance suite.

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

The UP046 stage removes the final preemptive PEP 695 exception without adding
Python 3.12-only syntax. UP046 is clean under the configured Python 3.11 target;
an explicit Python 3.12 audit records the `PageWindow` and `HistoryItem` class
migrations. The billing suite passes 673 tests with 10 skips, the focused shifu
history test passes, and the full repository gates pass.

The PLW0603 stage removes the global ignore and every Python `global` statement
without adding inline or per-file exceptions. Stable Flask extensions keep
imported identities intact; replaceable process state now has explicit owners
for app, config, Redis, plugins, Celery, Langfuse, analytics, Ping++, and TTS;
verification codes read the current app instead of cross-app caches. Focused
lifecycle suites and the full backend suite pass 3,008 tests with 17 skips, and
the repository-wide pre-commit gate passes.

The G004 stage removes the global f-string logging ignore and converts all 195
findings across 44 backend files to positional logging interpolation. Message
text, argument order, conversions, levels, literal percent signs, and the one
`.1f` format are preserved; an AST equivalence audit found no other production
code changes. Exact config-warning and migration-progress log tests pass in the
25-test focused set, the full backend suite passes 3,009 tests with 17 skips,
and the repository-wide pre-commit gate passes. The engineering baseline now
tells future agents to parameterize logging rather than hiding eager f-strings.

The D205 stage removes the global missing-blank-line exception and gives all
262 affected docstrings a complete first-line summary. A semantic AST audit
confirms that the 66 tracked Python files contain no code changes outside
docstrings and that all 112 touched Flasgger YAML bodies are identical. The new
repository-wide parser regression test discovers all 114 Swagger docstrings,
requires the D205 boundary, parses every valid specification, and freezes the
three pre-existing invalid specifications. The focused suite passes 11 tests,
the full backend suite passes 3,010 tests with 17 skips, and the repository-wide
pre-commit gate passes. Future agents now have an explicit D205 and Flasgger
repair contract in the engineering baseline.

The D107 stage removes the global missing-constructor-docstring exception and
adds responsibility-focused documentation to all 123 affected constructors in
57 files. No runtime path reads `__init__.__doc__`; a semantic AST audit proves
the sources are otherwise identical after constructor docstrings and the one
redundant no-op `pass` are normalized. The focused constructor and test-double
suites pass 166 tests with one skip, the full backend suite passes 3,010 tests
with 17 skips, and the repository-wide pre-commit gate passes. The engineering
baseline tells future agents to document the payload, state, dependency, setup,
or real side effects instead of copying a signature or adding generic filler.

The D105 stage removes the global missing-magic-method-docstring exception and
documents all 155 affected methods in 37 files. The 106 `__json__` methods state
whether they expose a scalar, JSON-compatible data, or a serialized string;
mapping, representation, comparison, iteration, and delegation methods name
their visible protocol result. No runtime path consumes these docstrings, and a
semantic AST audit proves the Python sources are otherwise identical after
docstrings are removed. The focused protocol suites pass 224 tests, the full
backend suite passes 3,010 tests with 17 skips, and the repository-wide
pre-commit gate passes. Future agents now have an explicit D105 repair contract
that rejects filler summaries in favor of observable behavior.

The TC003 stage removes the global standard-library type-only import exception.
Ninety-five imports across 81 Python files now load only under `TYPE_CHECKING`;
an AST normalization audit proves those modules have no other executable syntax
changes. Five Pydantic DTO modules keep `datetime` available while their model
classes resolve field annotations, modeled once through Ruff's runtime-
evaluated base-class setting and protected by five parameterized assertions.
Focused testing also removed four ineffective `datetime` monkeypatch calls
while preserving the real `now_utc` clock injection. The cross-service suite
passes 261 tests, the full backend suite passes 3,015 tests with 17 skips, both
diagnostic script entry points import, and the repository-wide pre-commit gate
passes. Future agents now distinguish postponed and local annotations from
Pydantic fields, runtime reflection, and genuine module-attribute test seams.

The TC002 stage removes the global third-party type-only import exception. All
134 findings across 113 Python files are annotation-only uses and now load
under `TYPE_CHECKING`; runtime SQLAlchemy models remain in normal imports, and
Pydantic field types remain protected by the shared runtime-evaluated base-
class setting. An AST audit proves a one-for-one movement of import aliases and
no other executable changes. The focused cross-service suite passes 908 tests,
the full backend suite passes 3,015 tests with 17 skips, and the stable `ALL`
census falls exactly 134 findings to 30,384 across 36 rules. Future agents now
apply the same runtime-resolution test to both third-party and standard-library
annotation imports instead of treating import provenance as the safety proof.

The D100 stage removes the global undocumented-module exception. Four hundred
fourteen production, script, fixture, and test modules now state the service
responsibility, operation, or behavior group they own; one empty and
unreferenced test placeholder is removed instead of receiving filler text. A
semantic AST audit proves that stripping the new first-statement docstrings
restores every module exactly, and repository search found no runtime consumer
of module `__doc__`. Entry-point tests pass 10 cases with one infrastructure
skip, both changed maintenance scripts expose their help successfully, the
full backend suite passes 3,015 tests with 17 skips, and the stable `ALL` census
falls to 29,968 findings across 35 rules. Future agents now document module
ownership rather than restating filenames or inventing generic helper prose.

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
