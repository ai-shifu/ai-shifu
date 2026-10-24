# Course-only models and temperatures

## Purpose / Big Picture

Teachers select teaching and follow-up models and temperatures only in course
settings. Chapter, lesson, and block configuration cannot override those four
values. Chapter and lesson system prompts, prompt inheritance, follow-up enable
switches, and publication prompt generation retain their existing behavior.

## Progress

- [x] 2026-09-18 10:18 UTC: Inspected the current main branch and model-resolution paths.
- [x] 2026-09-18 10:59 UTC: Narrowed the change to models and temperatures; restored outline prompts and follow-up switches.
- [x] 2026-09-18 10:59 UTC: Regenerated the unapplied migration from the narrowed model change.
- [x] 2026-09-18 11:08 UTC: Completed final regression tests and repository checks.

## Surprises & Discoveries

- Both teaching engines and Live follow-up classification used outline model
  overrides even though the authoring UI had no model selector there.
- Block preview accepted model and temperature overrides independently of the
  course. Its prompt overrides are separate and remain supported.
- Publication generates outline follow-up prompts. Keeping prompts requires
  preserving this existing generation path and its follow-up status behavior.

## Decision Log

- Only remove `llm`, `llm_temperature`, `ask_llm`, and `ask_llm_temperature`
  from `DraftOutlineItem` and `PublishedOutlineItem`.
- Preserve `llm_system_prompt`, `ask_llm_system_prompt`, and `ask_enabled_status`,
  including their UI, APIs, inheritance, persistence, import/export, copying,
  history, and publishing behavior. Preserve existing analytics contracts.
- Ignore legacy outline model/temperature keys on import and block preview;
  never promote these overrides to course defaults. Export retained prompt and
  follow-up status fields without obsolete models or temperatures.
- Preserve course/deployment fallback semantics. Follow-up model and temperature
  always come from the course, even when a chapter or lesson supplies its prompt
  and enable/disable setting.
- Regenerate the unmerged, unapplied migration to drop four columns from each
  outline table. Downgrade restores empty model/temperature columns, not their
  historical values. Retained prompts and follow-up status survive both directions.

## Outcomes & Retrospective

The final change removes only models and temperatures outside the course.
Chapter and lesson prompts, inheritance, follow-up switches, authoring controls,
and publication prompt generation retain their original behavior.

Validation completed on 2026-09-18:

- Full backend suite: 4,737 passed, 107 skipped; 46 subtests passed.
- Focused model/prompt/migration tests: 135 passed, 4 skipped.
- Operator course detail tests: 64 passed after updating the shared fixture to
  omit deleted model fields while keeping prompt data.
- Frontend chapter settings, store, and admin detail tests: 44 passed.
- Frontend type checking and lint passed.
- Populated SQLite migration tests confirm prompts, follow-up switches, content,
  and course settings survive upgrade/downgrade.
- Development-tool verification and repository-wide pre-commit checks passed,
  including Ruff, architecture, harness, translation, and unit-of-work checks.

No live database has been modified. The migration remains a deployment step.

## Context and Orientation

`DraftShifu` / `PublishedShifu` own course model settings. `DraftOutlineItem` /
`PublishedOutlineItem` own chapter and lesson content, prompts, and follow-up
switches. `context_v2.py`, `agent/lesson_entry.py`, and `utils_v2.py` resolve
teaching and follow-up models. Authoring helpers under `service/shifu/` copy
records for publication, course copying, history, and import/export.

## Plan of Work

Remove only outline model and temperature fields and make runtime consumers use
course values with existing deployment fallbacks. Preserve prompt and switch
paths. Narrow preview types and observability contracts. Generate the migration
against an isolated pre-change schema, then verify retained data through a
populated upgrade/downgrade and regression tests across the affected services.

## Concrete Steps

1. Update model fields and runtime/authoring consumers together.
2. Generate the Alembic revision from an isolated pre-change schema and review it.
3. Test model resolution, retained prompts/switches, import/export, copying,
   publication, and migration preservation.
4. Run backend regressions, frontend tests/type checking/lint, development-tool
   verification, and repository-wide pre-commit checks.

## Validation and Acceptance

Conflicting legacy model and temperature overrides cannot change course model
selection in either learning engine, block preview, or follow-up. Chapter and
lesson prompts and follow-up switches continue to work. Old files import with
prompt/status values intact and export without the four obsolete keys. Migration
upgrade drops exactly eight columns while retaining all prompt/status values,
course settings, and lesson content.

## Idempotence and Recovery

The migration runs once through Alembic. Deploy application and schema together:
old application versions still reference removed columns. Restore the old schema
before rolling back application code; restoring old model/temperature overrides
requires a pre-migration backup. No live migration is part of this task.

## Interfaces and Dependencies

Course APIs stay unchanged. Outline APIs retain `system_prompt`; exported outline
JSON retains prompt and follow-up switch fields. Block preview retains prompt
inputs but ignores legacy model/temperature inputs. No application dependencies
or environment variables are added.
