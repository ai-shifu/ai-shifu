---
title: Retire chapter and lesson teaching prompts
status: completed
owner_surface: shared
last_reviewed: 2026-11-04
---

# Retire chapter and lesson teaching prompts

## Purpose / Big Picture

Teaching and follow-up instruction resolution must use the course teaching
prompt exclusively. Chapter and lesson teaching prompts are retired across
authoring, publication, copying, backups, learning, and operator views. This
is the application cleanup stage before a separate database-column migration.
The durable behavior contract is
[Course Teaching Prompts](../../product-specs/course-teaching-prompts.md).

## Progress

- [x] 2026-11-04 02:50 UTC: Audit current consumers and confirm outline temperatures
  were already removed by revision `fde432bceab4`.
- [x] 2026-11-04 02:50 UTC: Confirm application cleanup precedes schema deletion.
- [x] 2026-11-04 03:00 UTC: Remove runtime, authoring, backup, and frontend
  dependencies; focused backend and frontend checks pass.
- [x] 2026-11-04 03:10 UTC: Refresh identifiable persisted Agent-session
  constraints without changing historical scripts or learner conversations;
  document and test the conservative boundary for ambiguous old messages.
- [x] 2026-11-04 03:14 UTC: Verify legacy column values are ignored and course
  instructions remain effective: 4,812 backend tests passed, 93 skipped;
  88 focused frontend tests and TypeScript checks passed.
- [x] 2026-11-04 03:14 UTC: Pass the full repository pre-commit gate and prepare
  the task branch for a ready pull request. Merge and deployment are outside
  this implementation plan.

## Surprises & Discoveries

Outline `ask_llm_system_prompt` stores generated follow-up context and is a
different feature from the chapter/lesson teaching prompt (`llm_system_prompt`).
Keep that context and the outline follow-up enablement inheritance intact.

Updating a resumed session's script bundle alone does not update the initial
model message. Existing sessions must also discard the retired outline
constraints in that message, including when the course prompt is empty.
Historical messages do not consistently preserve the source of a constraints
block: the old host could update the bundle alone, and the engine clears
`request_inputs` after a turn. Text matching a constraints block may therefore
be a learner's first question. Preserve ambiguous evidence; the later schema
cleanup must explicitly settle session reset/migration for those cases.

## Decision Log

- Retire outline teaching prompts only. Preserve course-level teaching prompts,
  course temperatures, generated outline follow-up contexts, and permissions.
- Keep the existing outline teaching columns mapped with empty defaults until
  the subsequent schema migration. Business logic must not read, copy, compare,
  expose, import, export, or apply their historical values.
- Legacy authoring and backup inputs may still contain outline prompt keys;
  ignore them rather than reject otherwise valid requests. New responses and
  exports omit these keys. Existing saved history is not rewritten.
- Operator details keep their response fields for the resolved teaching prompt
  and source, but return only the course prompt and `course` (or an empty source).
- Refresh saved initial constraints only when their ownership is identifiable;
  never infer host ownership from an arbitrary learner-authored XML-like tag.

## Outcomes & Retrospective

Application field retirement is implemented and verified. Authoring, copying,
publication, backups, learning, and operator calculations no longer consume
outline teaching columns. Generated follow-up context remains effective.
The full authoring/learning regression suite passed (4,812 passed, 93 skipped),
as did focused frontend tests, type checks, and repository gates. Independent
review identified and corrected a resumed-session instruction refresh gap and
an initial-learner-input preservation issue. No database DDL is included.

The follow-up schema cleanup must settle reset/migration of ambiguous historical
Agent messages as described in the canonical product contract. Those messages
are deliberately preserved at this stage rather than reinterpreted or erased.

## Context and Orientation

`shifu/models.py`, `shifu_outline_funcs.py`, `route.py`, `dtos.py`,
`shifu_publish_funcs.py`, and `shifu_import_export_funcs.py` own persistence
and authoring. `learn/agent/lesson_entry.py` and `learn/ask/context.py` resolve
teaching instructions. Operator details and cost estimates have parallel
resolution paths. `ChapterSetting.tsx` is shared by chapter and lesson settings.

## Plan of Work

Remove outline prompt configuration and its data-flow consumers. Resolve
teaching instructions from the correct draft or published course version;
retain publication and cross-course validation. Replace override-inheritance
tests with regressions proving populated legacy fields have no effect.

## Concrete Steps

Run focused backend authoring, learning, operator, and import/export tests and
frontend settings/analytics tests. Run developer-tool checks, the repository
harness, architecture checks, formatting, and the full pre-commit gate.

## Validation and Acceptance

Legacy chapter/lesson columns are never read for model instructions or cost
estimates and never appear in authoring responses or new backups. Identifiable
saved host constraints are refreshed; ambiguous old messages follow the
documented preservation boundary. Creating,
renaming, copying, publishing, and restoring a course still work. Course-level
instructions and generated follow-up contexts retain their behavior.

### Settings analytics compatibility

- Decision and metric: daily successful chapter and lesson settings saves by
  save type; this measures confirmed saves, not prompt editing or exposure.
- Chapter event: retire `creator_outline_prompt_save`; emit the new
  `creator_chapter_setting_save` for authenticated editable existing chapters
  only after a changed, valid settings request succeeds.
- Chapter payload: exactly `shifu_bid`, `outline_bid` (stable pseudonymous
  business IDs), and `save_type=auto|manual` (low cardinality).
- Lesson event: retain `creator_outline_setting_save` and its settings meaning;
  remove the retired `prompt_change` dimension. Payload is exactly `shifu_bid`,
  `outline_bid`, `save_type`, `variant=lesson`, `learning_permission`, and
  `hide_chapter`. Existing permission enums remain unchanged.
- Deduplication: one event per accepted successful save; exclude unchanged,
  read-only, unsaved, invalid, failed, render-only, and duplicate close paths.
- Consumers: authoring-adoption reports must use the new chapter series after
  deployment. Keep historical prompt-save and prompt-change series separate;
  do not backfill or dual-write. No repository-owned query consumes these names.
- Delivery and verification: use shared tracking, explicit scalar allowlists,
  no authored text or prompt-derived metadata. Test exact payloads, success
  timing, exclusions, deduplication, and synchronous/asynchronous tracker failures.

## Idempotence and Recovery

No schema or historical data is changed. Legacy clients can send ignored prompt
keys. Reverting application code restores the old behavior while the database
columns remain available. Column deletion is a separate deployment step.

## Interfaces and Dependencies

Coordinate DTOs, request parsing, frontend types and UI, backup shape, model
helpers, publication, operator estimates, runtime instructions, analytics
producers, canonical documentation, and focused regressions in this change.
