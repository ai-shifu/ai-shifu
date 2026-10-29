---
title: Upgrade Ruff to 0.17.3
---

## Purpose / Big Picture

Use the latest stable Ruff release, 0.17.3, consistently in CI and local
development. Preserve the checked-in lint policy and runtime behavior while
adapting existing datetime imports to the upgraded import-alias convention.

## Progress

- [x] 2026-10-29 16:30 CST: Fetched `origin/main`, confirmed a clean checkout,
  and created `sunner/upgrade-ruff-0.17.3` from the current main revision.
- [x] 2026-10-29 16:31 CST: Verified the latest stable version against the
  official GitHub release and PyPI. Audited all current version references.
- [x] 2026-10-29 16:33 CST: Updated six tooling pins and install commands,
  plus current-version references in two active plans.
- [x] 2026-10-29 16:36 CST: Adjusted datetime aliases, verified normalized
  AST equivalence, and audited consumers for former namespace dependencies.
  Seven Ruff policy regressions and 87 affected backend tests passed.
- [x] 2026-10-29 16:37 CST: Passed repository-wide lint, formatting, developer
  tooling, harness, architecture, and all-files lefthook checks. Prepared the
  ready PR description and validation evidence; leave merging to the user.

## Surprises & Discoveries

- The installed Homebrew binary already reports 0.17.3, while the repository
  pins 0.16.5. The updated doctor must validate the new exact version.
- Ruff 0.17.3 reports ten ICN001 findings in nine files because `datetime`
  module imports now require the `dt` alias. All 1,812 Python files already
  pass the upgraded formatter.
- The host's default Python lacks the pinned Markdown parser. Use an isolated
  Python 3.11 tooling environment and the existing backend environment for
  tests without changing shared installed packages.
- The existing backend environment has markdown-flow 0.3.4 rather than the
  pinned 0.4.2. Install only 0.4.2 into an isolated temporary overlay and use
  it on the focused test process's `PYTHONPATH`.

## Decision Log

- Pin 0.17.3 exactly, as confirmed by [PyPI](https://pypi.org/project/ruff/0.17.3/)
  and the [official release](https://github.com/astral-sh/ruff/releases/tag/0.17.3).
- Keep `ruff.toml` unchanged. This upgrade does not adopt additional rule
  families or widen exemptions; independent policy work remains in
  `docs/exec-plans/active/ruff-rule-minimization.md`.
- Preserve historical release references in completed plans and journals.
  Update only executable pins, contributor commands, and active guidance.

## Outcomes & Retrospective

All six operational version locations and two active-plan references now use
0.17.3. Nine files adopt the required datetime alias; their ASTs are unchanged
after normalizing the alias. Existing policy tests passed (7 tests), and
focused backend regressions passed (87 tests). Ruff check, Ruff format, the
strict developer-tool doctor, repository harness, and the all-files hook gate
passed. A separate read-only review found no actionable issues. No deployment
or merge is part of this upgrade.

## Context and Orientation

`lefthook.yml`, `.github/workflows/lint.yml`, and
`src/api/requirements-ci.txt` configure lint and test tooling.
`scripts/check_dev_tools.py` checks the installed version and provides install
instructions mirrored in `INSTALL_MANUAL.md` and
`docs/engineering-baseline.md`. Three existing Ruff policy test modules
exercise documentation, annotation, and test-fixture exception boundaries.

## Plan of Work

1. Align all tooling version pins and current contributor guidance.
2. Rename only the datetime module bindings required by ICN001 and inspect
   consumers for string-based imports or monkeypatch targets.
3. Run existing policy and affected backend regressions, then repository
   Ruff, formatter, harness, developer-tool, and all-files hook checks.
4. Record results and create a focused, ready pull request.

## Concrete Steps

Use `/tmp/ai-shifu-ruff-upgrade-venv` for Ruff 0.17.3 and markdown-it-py 4.0.0.
Run `python -m unittest discover -s src/api/tests/scripts -p 'test_ruff_*policy.py'`.
Run affected backend tests with the existing Python 3.11 environment, then
`ruff check .`, `ruff format --check .`, `python scripts/check_dev_tools.py`,
`python scripts/check_repo_harness.py`, and
`lefthook run pre-commit --all-files --no-stage-fixed --exclude '.codex/**'
--exclude '.agents/**'`. The exclusions are managed, read-only agent assets.
Regenerate knowledge indexes after staging intended Markdown changes so the
new plan is indexed.

The backend run used the existing Python 3.11 environment with the isolated
markdown-flow overlay. From `src/api`, it covered:

```text
tests/common/test_http_body_policy.py
tests/service/common/test_dto_base.py
tests/service/shifu/test_operator_datetime_localization.py
tests/service/order/test_uow_failure_paths.py
tests/service/profile/test_profile_value_contracts.py
tests/service/user/test_sessions.py
tests/service/user/test_session_store_boundaries.py
tests/service/user/test_verification_code_errors.py
tests/test_pydantic_field_compatibility.py
```

## Validation and Acceptance

- CI, test dependencies, the local doctor, and contributor commands all use
  Ruff 0.17.3, and no operational 0.16.5 pin remains.
- Existing lint policy and formatter checks pass repository-wide.
- Existing policy regressions and affected runtime tests pass.
- The developer-tool doctor and repository hook gate pass.
- Delivery is a ready PR; this task never merges into `main`.

## Idempotence and Recovery

Check-only Ruff commands and policy tests are safe to repeat. Hook fixers can
rewrite files; inspect their diff and preserve unrelated changes. The isolated
tooling environment can be recreated without altering shared packages.

## Interfaces and Dependencies

The lint selection and exceptions remain owned by `ruff.toml`. Runtime API,
database, timestamp serialization, and product analytics contracts do not
change. The CI requirements pin participates in backend test-cache identity.
