# Repository Scripts Rules

This file owns engineering rules for shared maintenance and generation scripts
under `scripts/`, including translation utilities and AI-doc tooling.

## Scope

- Apply this file to `scripts/`, including Python and JavaScript generators,
  validation scripts, translation helpers, and repo-maintenance utilities.

- Script engineering conventions live in the
  [engineering baseline](../docs/engineering-baseline.md), especially:
  [Testing Expectations](../docs/engineering-baseline.md#testing-expectations),
  [CI/CD And Release Workflow](../docs/engineering-baseline.md#cicd-and-release-workflow),
  [Environment Configuration](../docs/engineering-baseline.md#environment-configuration),
  and [Internationalization Rules](../docs/engineering-baseline.md#internationalization-rules).

- This directory owns repeatable repo maintenance, translation validation, and
  AI-doc generation or validation logic used by both local development and CI.

- Script changes can rewrite tracked files or change automation behavior, so
  keep ownership and side effects explicit.

## Do

- Inspect the script’s current call sites, declared outputs, and sibling
  checker or generator scripts before changing behavior.

- Keep script inputs, outputs, and file ownership explicit, repo-relative, and
  predictable so local runs and CI jobs behave the same way.

- Prefer idempotent behavior for maintenance and generation scripts that may
  be rerun in CI or by multiple contributors.

- Keep generator and checker pairs aligned whenever generated artifacts,
  validation markers, or expected file inventories change.

- Keep script-facing text, comments, and documentation English-only; user-
  facing translations still belong in shared i18n data rather than in scripts.

## Avoid

- Do not silently rewrite tracked files outside the script’s declared
  ownership.

- Do not hardcode machine-specific paths, secrets, or local-only assumptions
  into shared scripts.

- Do not let validation scripts drift from the artifacts or invariants they
  are supposed to verify.

- Do not mix unrelated responsibilities into one script when an existing
  generator, checker, or migration utility already owns the surface.

## Commands

- `python scripts/check_repo_harness.py` validates the AI-doc ownership,
  knowledge metadata, and generated-file model after doc-tooling changes.
- `python scripts/check_architecture_boundaries.py` validates the committed
  frontend/backend boundary baseline and fixture coverage.

- `python scripts/generate_ai_collab_docs.py` regenerates the derived AI-doc
  mirrors after AI instruction or generator changes.

- `python scripts/build_repo_knowledge_index.py` regenerates the knowledge
  indexes and generated document inventory.

- `python scripts/check_translations.py && python scripts/check_translation_usage.py --fail-on-unused`
  is the shared translation validation pass after translation-tooling changes.

- `python scripts/generate_languages.py` refreshes locale metadata when
  translation inventory behavior changes.

## Tests

- Run the nearest checker after changing any generator or maintenance script.
- Run `python scripts/check_architecture_boundaries.py --run-fixture-tests`
  after changing the boundary checker or its fixture inventory.

- When a script writes tracked files, rerun it and review the resulting diff to
  confirm deterministic output.

- When translation scripts change, rerun translation parity, translation usage,
  and locale-metadata checks in the same task.

- When AI-doc generation or validation scripts change, regenerate docs, rerun
  `python scripts/check_repo_harness.py`, and run focused pre-commit on the
  touched files.

## Related Skills

- `SKILL.md` is the repository-level skill routing index.

- `src/api/SKILL.md` and `src/cook-web/SKILL.md` remain the right entry points
  when a shared script change is tightly coupled to backend or frontend
  behavior.

- Keep durable script rules here, and create a focused skill only when the
  same multi-step maintenance workflow repeats often enough to justify it.
