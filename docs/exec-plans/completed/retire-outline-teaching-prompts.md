---
title: Retire chapter and lesson prompts
status: completed
owner_surface: shared
last_reviewed: 2026-11-04
---

# Retire chapter and lesson prompts

## Purpose / Big Picture

Teaching and follow-up instruction resolution must use the course
prompt exclusively. Chapter and lesson prompts are retired across
authoring, publication, copying, backups, learning, and operator views. This
is the application cleanup stage before a separate database-column migration.
The durable behavior contract is
[Course Prompts](../../product-specs/course-prompts.md).

## Progress

- [x] 2026-11-04 02:50 UTC: Audit current consumers and confirm outline temperatures
  were already removed by revision `fde432bceab4`.
- [x] 2026-11-04 02:50 UTC: Confirm application cleanup precedes schema deletion.
- [x] 2026-11-04 03:00 UTC: Remove runtime, authoring, backup, and frontend
  dependencies; focused backend and frontend checks pass.
- [x] 2026-11-04 03:10 UTC: Initially implement saved-session instruction
  synchronization; superseded by the later decision to preserve initial messages.
- [x] 2026-11-04 03:14 UTC: Verify legacy column values are ignored and course
  instructions remain effective: 4,812 backend tests passed, 93 skipped;
  88 focused frontend tests and TypeScript checks passed.
- [x] 2026-11-04 03:14 UTC: Pass the full repository pre-commit gate and prepare
  the task branch for a ready pull request. Merge and deployment are outside
  this implementation plan.
- [x] 2026-11-04 03:54 UTC: Address review feedback with independent initial
  prompt ownership metadata and real-engine serialization regressions; 484
  focused Agent tests passed, with additional DB/Debug assertions verified in
  a 95-test subset. The compatibility layer was later removed. Strengthen the
  operator, copy, and authoring-write tests.
- [x] 2026-11-04 05:17 UTC: Remove optional saved-session prompt synchronization
  and ownership metadata at the owner's request; preserve the existing bundle
  update and Debug script-edit rebuild. Rebase onto main without conflicts;
  all 1,992 Agent tests pass, including six new session-state regressions.

## Surprises & Discoveries

Outline `ask_llm_system_prompt` stores generated follow-up context and is a
different feature from the chapter/lesson teaching prompt (`llm_system_prompt`).
Keep that context and the outline follow-up enablement inheritance intact.

Updating a resumed session's script bundle alone does not update the initial
model message. Saved sessions can retain historical outline constraints even
when the current course prompt is empty.
Historical messages do not consistently preserve the source of a constraints
block: the old host could update the bundle alone, and the engine clears
`request_inputs` after a turn. Text matching a constraints block may therefore
be a learner's first question. Preserve ambiguous evidence; the later schema
cleanup must explicitly settle session reset/migration for those cases.

PR review reproduced the same ambiguity even when the message exactly matches
the bundle's previous constraints. No textual match proves host ownership.
An optional ownership-metadata compatibility layer was implemented and reviewed,
then removed at the owner's request to keep this PR focused on field retirement.

## Decision Log

- Retire outline prompts only. Preserve course-level prompts,
  course temperatures, generated outline follow-up contexts, and permissions.
- Keep the existing outline teaching columns mapped with empty defaults until
  the subsequent schema migration. Business logic must not read, copy, compare,
  expose, import, export, or apply their historical values.
- Legacy authoring and backup inputs may still contain outline prompt keys;
  ignore them rather than reject otherwise valid requests. New responses and
  exports omit these keys. Existing saved history is not rewritten.
- Operator details return the course prompt directly. Remove the redundant
  source field, constants, types, labels, and conditional display paths together.
- Preserve saved initial model messages without ownership metadata or automatic
  prompt synchronization. Keep the original bundle-constraints update and
  Debug's explicit script-edit rebuild. A course-prompt-only change or removal
  requires a new or reset session to affect the initial message.

## Outcomes & Retrospective

Application field retirement is implemented and verified. Authoring, copying,
publication, backups, learning, and operator calculations no longer consume
outline teaching columns. Generated follow-up context remains effective.
The full authoring/learning regression suite passed (4,812 passed, 93 skipped),
as did focused frontend tests, type checks, and repository gates. Independent
review clarified the saved-session instruction boundary. The optional initial
message refresh and ownership metadata are removed. No database DDL is included.

The follow-up schema cleanup must settle reset/migration of ambiguous historical
Agent messages as described in the canonical product contract. Those messages
are deliberately preserved at this stage rather than reinterpreted or erased.

The review follow-up preserves saved initial messages, including learner text
identical to old constraints. Operator estimates/details, course copying, and
authoring writes also seed nonempty retired values to prove those paths ignore
them.

Manual review removes the remaining single-source discriminator across the
operator API and UI and standardizes the product term as Course Prompt. The
optional saved-session helper is removed following the owner's scope decision.
Lesson-settings analytics still describes permission and visibility saves. Its fixed
`variant=lesson` input is removed while the existing delivered payload is kept.

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
estimates and never appear in authoring responses or new backups. New sessions
use the current course prompt; saved initial messages follow the documented
preservation boundary. Creating,
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
