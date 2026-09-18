# Course-only LLM and follow-up settings

## Purpose / Big Picture

Teachers select the teaching and follow-up models only in course settings.
Chapter, lesson, and block configuration must not override models, temperatures,
system prompts, or the follow-up enable/disable setting.
Both learning engines, preview, publication, copying, and imports follow this
contract. Deployment defaults remain the fallback for an empty course model.

## Progress

- [x] 2026-09-18 10:18 UTC: Inspected the current main branch and all model-resolution paths.
- [x] 2026-09-18 10:38 UTC: Removed all seven outline settings, runtime overrides, and frontend prompt controls.
- [x] 2026-09-18 10:38 UTC: Generated and reviewed the migration; populated SQLite upgrade/downgrade test passed.
- [x] 2026-09-18 10:49 UTC: Completed repository checks and final regression run: 4,688 backend tests and 45 frontend tests passed.

## Surprises & Discoveries

- The outline model fields still affect both teaching engines and Live follow-up
  classification despite having no current outline authoring controls.
- Block preview accepts an independent request model override.
- Old import files and the observability inventory also carry outline models.

## Decision Log

- User clarified that all related settings belong at the course level. Remove
  `llm`, `llm_temperature`, `llm_system_prompt`, `ask_enabled_status`, `ask_llm`,
  `ask_llm_temperature`, and `ask_llm_system_prompt` from both outline tables.
- Ignore legacy outline model keys on import; never promote them to course
  defaults. Export only the course model fields.
- Drop outline model columns in a new migration; do not rewrite applied history.
  Downgrade restores empty columns, not discarded overrides. Back up old values
  before deployment if rollback needs those historical settings.
- Course-setting preview for unsaved course form values remains valid; block
  preview no longer accepts a separate model selection.
- Retire `creator_outline_prompt_save`; chapter title edits now use the existing
  `creator_outline_setting_save` event with `variant=chapter`. Contract, migration,
  payload, consumer, deduplication, and failure rules are documented in
  `docs/product-specs/web-umami-contract-remediation.md`.
- Remove publication summary generation: its only persisted outputs were the
  deleted outline prompts and forced follow-up enable flags. Publishing now
  preserves the course-owned prompt and follow-up status without background edits.

## Outcomes & Retrospective

All seven settings are now course-owned. Both teaching engines resolve course
models; block preview, text/Live follow-up, outline projection, authoring,
import/export, copying, and publication no longer accept outline overrides.
Chapter and lesson settings no longer expose a separate system prompt. Publishing
preserves the course follow-up status and prompts instead of generating outline
prompts or forcing follow-up on.

Validation completed on 2026-09-18:

- Full backend suite: 4,688 passed, 107 skipped, and 46 subtests passed.
- Frontend chapter settings, store, and admin detail suites: 45 tests passed.
- Frontend type checking and lint passed; lint reports existing warnings only.
- Populated SQLite migration upgrade/downgrade passed and Alembic has one head.
- Development-tool verification and repository-wide pre-commit checks passed,
  including Ruff, translations, harness, architecture, and unit-of-work checks.

A temporary test-only SOCKS dependency was needed by the existing proxy-enabled
Langfuse tests. It is not a new application dependency. No live database was
modified; coordinated application/schema deployment remains a release step.

## Context and Orientation

`DraftShifu` / `PublishedShifu` own course settings. `DraftOutlineItem` /
`PublishedOutlineItem` own every chapter and lesson, including version history.
`context_v2.py`, `agent/lesson_entry.py`, and `utils_v2.py` resolve the teaching
and follow-up settings. Authoring helpers under `service/shifu/` copy those
records for publication, course copying, history, and import/export.

## Plan of Work

Remove outline selectors from models and persistence; make all runtimes use
the course model, with existing fallback and provider validation behavior.
Remove obsolete preview/type and observability contracts. Generate a migration
from the changed SQLAlchemy models against an isolated local schema fixture.
Update fixtures and test runtime selection, import/export, copying, publication,
and migration preservation of course fields and outline content.

## Concrete Steps

1. Modify the model and runtime/authoring consumers together.
2. Run `FLASK_APP=<isolated migration app> flask db migrate` and inspect its diff.
3. Run focused backend regression tests, then the affected service suites.
4. Run frontend type checking, lint, repository harness, architecture checks,
   development-tool checks, and the repository pre-commit gate.

## Validation and Acceptance

Conflicting legacy outline values cannot override course models in draft or
published learning, preview, follow-up, or engine 2.0. Follow-up mode and temperatures
come from the course; legacy outline overrides are ignored. Old files import
successfully and export without outline model keys. Migration upgrade removes only fourteen columns and
preserves course settings and outline content. No production database is changed
as part of implementation.

## Idempotence and Recovery

The migration runs once through Alembic. Deploy application and schema together:
old application versions still reference the removed columns. Restore the old
schema before rolling back application code; restoring historical overrides
requires a pre-migration backup. Local test databases are disposable.

## Interfaces and Dependencies

Course API `model` / `ask_model` stays unchanged. Outline JSON no longer exports
the seven removed settings; legacy input keys are ignored. Block preview ignores
legacy model, temperature, and system-prompt override input. The outline API
no longer exposes `system_prompt`. No dependencies or environment variables are added.
