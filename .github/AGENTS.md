# GitHub Automation Rules

This file owns engineering rules for repository automation under `.github/`,
including workflow YAMLs, release automation, issue templates, and GitHub-side
AI compatibility instruction files.

## Scope

- Apply this file to `.github/`, especially `.github/workflows/`,
  `.github/instructions/`, and `.github/copilot-instructions.md`.

- GitHub engineering conventions live in the
  [engineering baseline](../docs/engineering-baseline.md), especially:
  [CI/CD And Release Workflow](../docs/engineering-baseline.md#cicd-and-release-workflow),
  [Development Workflow](../docs/engineering-baseline.md#development-workflow),
  [Environment Configuration](../docs/engineering-baseline.md#environment-configuration),
  and [Troubleshooting](../docs/engineering-baseline.md#troubleshooting).

- This directory owns repository test automation, release-draft behavior, and
  image build-and-publish automation that affects backend, frontend, and
  Docker surfaces together.

- The instruction compatibility files under `.github/` are mirrors of the
  primary manual docs and must stay aligned with them.

## Do

- Inspect the affected workflows, current triggers, path filters, and related
  downstream jobs before changing automation behavior.

- Preserve workflow trigger intent and keep branch, tag, and path filters as
  narrow as the current release or validation model requires.

- Keep secrets, tokens, registry credentials, and configurable toggles in
  GitHub Actions secrets or vars instead of hardcoding them in YAML.

- Keep `prepare-release.yml`, `build-latest.yml`, and `build-on-release.yml`
  aligned with the actual image names, tag semantics, and Docker expectations
  used elsewhere in the repo.

- When changing `.github/instructions/` or
  `.github/copilot-instructions.md`, update the corresponding manual docs and
  generated mirrors in the same change.

## Avoid

- Do not widen workflow triggers or remove path filters casually.

- Do not inline secrets, tokens, or environment-specific registry values in
  workflow files.

- Do not change release versioning or image tag behavior in one workflow
  without checking the related release and build workflows together.

- Do not treat `.github/instructions/` or `copilot-instructions.md` as the
  source of truth when the nearest manual `AGENTS.md` and `CLAUDE.md` say
  otherwise.

## Commands

- `find .github/workflows -maxdepth 1 -type f | sort` lists the repository
  workflow set before you change trigger scope or release behavior.

- `git diff -- .github/workflows .github/instructions .github/copilot-instructions.md`
  shows the affected automation and compatibility surfaces together.

- `pre-commit run --files .github/workflows/*.yml .github/copilot-instructions.md .github/instructions/*.instructions.md`
  is the focused hygiene pass for workflow and GitHub-side instruction changes.

- `python scripts/check_repo_harness.py` is required when `.github/`
  instruction mirrors or manual AI-doc entry points change.

- `python scripts/check_architecture_boundaries.py` is required when workflow
  path filters or repo-harness coverage changes affect source ownership.

## Tests

- Manually review at least one affected workflow for trigger scope, secret
  usage, and downstream job assumptions whenever workflow logic changes.

- When release or image-build automation changes, cross-check the workflow
  behavior against Docker image names, tags, and release expectations in the
  handbook.

- When only GitHub-side AI instruction files change, run
  `python scripts/check_repo_harness.py` and note that runtime automation
  was not executed.

- When workflow changes affect backend, frontend, Docker, or scripts paths,
  verify the path filters and changed-file assumptions still match the intended
  automation surface.
- Keep `repo-harness.yml`, `runtime-harness.yml`, and
  `harness-gardening.yml` aligned with the actual harness assets they are meant
  to police.

## Related Skills

- `SKILL.md` is the repository-level skill routing index.

- `src/api/SKILL.md` and `src/cook-web/SKILL.md` remain the right entry points
  when a workflow change is tightly coupled to backend or frontend behavior.

- Keep durable GitHub automation rules here, and put multi-step debugging or
  release runbooks into focused skills only when the same workflow repeats.
