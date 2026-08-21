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
- [x] 2026-08-21 02:47 CST: Opened ready D100 PR #2586 against the TC002
  branch after all local gates passed.
- [ ] Merge or retarget D100 PR #2586 after its predecessors without combining
  it with the next rule unit.
- [x] 2026-08-21 03:21 CST: Prepared the FIX002 stage on
  `sunner/ruff-fix002`, stacked on D100. Implemented password-login failure
  throttling by privacy-preserving identifier and client-IP counters, and
  removed the expired interaction-key remap after verifying both learner
  clients submit the canonical key and the pinned MarkdownFlow release has
  passed the documented rollout checkpoint.
- [x] 2026-08-21 03:21 CST: Re-ran the stable `ALL` census on the FIX002 tip.
  It reports 29,964 findings across 33 rules: FIX002 and TD003 both fall from
  two findings to zero, while every other rule count is unchanged. FIX002 is
  the only rule newly selected in this stage; TD003 remains a separate rule
  PR.
- [x] 2026-08-21 03:28 CST: Verified the affected contracts with 254 user-
  service tests, 78 learn-context tests with four skips, 13 learner-client
  submission tests, and 127 config tests. The full backend suite passes 3,019
  tests with 17 skips; translations, repository Ruff and format, the repository
  harness, the architecture-boundary check, and every repository pre-commit
  hook also pass.
- [x] 2026-08-21 03:31 CST: Opened ready FIX002 PR
  [#2587](https://github.com/ai-shifu/ai-shifu/pull/2587) from
  `sunner/ruff-fix002` to the D100 branch after the full backend suite and
  repository pre-commit gate passed.
- [ ] Merge or retarget FIX002 PR #2587 after its predecessors without
  combining it with the TD003 rule unit.
- [x] 2026-08-21 03:42 CST: Prepared the TD003 stage on `sunner/ruff-td003`,
  stacked on FIX002. Added TD003 to the enforced selection after its two
  findings were semantically resolved in the predecessor, and documented that
  an issue link does not make a TODO acceptable while FIX002 is active.
- [x] 2026-08-21 03:42 CST: Confirmed TD003 has zero findings and the stable
  `ALL` census remains 29,964 findings across 33 rules; this policy-only stage
  changes no Python runtime or test behavior.
- [x] 2026-08-21 03:44 CST: Repository Ruff, format, generated knowledge,
  harness, architecture boundaries, development-tool checks, and every
  pre-commit hook pass on the TD003 tip.
- [x] 2026-08-21 03:45 CST: Opened ready TD003 PR
  [#2588](https://github.com/ai-shifu/ai-shifu/pull/2588) from
  `sunner/ruff-td003` to the FIX002 branch after all repository checks passed.
- [ ] Merge or retarget TD003 PR #2588 after its predecessors without combining
  it with the next rule unit.
- [x] 2026-08-21 03:55 CST: Prepared the N806 stage on `sunner/ruff-n806`,
  stacked on TD003. Replaced 21 function-local CapWords model and session-
  factory bindings with descriptive snake_case names while preserving their
  lazy loaders, then removed all four N806 per-file exceptions.
- [x] 2026-08-21 03:55 CST: The isolated repository-wide N806 scan is clean,
  all 37 owning tests pass, and the stable `ALL` census remains exactly 29,964
  findings across 33 rules with every other finding count unchanged.
- [x] 2026-08-21 03:58 CST: The full backend suite passes 3,019 tests with 17
  skips; generated collaboration and knowledge documents, the repository
  harness, architecture boundaries, development-tool checks, and every
  repository pre-commit hook also pass.
- [x] 2026-08-21 04:01 CST: Opened ready N806 PR
  [#2589](https://github.com/ai-shifu/ai-shifu/pull/2589) from
  `sunner/ruff-n806` to the TD003 branch after all local gates passed.
- [ ] Merge or retarget N806 PR #2589 after its predecessors without combining
  it with the next rule unit.
- [x] 2026-08-21 04:22 CST: Prepared the D101 stage on `sunner/ruff-d101`,
  stacked on N806. Added role- or contract-focused docstrings to all 431 public
  classes across 144 Python files, removed the global D101 exception, and
  documented how future classes should distinguish DTO, persistence, protocol,
  exception, test-group, and test-double ownership.
- [x] 2026-08-21 04:22 CST: A semantic audit found exactly 431 added class
  docstrings, no removed or changed existing class docstrings, and no executable
  AST differences after normalizing the new docstrings and two now-redundant
  empty-class `pass` statements. The stable `ALL` census falls by exactly 431
  findings to 29,533 across 32 rules; every other rule count is unchanged.
- [x] 2026-08-21 04:22 CST: The 110-test Swagger, Pydantic, DTO, and schema
  contract set passes, followed by the full backend suite at 3,019 tests passed
  with 17 skipped. Collaboration and knowledge generators, architecture fixture
  tests, identifier-example validation, repository Ruff, and format also pass.
- [x] 2026-08-21 04:24 CST: Development-tool validation and every repository
  pre-commit hook pass on the D101 tip.
- [x] 2026-08-21 04:27 CST: Opened ready D101 PR
  [#2590](https://github.com/ai-shifu/ai-shifu/pull/2590) from
  `sunner/ruff-d101` to the N806 branch after all local gates passed.
- [ ] Merge or retarget D101 PR #2590 after its predecessors without combining
  it with the next rule unit.
- [x] 2026-08-21 04:52 CST: Prepared the EM102 stage on
  `sunner/ruff-em102`, stacked on D101. Moved all 162 contextual f-string
  exception messages across 72 Python files into collision-free locals
  immediately before the original raise: 150 use `message`, while 12 functions
  with an existing `message` binding use `error_message`. EM102 is now enforced
  repository-wide with no suppression.
- [x] 2026-08-21 04:52 CST: A reversible AST audit restored all 162 direct
  f-string arguments and the one equivalent Coze URL conditional, then matched
  every executable AST to the D101 parent. The stable `ALL` census falls to
  29,175 findings across 31 rules: EM102 falls by 162, the same construct also
  removes 136 TRY003 findings, formatter-owned COM812 falls by 60, and no rule
  gains debt.
- [x] 2026-08-21 04:52 CST: Translation and identifier checkers, affected
  script help entry points, and 1,822 focused billing, payment-provider, TTS,
  ask-provider, config, analytics, auth, migration, and error-path tests pass
  with 10 skips. The full backend suite passes 3,019 tests with 17 skips;
  repository Ruff and format also pass.
- [x] 2026-08-21 04:54 CST: Collaboration and knowledge generators,
  repository harness, architecture boundaries, development-tool validation,
  and every repository pre-commit hook pass on the EM102 tip.
- [x] 2026-08-21 04:58 CST: Opened ready EM102 PR
  [#2591](https://github.com/ai-shifu/ai-shifu/pull/2591) from
  `sunner/ruff-em102` to the D101 branch after all local gates passed.
- [ ] Merge or retarget EM102 PR #2591 after its predecessors without combining
  it with the next rule unit.
- [x] 2026-08-21 05:24 CST: Prepared the EM101 stage on
  `sunner/ruff-em101`, stacked on EM102. Moved all 388 fixed exception strings
  across 135 Python files into whole-function collision-free bindings: 296 use
  `message`, 67 use `error_message`, and 25 use `exception_message`. With EM103
  already clean, the configuration now enforces the complete `EM` family
  instead of selecting one code.
- [x] 2026-08-21 05:24 CST: A reversible AST audit restored all 388 literal
  arguments, including eight bindings outside single-statement `pytest.raises`
  bodies, and found no unexpected executable difference after normalizing one
  equivalent Coze payload consolidation. The strengthened Coze test now asserts
  that `bot_id` reaches the provider request.
- [x] 2026-08-21 05:24 CST: The stable `ALL` census falls to 28,364 findings
  across 29 rules: EM101 falls by 388, the same rewrites remove all 358 TRY003
  findings, formatter-owned COM812 falls by 64, and the Coze test removes one
  ARG001 finding. PT012 and PLR0915 briefly increased, then returned to their
  parent counts; no rule gains debt.
- [x] 2026-08-21 05:24 CST: All 61 touched test modules pass 918 tests with 14
  skips, followed by the full backend suite at 3,019 tests passed with 17
  skipped. Identifier, translation, affected script-entry, repository Ruff,
  and format checks also pass.
- [x] 2026-08-21 05:26 CST: Collaboration and knowledge generators,
  repository harness, architecture boundaries, development-tool validation,
  and every repository pre-commit hook pass on the EM101 tip.
- [x] 2026-08-21 05:29 CST: Opened ready EM101 PR
  [#2592](https://github.com/ai-shifu/ai-shifu/pull/2592) from
  `sunner/ruff-em101` to the EM102 branch after all local gates passed.
- [ ] Merge or retarget EM101 PR #2592 after its predecessors without combining
  it with the next rule unit.
- [x] 2026-08-21 05:44 CST: Prepared the RUF001 stage on
  `sunner/ruff-ruf001`, stacked on EM101. Audited all 162 findings across 24
  files and 106 source lines: every occurrence is one of the five standard
  Chinese punctuation characters `，`, `：`, `！`, `？`, or `；`, used in
  Chinese prose and notification formatting or as a TTS sentence boundary.
- [x] 2026-08-21 05:44 CST: Removed the global RUF001 ignore and replaced it
  with Ruff's exact five-character `allowed-confusables` list. RUF001 now
  rejects every other confusable without rewriting runtime text or fixtures;
  RUF002 and RUF003 remain clean. The stable `ALL` census falls exactly 162
  findings to 28,202 across 28 rules, with every other rule count unchanged.
- [x] 2026-08-21 05:44 CST: Documented that future agents must preserve the
  five intentional Chinese punctuation characters, fix every other confusable
  by default, and inventory all uses before expanding the shared allowlist.
  The 323 focused notification, learner-profile, TTS, and LLM tests pass with
  five skips, and the TTS report entry point exposes its help successfully.
- [x] 2026-08-21 05:48 CST: The full backend suite passes 3,019 tests with 17
  skips. Translation checks, collaboration and knowledge generators, repository
  harness, architecture boundaries, development-tool validation, configured
  Ruff and format, and every repository pre-commit hook also pass.
- [x] 2026-08-21 05:50 CST: Opened ready RUF001 PR
  [#2593](https://github.com/ai-shifu/ai-shifu/pull/2593) from
  `sunner/ruff-ruf001` to the EM101 branch after all local gates passed.
- [ ] Merge or retarget RUF001 PR #2593 after its predecessors without
  combining it with the next rule unit.
- [x] 2026-08-21 05:59 CST: Prepared the N815 stage on
  `sunner/ruff-n815`, stacked on RUF001. An isolated scan exposed 27 findings
  hidden by two file-wide exceptions: 26 camelCase fields on the Pydantic
  `RuntimeConfigDTO` and the annotated `UserToken.userInfo` wire field.
- [x] 2026-08-21 05:59 CST: Replaced all 26 Pydantic fields with snake_case
  Python names and exact `Field(alias=...)` wire names, then changed the route
  builder to use the Python names. The one non-Pydantic `userInfo` annotation
  retains its exact JSON and generated Swagger contract through one explained
  inline suppression. Both N815 per-file exceptions are removed.
- [x] 2026-08-21 05:59 CST: The isolated repository-wide N815 scan is clean.
  Twenty-eight focused DTO, runtime-config, JSON-alias, and Swagger-contract
  tests pass; the stable `ALL` census remains exactly 28,202 findings across
  28 rules, with every other rule count unchanged.
- [x] 2026-08-21 06:01 CST: The wider billing and common-service regression
  suites pass 749 tests with 10 skips, covering the route builder, DTO payloads,
  billing consumers, and shared serialization paths.
- [x] 2026-08-21 06:04 CST: The full backend suite passes 3,020 tests with 17
  skips. Translation checks, collaboration and knowledge generators, repository
  harness, architecture boundaries, development-tool validation, configured
  Ruff, and format also pass.
- [x] 2026-08-21 06:05 CST: Every repository pre-commit hook passes on the
  N815 tip.
- [x] 2026-08-21 06:07 CST: Opened ready N815 PR
  [#2595](https://github.com/ai-shifu/ai-shifu/pull/2595) from
  `sunner/ruff-n815` to the RUF001 branch after all local gates passed.
- [ ] Merge or retarget N815 PR #2595 after its predecessors without combining
  it with the next rule unit.
- [x] 2026-08-21 06:20 CST: Prepared the N803 stage on
  `sunner/ruff-n803`, stacked on N815. Ignoring suppressions exposed exactly one
  repository-wide finding: the `UserToken` constructor copied the camelCase
  serialized field name into its Python parameter.
- [x] 2026-08-21 06:20 CST: Renamed the constructor argument to `user_info`,
  updated all five keyword call sites, and removed the only N803 suppression.
  The annotated `userInfo` attribute and JSON/Swagger field remain unchanged.
- [x] 2026-08-21 06:20 CST: The isolated N803 scan with `--ignore-noqa` is
  clean, no camelCase `UserToken` keyword caller remains, and 72 focused shared
  DTO and authentication-flow tests pass. The stable `ALL` census remains
  exactly 28,202 findings across 28 rules with no debt transfer.
- [x] 2026-08-21 06:21 CST: The wider user-service and shared DTO suites pass
  266 tests, covering every authentication provider and account-flow consumer
  of the constructor.
- [x] 2026-08-21 06:24 CST: The full backend suite passes 3,020 tests with 17
  skips. Translation checks, collaboration and knowledge generators, repository
  harness, architecture boundaries, development-tool validation, configured
  Ruff, and format also pass.
- [x] 2026-08-21 06:25 CST: Every repository pre-commit hook passes on the
  N803 tip.
- [x] 2026-08-21 06:29 CST: Opened ready N803 PR
  [#2596](https://github.com/ai-shifu/ai-shifu/pull/2596) from
  `sunner/ruff-n803` to the N815 branch after all local gates passed.
- [ ] Merge or retarget N803 PR #2596 after its predecessors without combining
  it with the next rule unit.
- [x] 2026-08-21 06:47 CST: Prepared the S101 stale-exception stage on
  `sunner/ruff-s101`, stacked on N803. The exact
  `src/api/conftest.py` exception names no tracked or on-disk file and has no
  history on any local branch; the real `src/api/tests/conftest.py` is already
  owned by the test-tree exception and has no S101 finding of its own.
- [x] 2026-08-21 06:47 CST: Removed the dead exact-file S101 exception while
  retaining the test-tree and executable self-test boundaries that have real
  assertion findings. Documented that production guards raise explicit
  exceptions and stale paths must be deleted rather than kept as commentary.
- [x] 2026-08-21 06:47 CST: Configured S101 scans with and without inline
  suppressions are clean. All 18 remaining per-file ignore patterns match real
  files, and the stable `ALL` census remains exactly 28,202 findings across 28
  rules because the removed path never hid a live finding.
- [x] 2026-08-21 06:47 CST: Collaboration and knowledge generators, repository
  Ruff and format, translation checks, repository harness, architecture
  boundaries, development-tool validation, and every repository pre-commit
  hook pass on the S101 tip.
- [x] 2026-08-21 06:50 CST: Opened ready S101 stale-exception PR
  [#2598](https://github.com/ai-shifu/ai-shifu/pull/2598) from
  `sunner/ruff-s101` to the N803 branch after all local gates passed.
- [ ] Merge or retarget S101 PR #2598 after its predecessors without combining
  it with the next rule unit.
- [x] 2026-08-21 06:55 CST: Prepared the S607 stage on
  `sunner/ruff-s607`, stacked on S101. Isolated test-tree scans with and without
  inline suppressions report zero findings, so the inherited test-tree S607
  exception is redundant rather than a hidden test contract.
- [x] 2026-08-21 08:02 CST: Expanded the existing S607 unit after a semantic
  audit found more shrinkage was safe. Ruff reported five repository-script
  calls and one backend evaluator call, while the evaluator's main variable
  command also started partial `codex` without being reported. The Windows
  application entrypoint remains one explained inline `tzutil` exception
  because that platform command name is the contract.
- [x] 2026-08-21 08:02 CST: Resolved Git and Codex through `shutil.which(...)`,
  converted the results to absolute paths, preserved each script's existing
  missing-tool behavior, and removed S607 from both script-tree exceptions.
  Four executable repository tests cover both Git queries, all three inventory
  commands, and missing Git; four backend tests cover both Codex call paths and
  both missing-Codex errors.
- [x] 2026-08-21 08:02 CST: Configured S607 passes, and an audit that ignores
  inline suppressions reports only the documented Windows `tzutil` call. All
  18 remaining per-file ignore patterns still match real files, and the stable
  `ALL` census remains exactly 28,202 findings across 28 rules without debt
  transfer.
- [x] 2026-08-21 08:03 CST: Focused executable tests pass 4 repository and 4
  backend cases. Collaboration and knowledge generators, translations,
  repository harness, architecture boundaries, development-tool validation,
  repository Ruff and format, and every pre-commit hook pass on the expanded
  S607 tip.
- [x] 2026-08-21 08:13 CST: Final Backend Tests exposed that the missing-Codex
  test entered the evaluator's macOS `/private/tmp` context before checking the
  executable on Linux. Kept the production evaluator contract unchanged and
  isolated that test with pytest's cross-platform `tmp_path`; it still proves
  the missing-tool error occurs before subprocess startup.
- [x] 2026-08-21 06:57 CST: Collaboration and knowledge generators, repository
  Ruff and format, translation checks, repository harness, architecture
  boundaries, development-tool validation, and every repository pre-commit
  hook pass on the S607 tip.
- [x] 2026-08-21 07:01 CST: Opened ready S607 PR
  [#2599](https://github.com/ai-shifu/ai-shifu/pull/2599) from
  `sunner/ruff-s607` to the S101 branch after all local gates passed.
- [x] 2026-08-21 09:21 CST: Merged S607 PR #2599 into S101 after its
  predecessor without changing the independently reviewed S607 rule unit.
- [x] 2026-08-21 07:07 CST: Prepared the S603 stage on
  `sunner/ruff-s603`, stacked on S607. Removing the test-tree exception exposes
  exactly two calls: the fresh-MySQL migration smoke test and the pinned
  LiteLLM adapter-contract test.
- [x] 2026-08-21 07:07 CST: Both calls execute the current `sys.executable`
  with a test-owned fixed `-c` script. No request, fixture, environment, or
  database value can select the executable or become a command argument, and
  child-process isolation is the behavior those tests need to exercise.
- [x] 2026-08-21 07:07 CST: Removed S603 from the test-tree exception, retained
  the two audited calls behind explained inline suppressions, and documented
  the project contract for validating subprocess executables and arguments.
- [x] 2026-08-21 07:11 CST: Configured and isolated test-tree S603 scans pass;
  ignoring suppressions exposes exactly the two audited calls. The stable
  `ALL` census remains exactly 28,202 findings across 28 rules because the
  broad exception became equivalent narrow suppressions without debt transfer.
- [x] 2026-08-21 07:11 CST: The two owning test files pass 61 tests and skip two
  explicit environment contracts: the opt-in fresh-MySQL smoke test and the
  LiteLLM 1.95.0 adapter test, because the shared local venv has 1.80.11 while
  checked-in requirements pin 1.95.0. Final backend CI owns the clean current-
  dependency execution of the latter.
- [x] 2026-08-21 07:11 CST: Collaboration and knowledge generators, repository
  Ruff and format, translation checks, repository harness, architecture
  boundaries, development-tool validation, and every repository pre-commit
  hook pass on the S603 tip.
- [x] 2026-08-21 07:14 CST: Opened ready S603 PR
  [#2601](https://github.com/ai-shifu/ai-shifu/pull/2601) from
  `sunner/ruff-s603` to the S607 branch after all local gates passed.
- [x] 2026-08-21 07:28 CST: Extended the still-unstacked S603 PR instead of
  opening a second PR for the same rule. Isolated scanning exposed four more
  calls hidden by `scripts/**` and `src/api/scripts/**`: a fixed-interpreter
  diagnostics runner, an allowlisted test-command helper, the fixed Codex
  evaluator command, and a fixed `grep` route-inventory command.
- [x] 2026-08-21 07:28 CST: Removed S603 from both script-tree exceptions and
  replaced them with per-call audits. The Prettier test helper now rejects
  executables outside `git` and `node`; the route inventory puts `--` before
  its environment-provided root so a leading-dash path cannot become a grep
  option. The other two commands already fixed the executable and constructed
  every argument from source-owned structure.
- [x] 2026-08-21 07:28 CST: Added regression coverage for the executable
  allowlist, shell-like request and prompt values remaining single arguments,
  and a leading-dash inventory directory. The two root script suites pass four
  tests; the two new backend script tests plus the original S603 owners pass 63
  tests and skip only the opt-in MySQL smoke and locally mismatched LiteLLM
  contract.
- [x] 2026-08-21 07:28 CST: Configured and isolated S603 scans pass. Ignoring
  suppressions exposes seven explicit calls repository-wide: the six S603 PR
  calls and the existing operator-supplied plugin clone. The stable `ALL`
  census remains exactly 28,202 findings across 28 rules after making the new
  tests ALL-neutral; all 18 remaining per-file patterns resolve to real files.
- [x] 2026-08-21 07:32 CST: Collaboration and knowledge generators produced no
  extra diff; repository Ruff and format, translations, repository harness,
  architecture boundaries, development-tool validation, and all 19
  pre-commit hooks pass for the extended S603 change. Final-SHA CI remains the
  post-push acceptance gate.
- [x] 2026-08-21 07:39 CST: Final Backend Tests exposed a test-only platform
  assumption: the new evaluator boundary test entered the script's macOS
  `/private/tmp` context on a Linux runner. Kept the production evaluator
  contract unchanged and isolated the test with pytest's cross-platform
  `tmp_path`; the test still exercises the exact subprocess command and stdin
  boundary it owns.
- [x] 2026-08-21 08:09 CST: Rebased S603 onto expanded S607 commit
  `ed43b47d3`. The predecessor's five resolved Git calls and resolved Codex
  version call also require S603 argument-boundary audits, so all six now have
  explained inline suppressions instead of restoring a script-tree exception.
  The S603 Codex argument test now fixes and expects the predecessor's resolved
  executable path.
- [x] 2026-08-21 08:09 CST: Configured S603 and S607 scans pass. Ignoring S603
  suppressions reports 13 reviewed boundaries: the 12 calls owned across these
  two stacked rule units plus the pre-existing operator-supplied plugin clone.
  Eight root-script tests pass, and the combined backend owners pass 67 tests
  with the same two explicit environment skips. The stable `ALL` census remains
  exactly 28,202 findings across 28 rules.
- [x] 2026-08-21 08:10 CST: After the rebase adjustment, collaboration and
  knowledge generators produced no extra diff; translations, repository
  harness, architecture boundaries, development-tool validation, repository
  Ruff and format, and every pre-commit hook pass on the final local S603 tip.
- [x] 2026-08-21 09:21 CST: Merged S603 PR #2601 into S101 after S607 without
  changing the independently reviewed S603 rule unit.
- [x] 2026-08-21 08:33 CST: Prepared the T20 stage on `sunner/ruff-t20`,
  stacked on S603. Auditing all 18 per-file patterns found that every entry
  still hides a real finding; the backend test-tree T20 boundary is the
  smallest removable unit, with all 51 prints confined to two files.
- [x] 2026-08-21 08:33 CST: Confirmed `src/api/tests/test_utils.py` has no
  repository caller and removed the obsolete debug helper. Replaced the 27
  database-backed SSE test prints with pytest report sections so diagnostics
  remain attached to failures without treating stdout as a test interface.
  A focused unit test freezes the report-section name and rendered content.
- [x] 2026-08-21 08:33 CST: Removed T20 from the backend test-tree exception
  without adding an inline or exact-file replacement. Configured T20,
  repository Ruff, and format pass; the focused SSE module passes its report
  test and skips six database-dependent cases at their existing empty-fixture
  gate. The stable `ALL` census falls 22 findings to 28,180 across the same 28
  rules, exactly matching the non-T20 debt removed with the unused helper.
- [x] 2026-08-21 08:38 CST: The full backend suite passes 3,027 tests with 17
  existing environment skips, proving no test dynamically imports the removed
  debug helper and the report-section rewrite does not disturb collection or
  neighboring test behavior.
- [x] 2026-08-21 08:40 CST: Collaboration and knowledge generators produced no
  extra diff; development-tool validation, translations, repository harness,
  architecture boundaries, configured Ruff and format, and every repository
  pre-commit hook pass on the final local T20 change.
- [x] 2026-08-21 08:42 CST: Opened ready T20 PR #2602 from
  `sunner/ruff-t20` to `sunner/ruff-s603` after the targeted, full-backend,
  harness, and repository gates passed locally.
- [x] 2026-08-21 09:21 CST: Merged T20 PR #2602 into S101 after S603. The
  resulting merge commit exposed that the S101 branch pointer already included
  ARG002, so the predecessor temporarily contained the next rule unit.
- [x] 2026-08-21 09:02 CST: Prepared the ARG002 stage on
  `sunner/ruff-arg002`, stacked on T20. The current census exposed 191 unused
  method arguments: 25 in runtime code and 166 in test fixtures or doubles,
  spread across 107 methods in 43 files.
- [x] 2026-08-21 09:02 CST: Audited every signature instead of bulk-renaming
  parameters. Removed five repository-owned method parameters and their
  dependent call-site argument, including the now-redundant trial resolver
  `app`; preserved protocol, provider, framework, fixture, and test-double
  keyword names with signature-ordered explicit consumption. No ARG002
  suppression or per-file exception was added.
- [x] 2026-08-21 09:02 CST: Enabled ARG002. The configured rule, repository
  Ruff, format, and the unchanged 209-finding ARG001 census pass. The stable
  `ALL` census falls 194 findings: all 191 ARG002 findings plus two
  formatter-conflicting COM812 findings and one ANN003 finding removed by the
  honest signature cleanup.
- [x] 2026-08-21 09:02 CST: Focused Config, billing trial, learning phase,
  provider, payment, and DTO contracts pass 193 tests with four existing
  environment skips. The full backend suite passes 3,027 tests with 17
  existing skips, executing the changed fixtures and behaviorally faithful
  doubles as well as all runtime owners.
- [x] 2026-08-21 09:03 CST: Collaboration and knowledge generators produced no
  extra diff; development-tool validation, translations, repository harness,
  architecture boundaries, configured Ruff and format, and every repository
  pre-commit hook pass on the final local ARG002 change.
- [x] 2026-08-21 09:06 CST: Opened ready ARG002 PR #2604 from
  `sunner/ruff-arg002` to `sunner/ruff-t20` after the collaboration,
  knowledge, harness, and repository gates passed locally.
- [x] 2026-08-21 09:14 CST: Fast-forwarded the user-authored merge of updated
  T20 predecessor `e4c10e10d` into ARG002. Its immediate-base diff remains the
  same 47-file ARG002 unit. On that final base, the stable census falls exactly
  194 findings from 28,185 to 27,991 across 27 rules, the isolated census falls
  from 39,571 to 39,377, and ARG001 remains exactly 209.
- [x] 2026-08-21 09:17 CST: Re-ran the full backend suite on the combined
  predecessor/ARG002 tip; all 3,032 tests pass with the same 17 environment
  skips and 733 existing warnings.
- [x] 2026-08-21 09:37 CST: Restored the stack boundary with ordinary commits:
  S101 now reverts only the accidental ARG002 merge and has exactly the T20
  worktree, while ARG002 records the repaired S101 commit as a parent without
  changing its own worktree. Ready PR #2604 is based on S101 again and exposes
  the complete 47-file ARG002 unit.
- [x] 2026-08-21 10:01 CST: Backend CI testmon ordering exposed a pre-existing
  test-isolation leak after the `Config` constructor changed: a non-app config
  test replaced the session app's process-global `Config._instance` with a
  MagicMock, so the later onboarding golden case rendered `mock.get()` as its
  demo-course ID. The isolated golden case passed, while app initialization,
  the leaking config test, and the golden case in that order reproduced the
  failure.
- [x] 2026-08-21 10:01 CST: Made the existing non-app environment fixture also
  restore the `Config` singleton it inherited. The exact three-test regression
  now passes, and the ordered app, complete Config unit/integration, and JSON
  golden suites pass all 50 tests without changing the recorded API contract.
- [x] 2026-08-21 10:05 CST: Re-ran the full backend suite after the isolation
  fix; all 3,032 tests pass with the same 17 environment skips and 733 existing
  warnings. The runtime harness on the preceding code-equivalent SHA also
  passed before the final fix commit.
- [x] 2026-08-21 10:09 CST: Reused the captured original Config instance for
  both cache clears instead of adding private-member accesses. The final stable
  census falls 196 findings from 28,185 to 27,989 and the isolated census falls
  from 39,571 to 39,375: the ARG002 unit now also removes two existing SLF001
  findings, while ARG001 remains exactly 209.
- [x] 2026-08-21 10:12 CST: Re-ran the full backend suite after the final
  private-member cleanup; all 3,032 tests still pass with 17 skips and 733
  existing warnings.
- [x] 2026-08-21 10:37 CST: Merged the latest S101 review-fix tip
  `46df6998a` into ARG002. The immediate-base diff remains the same 47-file
  ARG002 unit. Four root subprocess-boundary tests and the backend route-
  inventory test pass; configured S603/S607/T20, repository Ruff, format,
  development-tool validation, and every repository pre-commit hook also pass.
- [x] 2026-08-21 10:49 CST: Audited the next low-count candidates. PLR0911 has
  72 findings but requires control-flow redesign; FBT002 has 98 findings but
  changes stable call contracts. Selected ARG001's 209 function-argument
  findings because it extends the signature-ownership policy proven by ARG002
  and leaves ARG005 as the only unenforced `ARG` member.
- [x] 2026-08-21 11:00 CST: Prepared ARG001 across 156 functions in 76 files.
  Removed narrow repository-owned parameters from architecture, i18n, billing,
  analytics, learning, and inventory helpers and their callers; preserved
  framework callbacks, migration hooks, provider adapters, fixtures, and test
  doubles with signature-ordered explicit consumption. No suppression or
  per-file exception was added.
- [x] 2026-08-21 11:06 CST: The 613 tests from every touched test module pass
  with 11 existing environment skips, after a focused 304-test contract set
  passed with 10 skips and the architecture-boundary fixture harness passed.
  A failing order regression exposed and fixed `_ = app` shadowing the imported
  translation helper `_()`; the durable guidance now calls out this trap.
- [x] 2026-08-21 11:09 CST: The full backend suite passes all 3,032 tests with
  17 skips and 733 existing warnings. Configured ARG001, repository Ruff,
  format, and collaboration/knowledge generators pass. The stable `ALL` census
  falls by 216 from 27,989 to 27,773 across 26 rules: ARG001 falls by 209,
  COM812 by five, and ANN001 by two. The isolated census is 39,160.
- [x] 2026-08-21 11:11 CST: Repository and architecture harnesses, generated
  collaboration and knowledge documents, pinned development-tool validation,
  and every repository pre-commit hook pass on the pre-sync ARG001 worktree.
- [x] 2026-08-21 11:20 CST: Merged the current S101 tip `503377596` into
  ARG002 after its follow-up executable-resolution review fixes. Nine root
  script tests and the backend route-inventory test pass; configured S603/S607,
  repository Ruff, format, pinned development-tool validation, and every
  repository pre-commit hook pass without changing the 47-file ARG002 unit.
- [x] 2026-08-21 11:28 CST: Merged the updated ARG002 tip into ARG001. The
  immediate-base diff remains exactly the 82-file ARG001 rule unit. Nine root
  script tests and the backend route-inventory test pass on the combined tip,
  followed by configured ARG001/S603/S607, repository Ruff, format, pinned
  development-tool validation, and every pre-commit hook. Against the current
  base, the stable census falls 216 from 27,991 to 27,775 and the isolated
  census falls 216 from 39,380 to 39,164.
- [x] 2026-08-21 12:05 CST: Audited all 565 ARG005 findings: 384 lambdas in 76
  files, all under the backend test tree. The dominant contexts are 303
  `monkeypatch.setattr` callbacks and 37 `types.MethodType` test doubles. A
  mechanical underscore pass proved insufficient because production code
  invokes many of those substitutes by keyword.
- [x] 2026-08-21 12:18 CST: Removed every ARG005 finding without suppression.
  Positional-only test callbacks use explicit dummy names; keyword-compatible
  substitutes became named local or module helpers that preserve fixed
  parameter names, while intentionally open MethodType doubles use `**_kwargs`
  to absorb ignored options. The first affected-file run exposed 50 keyword-
  contract failures and the second exposed 12 more; fixing those contracts made
  all 76 touched modules pass 1,062 tests with 15 existing environment skips.
  The Ruff selection now replaces four explicit ARG001-ARG004 entries with the
  single `ARG` prefix.
- [x] 2026-08-21 12:25 CST: Compared the final tree to predecessor
  `b663a045c` in a detached baseline worktree. No other rule gains debt: the
  stable `ALL` census falls by 569 from 27,775 to 27,206 and the isolated
  census falls by the same amount from 39,164 to 38,595. ARG005 contributes
  565 removals and the signature rewrites also remove four COM812 findings.
- [x] 2026-08-21 12:31 CST: The final full backend suite passes all 3,032 tests
  with 17 existing environment skips and 733 existing warnings. Configured
  Ruff passes, both collaboration and knowledge generators reproduce their
  committed output, and repository format is clean.
- [x] 2026-08-21 12:34 CST: Repository and architecture harnesses pass with no
  new boundary violations, pinned development-tool validation confirms Ruff
  0.16.3 and the full hook toolchain, and every repository pre-commit hook
  passes on all files.
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
- D101 covers runtime-visible metadata, not comments: 103 affected classes are
  registered with the custom Swagger collector, and Pydantic can expose class
  docstrings in generated schemas. The custom collector reads annotated fields
  and inline field comments rather than `Class.__doc__`; a repository search
  found no direct runtime class-docstring consumer, and focused schema tests
  protect the framework-driven paths.
- EM102 and TRY003 overlap on dynamic built-in exception messages: naming an
  f-string before raising it resolves both findings at 136 sites even though
  only EM102 is adopted in this rule unit. Ruff format also collapses 60 now-
  simple exception calls, removing formatter-conflicting COM812 findings. One
  Coze adapter initially crossed the PLR0915 statement threshold; an equivalent
  lazy URL conditional kept that rule at its previous 128 findings rather than
  adding new debt.
- EM101 has the same overlap: naming its 388 fixed strings removes the remaining
  358 TRY003 findings, while formatting removes 64 COM812 findings. Eight test
  raises must bind their messages before the surrounding `pytest.raises` block
  so PT012 keeps the block to one statement. The Coze adapter again sat exactly
  at the PLR0915 boundary; folding its optional `bot_id` into the payload literal
  and asserting the outgoing value keeps PLR0915 at 128 without changing the
  request contract.
- Backend audit scripts under `src/api/scripts` import `flaskr` correctly when
  invoked as modules from `src/api`; executing their file paths directly from
  the repository root omits the backend package from `sys.path` and fails before
  argument parsing. The EM102 help-entry verification therefore uses
  `python -m scripts.<name> --help` from the backend root.
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
- RUF001's 162 findings are deliberate full-width Chinese punctuation in
  customer messages, TTS boundary patterns, and tests that freeze those
  language semantics. Replacing them with ASCII punctuation would change
  product and speech behavior merely to shorten configuration. Ruff's
  `allowed-confusables` setting provides the narrower resolution: allow exactly
  the five audited punctuation characters while enforcing RUF001 for every
  other confusable.
- N815's normal configured scan hid 27 findings behind two per-file ignores,
  while the stable `ALL` census also honored those exceptions. The isolated
  scan exposed that only one field was intrinsically camelCase: the annotated
  name drives both `UserToken` JSON and its generated Swagger schema. Pydantic
  aliases preserve all 26 runtime-config wire keys without sacrificing Python
  naming, so the final exception can be one field rather than two files.
- N803 did not share N815's wire constraint. A constructor parameter is an
  internal Python API even when it is assigned to a camelCase serialized
  attribute, so renaming the parameter and keyword callers removes the
  suppression without changing JSON, Swagger, or positional callers.
- S101 had one exact-file exception for `src/api/conftest.py`, but the path is
  absent and has no tracked history. The similarly named backend fixture is
  `src/api/tests/conftest.py`; it is already inside the test-tree exception and
  contains no assertions today. Exact exception paths are obligations to
  validate, not durable breadcrumbs for files that no longer exist.
- The test-tree exception grouped S607 with rules that have thousands of real
  fixture findings, but isolated scans showed no partial executable path in any
  backend test, even when inline suppressions were ignored. Six literal script
  findings and one variable-built Codex command could all use resolved absolute
  paths; only the explained Windows `tzutil` entrypoint remains. A broad rule
  list must be audited code by code, and a clean lint result for a variable
  command does not replace semantic subprocess review.
- S603 reports every subprocess even with `shell=False`, so deleting the two
  test subprocesses or moving their scripts in-process would only weaken their
  environment-isolation coverage. Both use the current interpreter and fixed
  source owned by the test; their security boundary is narrow enough to explain
  inline, allowing the entire backend test tree to become enforced. The two
  script-tree S603 exceptions hid four original calls plus six resolved-command
  calls introduced by the S607 predecessor, not a durable class of safe code.
  Auditing them individually exposed a real option-boundary gap in the route
  inventory and made both broad exceptions removable.
- T20's backend test-tree exception hid 51 prints, but they were not a durable
  test-suite contract. Twenty-four belonged to an unreferenced debug helper;
  the other 27 were captured diagnostics in one database-backed SSE test.
  Pytest report sections preserve that failure context directly, allowing the
  broad exception to disappear without scattering inline suppressions.
- ARG002's 191 findings could not be fixed safely by blindly adding an
  underscore to parameter names: provider calls, framework callbacks, pytest
  fixtures, and test doubles receive those values by keyword. Explicitly
  consuming compatibility-only values preserves those names, while semantic
  review still removed five genuinely unnecessary method parameters. Removing
  the trial DTO's `app` also exposed the resolver's now-unused function
  parameter; deleting that dependent argument kept ARG001 exactly at 209
  instead of shifting debt to the next rule.
- ARG001 exposed a Python-specific compatibility-consumption trap: assigning
  `_ = app` inside a function that also calls the imported translation helper
  `_()` turns `_` into a local Flask object and fails only at runtime. Removing
  the owned parameter (or using `del value` for a fixed external signature)
  preserves both the callback contract and translation behavior.
- D100 included one zero-byte, unreferenced `test_rag.py` placeholder. Removing
  it was more honest than inventing a module purpose and also removed one
  CPY001 finding; every documented module otherwise differs from its parent
  only by the first docstring statement.
- The next numerically smaller candidate, PLR0911, spans 72 complex control-flow
  functions across authentication, billing, payment, permissions, and Alembic
  infrastructure. It is not a safe mechanical unit: adopting it requires
  behavior-specific decomposition rather than result-variable or threshold
  workarounds, so TC003 was the smaller reviewable exception-removal stage.
- FIX002 and TD003 reported the same two TODOs. Treating FIX002 as a semantic
  review exposed two different exit paths: the password-login security gap
  required a real guard with failure-path tests, while the compatibility
  checkpoint could be deleted only after confirming current and preview
  clients use the canonical input key and the pinned MarkdownFlow release has
  passed one release cycle. Resolving the work removes both rule findings, but
  only FIX002 is selected in this stage so the one-rule PR contract remains
  intact.
- The smallest useful next stage was not the lowest visible global finding
  count. N806 was already selected, but four per-file exceptions hid 21
  ordinary local bindings from the normal and stable `ALL` censuses. An
  isolated scan showed that every case could preserve its lazy loader or
  cross-session factory while using a descriptive snake_case value, so the
  exceptions were removable rather than intrinsic test contracts.

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
- 2026-08-21: S607 applies to contributor tooling as well as runtime code.
  Resolve external commands once per operation, make the result absolute, keep
  the existing missing-tool contract, and inspect variable-built subprocess
  commands that Ruff cannot identify before retaining a directory exception.
- 2026-08-21: T20 applies to ordinary tests. Put concise context in assertion
  messages and longer diagnostic summaries in pytest report sections. Retain a
  directory exception only for developer scripts whose stdout is the product;
  do not use one for a mixed test tree.
- 2026-08-21: For the ARG family, delete parameters only when the callable and
  callers own the complete signature. Protocol, provider, framework, fixture,
  and test-double signatures keep their keyword-compatible parameter names and
  consume compatibility-only values explicitly in signature order. Rename a
  lambda parameter to an underscore dummy only after proving all calls are
  positional. Otherwise promote a fixed keyword contract to a named helper;
  reserve `**_kwargs` for test doubles that deliberately accept an open set of
  ignored options. A fixture parameter can own setup even when the test body
  never reads it. Do not trade an argument finding for a broken keyword call,
  renamed pytest fixture, or broad suppression.

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

The FIX002 stage makes unfinished-work markers enforceable only after resolving
their actual contracts. Password login now throttles repeated failures per
identifier and client IP using expiring HMAC-fingerprinted counters, returns a
translated dedicated error at the configured limit, clears an account counter
after successful authentication, and never stores or logs the raw identifier
or address. The expired interaction-key remap is removed after focused backend
and learner-client tests prove canonical submissions and preserve noncanonical
keys instead of silently renaming them. The stable `ALL` census falls exactly
four findings to 29,964 across 33 rules without transferring debt. Future
agents are directed to complete security work, prove rollout exit conditions,
or move genuinely future work into the owning ExecPlan or issue rather than
hiding it through comment wording or lint suppression.

The TD003 stage separately enables the issue-link requirement after FIX002
removed every TODO marker. It adds no code change and no finding reduction,
but preserves one-rule reviewability on the path toward `select = ["ALL"]`.
Future agents now know that TD003 is defense in depth, not permission to leave
an issue-linked TODO: unfinished work belongs in the owning plan or issue, and
an intrinsic future exception would still need the real durable issue link.

The N806 stage removes four per-file exceptions that had treated local model
and session-factory values as if they were class declarations. Twenty-one
bindings now use descriptive snake_case names while the imported classes keep
their CapWords identities and the deliberate lazy-loading boundaries remain
unchanged. All 37 owning tests pass, an isolated repository-wide N806 scan is
clean, and the stable census is unchanged because it already honored those
exceptions. Future agents now preserve lazy imports and name their local class
values explicitly instead of moving imports or adding file-wide suppressions.

The S101 stale-exception stage removes the exact `src/api/conftest.py` entry
because that path is neither tracked nor present. The actual backend fixture
is under the already-exempt test tree and currently contains no assertions.
Configured scans with and without inline suppressions stay clean, every
remaining per-file ignore pattern resolves to real files, and the stable
`ALL` census remains 28,202 findings across 28 rules. Future agents now keep
assertions in tests and self-tests, use explicit exceptions for production
guards, and delete obsolete exact-file exceptions instead of preserving them
as historical commentary.

The S607 stage removes the test-tree and both script-tree exceptions. Five
repository-maintenance findings, one backend evaluator finding, and one
variable-built Codex command now resolve absolute executable paths while
preserving their existing missing-tool behavior. Four repository tests and
four backend tests cover the Git and Codex success and failure contracts; the
explained Windows `tzutil` platform entrypoint is the only inline exception.
Configured S607, repository Ruff, format, and harness pass, and the stable
census remains 28,202 findings across 28 rules. Future runtime, test, and
contributor code now follows the same executable-resolution contract.

The S603 stage removes the backend test-tree and both script-tree exceptions,
replacing them with 12 explained inline audits. The two child-process tests run
the current interpreter against fixed, test-owned source. The diagnostics
runner does the same with a fixed repository script; both Codex calls use the
resolved executable and source-owned arguments; the Prettier helper allowlists
`git` and `node`; the route inventory terminates grep options before its dynamic
directory; and five Git calls use resolved executables with fixed subcommands.
Eight root-script tests pass, while the backend script tests and original S603
owners pass 67 tests with only the two explicit environment skips. Configured
S603 and S607 scans pass, the stable census remains 28,202 findings across 28
rules, and future code validates every subprocess boundary at the call rather
than exempting tests or contributor scripts as a class.

The T20 stage removes T20 from the backend test-tree exception without adding
a narrower replacement. An unreferenced debug-print helper is deleted, while
the database-backed SSE diagnostic test attaches its summaries to pytest report
sections and has a focused test for that contract. Configured T20, repository
Ruff, and format pass; the stable census falls to 28,180 findings across 28
rules. Future tests now use assertion messages or pytest report sections, while
the two developer-script trees retain T20 because stdout is their interface.

The ARG002 stage enables unused-method-argument enforcement with no
suppression. Five repository-owned parameters and their dependent call-site
argument disappear; 186 protocol- or fixture-owned parameters retain their
keyword-compatible spelling and are explicitly consumed across 102 methods.
Focused contract tests pass 193 cases with four skips, the final combined
backend tip passes 3,032 cases with 17 skips, and the stable census falls to
27,989 findings across 27 rules without changing the 209-finding ARG001
baseline. The test-isolation follow-up also removes two existing SLF001
findings while keeping Config constructor tests from replacing the session
app singleton. Future agents now
distinguish an owned method signature from one imposed by an external contract.

The ARG001 stage extends that same ownership rule to functions. Eighteen
repository-owned parameters disappear from 17 narrow helpers and all callers;
framework callbacks, Alembic and SQLAlchemy hooks, provider adapters, fixtures,
and behaviorally faithful test doubles keep their keyword-compatible names and
consume compatibility-only values explicitly. All 209 ARG001 findings are
removed without suppression, while five COM812 and two ANN001 findings also
disappear. Every touched test module, the architecture fixture harness, and the
full backend suite pass. On the current predecessor, the stable census falls by
216 from 27,991 to 27,775 findings across 26 rules.

The ARG005 stage completes the unused-argument family and collapses four
explicit ARG001-ARG004 selectors to the single `ARG` prefix. All 565 findings
across 384 lambdas in 76 backend test files are removed without suppression.
Affected-file tests exposed 62 real keyword-call regressions from the initial
mechanical rename, so fixed keyword contracts now use typed named helpers and
intentionally open MethodType doubles use `**_kwargs`. All 1,062 affected tests
pass with 15 existing environment skips, followed by the complete backend at
3,032 tests passed with 17 skips. The stable census falls by 569 from 27,775 to
27,206 and the isolated census falls from 39,164 to 38,595, with no rule
gaining debt.

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
