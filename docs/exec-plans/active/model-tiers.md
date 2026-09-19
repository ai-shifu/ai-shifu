---
title: Course model tiers
---

## Purpose / Big Picture

Offer Fast, Balanced and Ultimate for course generation and text follow-up,
independently. Store reserved tier aliases in the existing llm and ask_llm fields so operators
can replace models without editing courses. Preserve explicit legacy model names. Keep credit multipliers and Live voice.

## Progress

- [x] 2026-09-19: Correct English/Chinese Docker quickstarts and the installation
  manual to require both provider credentials and the Fast mapping. Document
  upgrade maintenance and report-only cleanup for every installation mode.

- [x] 2026-09-19: Remove the cleanup audit model and runtime ledger queries.
  Keep exact previous/new values and original UTC modification times in the
  archived cleanup report; invocation metadata retains tier, resolved model and
  course revision identity. Generate a forward removal migration because the
  earlier ledger revision has already been pushed to dev.
- [x] 2026-09-19: Verify report-only cleanup, atomic failure recovery, SQL-free
  selection metadata and populated schema removal/downgrade. All 265 focused
  backend cleanup, gateway, preview and course-selection tests passed.

- [x] 2026-09-19: Integrate #2853's refreshed base with #2860 owner-billed
  settings previews. All tiers retain permission checks, actor identity and
  owner settlement through direct LLM, provider fallback and knowledge synthesis.
  The 151 backend integration tests, 138 frontend tests and TypeScript passed.

- [x] 2026-09-19: Integrate #2853's preview-temperature coverage while retaining
  strict alias resolution and audited blank-to-Fast cleanup. The 164 relevant
  preview/course/prompt tests passed (4 skipped).
- [x] 2026-09-19: Validate explicit provider edits for tier-backed courses and
  preserve untouched configurations when provider metadata is unavailable. All
  131 settings/model-selector tests and TypeScript passed; the added regression
  cases reproduced 20 failures before the fix.

- [x] 2026-09-19: Preserve course revision and cleanup provenance through the
  2.0 gateway; 440 gateway/agent/course-selection regression cases passed.
- [x] 2026-09-19: Recheck tier availability before Live-to-text transitions and
  ignore stale responses after close. All 72 settings/selector tests and
  TypeScript passed; rejected transitions retain Live and its analytics value.

- [x] 2026-09-19: Stack on PR #2853 and retain its course-only model and
  temperature contract. Chain the audit migration after outline-column removal.
- [x] 2026-09-19: Verify the combined migration and runtime contracts: 1702
  related backend tests passed (96 skipped), alongside 65 frontend tests,
  TypeScript and the repository-wide gate.

- [x] 2026-09-18: Replace tier columns with aliases in existing fields and adapt
  authoring/runtime/UI/cleanup. Local regressions and repository gate verified.

- [x] 2026-09-17: Confirmed independent tier fields, Fast defaults, legacy-model
  compatibility and explicit data cleanup rather than runtime empty fallback.
- [x] Implement schema, audited cleanup, selection and runtime contracts.
- [x] Implement localized selectors and analytics.
- [x] Complete targeted regressions, type checks and the full repository gate.
- [x] 2026-09-17: Address PR review gaps in operator copy/list paths, field
  validation, resolver failures, strict credit estimation and migration provenance.
- [x] 2026-09-17: Bound cleanup reads with keyset pages while preserving atomic
  recovery; verified the newest audit batch after recovery/reapply.
- [ ] Deploy configured mappings and run report-only cleanup in the target environment.

## Surprises & Discoveries

- Course draft/published rows explicitly copy model settings; clone/equality,
  import/export and publishing must preserve aliases in the original fields.
- PR #2853 removes outline model and temperature columns. Preview, learning and
  follow-up read only course model selections; outline prompts and follow-up
  switches retain their existing inheritance.
- A text alias and a Live model share the original field and cannot be active
  simultaneously. Switching modes replaces the selected value.

## Decision Log

- 2026-09-19: The user rejected the dedicated cleanup audit table. Supersede
  earlier ledger/provenance decisions below: migration traceability lives in
  archived JSON reports and a pre-cleanup database backup. Runtime metadata
  reports `tier` or `legacy_model`, without migration-batch queries. Keep old
  usage records unchanged. No new model-selection columns are introduced.
- 2026-09-19: Keep revision `5ca8717e482f` unchanged because it was pushed to dev
  and may already have run. The generated child `abbe9d73bdb1` drops its ledger;
  both fresh installations and existing dev databases end without that table.
  Downgrading recreates only its empty schema. Never rewrite or remove an
  applied revision, and archive any existing ledger before dropping it if its
  historical cleanup records are needed.

- 2026-09-19: Physical model catalog misses do not freeze a selected tier's
  provider settings after a teacher edits them. Validate and save explicit
  provider, scalar and object edits; metadata-driven fallback is not an edit.
  Preserve untouched configurations during metadata outages. Preview always
  resolves the selected course model and uses its temperature, including zero;
  a missing temperature uses the configured default. Blank model rows still
  require cleanup to Fast instead of falling back to a deployment model.

- 2026-09-19: Stack this PR on #2853 (`sunner/course-only-llm-settings`). Do not
  restore removed outline or block-preview model overrides. Both learning
  engines reject uncleaned empty course selections, then route cleaned Fast
  aliases through the shared gateway. The audit revision follows `fde432bceab4`
  so the combined migration graph has one head.

- 2026-09-18: Supersede the separate-field design. Store fast/balanced/ultimate
  directly in llm and ask_llm; remove the unmerged tier-column additions.
- Backfill course rows whose original model field is blank to fast;
  preserve explicit legacy course models and outline prompts/switches. Archive cleanup reports.
- New writes/imports normalize empty course selections to fast. Reads do not
  silently normalize missing selections. Unconfigured tiers fail closed.
- Resolve follow-up tiers only when an LLM is actually invoked: healthy external
  provider answers do not require unused LLM mappings, while fallback, synthesis
  and guardrail rejection replies still resolve and snapshot their model.
- Preserve existing explicit model choices until a teacher changes them; record actual invocation models
  and selection metadata in usage/Langfuse. Existing rates still bill actual models.
- Keep summary generation strict after the required cleanup: missing course
  follow-up selections are configuration errors rather than main-model fallbacks.
- Preserve course selection identity and actual models without additional
  runtime database queries. Migration-batch provenance is available only in
  archived operator reports. Cleanup precedes traffic.
- Operator lists carry the current revision tier and display its configured model
  even when provider routing is unavailable; missing mappings stay empty.
- Keep real model details off teacher-facing controls; operator/legacy APIs may
  retain them. This is not a network-data secrecy boundary.

## Outcomes & Retrospective

The #2853 integration passed 1702 related learning, course, migration and golden
regressions (96 skipped). The coverage includes one Alembic head, populated
upgrade/downgrade, both learning engines after cleanup, ignored outline/block
model overrides, copied/published course aliases and retained prompt inheritance.
Frontend verification passed all 65 settings/selector tests and TypeScript.

The alias implementation passed 1917 related backend/configuration/golden tests
(95 skipped), including the new import/default regression cases.
The settings/model-selector Jest suites passed 65 tests. TypeScript, the full
lefthook gate, repository harness, architecture
boundaries and the unit-of-work ratchet passed. Production configuration and
cleanup execution remain a deployment operation; no production rows were changed.

Review follow-up preserves the approved Fast cleanup contract. The pre-existing
preview admission issue was fixed independently in #2860 and is now integrated
through #2853's refreshed base. Settings previews require course edit permission
and charge the course owner while recording the requesting actor, including
tier-based invocations. The golden SSE seed models the post-cleanup Fast follow-up
selection; recorded JSON/SSE fixtures remain unchanged.

## Context and Orientation

The shifu service owns model rows, revisions, publication and imports. Learning
resolves inherited settings and invokes the shared flaskr.api.llm wrappers.
ShifuSetting and AskSettingsSection own the teacher controls. Existing ModelList
also handles TTS and must retain its generic behavior.

## Plan of Work

1. Reuse existing model fields; provide a report-only cleanup CLI and tests.
2. Add system tier mappings, options API, write normalization and runtime
   selection throughout preview, learning, follow-up and publication.
3. Add tier selectors, separate text/Live choice, translations and analytics.
4. Run targeted regressions, shared contract checks and repository hooks.

## Concrete Steps

Use LLM_TIER_FAST_MODEL, LLM_TIER_BALANCED_MODEL and LLM_TIER_ULTIMATE_MODEL.
Only LLM_TIER_FAST_MODEL is required at startup. Balanced and Ultimate remain
optional and unavailable until configured. None of the three has a default model.
Create with fast in both course fields. Omitted update fields preserve values;
empty course selections normalize to fast. Outlines have no model fields.
Existing course API model/ask_model fields carry aliases or legacy names.

## Validation and Acceptance

Verify actual persisted cleanup values and JSON reports, rerun safety, blank
normalization, inherited settings, revision equality/copy/publication and import
round trips. Verify changed mappings affect new invocations while old usage
keeps its actual model. Verify unavailable mappings, multipliers, Live switching,
permissions and absence of model names in teacher controls.

Extend creator_shifu_setting_save after successful editable-course saves with
main_model_tier and follow_up_model_tier. Values are fast/balanced/ultimate/legacy;
follow-up may be not_applicable for Live. Count once per successful save, never
on render, rejected validation or failed saves. Existing adoption consumers use
these fields; missing historical fields mean unknown. No real model, provider,
prompt or arbitrary text is collected. Tracking failure cannot affect saving.

## Idempotence and Recovery

Cleanup only changes blank course model values. Take a database backup before
applying changes and preserve the preview/apply/verification JSON files with the
deployment record. Each report contains a batch ID and UTC creation time;
each change contains table, row, field, exact previous/new model values and the
original UTC `previous_updated_at`. A failed update rolls back the whole cleanup.
Reports are printed only after the command returns: a crash or output-write
failure after commit can lose the apply report, so retain the preview and backup.
Schema and cleanup precede enabling tier reads. Stop old writers during final
deployment verification. Do not roll back to code unaware of tiers after
teachers start saving them.

## Interfaces and Dependencies

Course DTOs keep model/ask_model and exports keep llm/ask_llm. GET
/api/llm/model-tier-list returns three stable tier values, availability and credit
multipliers. Legacy model and follow-up capability endpoints remain compatible.
Keep existing provider routing, usage recording, billing and UTC helpers.

## Deployment Runbook

This change uses a maintenance cutover because the same release contains strict
tier reads. Configure Fast and its provider credentials before cutover; configure Balanced
and Ultimate only when enabling those choices. Stop traffic, background workers and all old writers; run the new image
as a maintenance job before allowing its API or web assets to serve users.
Do not perform a rolling switch with uncleaned course rows.

Take a database backup before schema upgrade and cleanup. If an older tier build
already created `shifu_model_tier_migration_audit`, export its records before
upgrading when their history is needed: the new migration drops the table.

From `src/api` in that configured deployment environment:

```bash
FLASK_APP=app.py flask db upgrade
FLASK_APP=app.py flask console shifu migrate-default-model-tiers > tiers-preview.json
FLASK_APP=app.py flask console shifu migrate-default-model-tiers --apply > tiers-applied.json
FLASK_APP=app.py flask console shifu migrate-default-model-tiers > tiers-verify.json
```

Review the preview count and per-table/row/field entries before apply. Archive
all three outputs with the deployment record. Verify that applied entries and
count match the preview and that the verification count is zero. The cleanup
reads historical revisions in keyset pages of at most 500 ORM rows; the JSON
report still grows with the number of changes. Keep these operator artifacts
private; they are not product analytics.
The applying transaction locks candidate course rows and remains atomic across
pages, so a later failure rolls back all changed selections. This requires the
maintenance window rather than committing partial cleanup batches. Historical
revisions, including deleted revisions, are included. The command never contacts
a model provider or changes billing history.

Then start the new API/workers, verify `/api/llm/model-tier-list` reports all
configured tiers as available, and release the new web assets/traffic. Validate
a cleaned Fast course and an explicit legacy course in both preview and learning.
The deployment is not complete just because the schema migration succeeded.

Before any new tier selections have been saved and while writers remain
stopped, an operator can use the saved report and database backup to restore only
the recorded table/row/field pairs whose current tier still equals `new_model`;
restore `previous_model` and `previous_updated_at`. No automatic data rollback
command is provided. After new selections exist, use a forward fix: an old binary
cannot interpret them correctly.

Invocation metadata includes `model_tier`, `resolved_model`, the selection table,
field and row ID, and `model_selection_origin` (`tier` or `legacy_model`). Cleaned
Fast selections use the same runtime metadata as any other Fast selection;
there is no migration-batch lookup. Earlier usage records keep their existing
metadata unchanged. New cloned revisions retain their tiers and their own row
identity. Provider routing and metering use the same resolved identity for each
invocation.

The final schema has no cleanup ledger or additional tier columns. The old
ledger-creation revision stays in history solely for upgrade compatibility;
its child removes the table without changing course selections. Upgrade and
schema-only downgrade remain covered. No production configuration, schema
upgrade or data cleanup has been executed by this implementation task.
