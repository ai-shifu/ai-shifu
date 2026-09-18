---
title: Course model tiers
---

## Purpose / Big Picture

Offer Fast, Balanced and Ultimate for course generation and text follow-up,
independently. Store reserved tier aliases in the existing llm and ask_llm fields so operators
can replace models without editing courses. Preserve explicit legacy model names. Keep credit multipliers and Live voice.

## Progress

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
- [ ] Deploy configured mappings and run audited cleanup in the target environment.

## Surprises & Discoveries

- Course draft/published rows and outline draft/published rows explicitly copy
  settings; clone/equality, import/export and publishing must all carry tiers.
- Empty outline settings mean inheritance and must not be backfilled.
- A text alias and a Live model share the original field and cannot be active
  simultaneously. Switching modes replaces the selected value.

## Decision Log

- 2026-09-18: Supersede the separate-field design. Store fast/balanced/ultimate
  directly in llm and ask_llm; remove the unmerged tier-column additions.
- Backfill course rows whose original model field is blank to fast;
  preserve explicit legacy models and all outline inheritance. Retain audit rows.
- New writes/imports normalize empty course selections to fast. Reads do not
  silently normalize missing selections. Unconfigured tiers fail closed.
- Resolve follow-up tiers only when an LLM is actually invoked: healthy external
  provider answers do not require unused LLM mappings, while fallback, synthesis
  and guardrail rejection replies still resolve and snapshot their model.
- Preserve existing explicit model choices until a teacher changes them; record actual invocation models
  and selection metadata in usage/Langfuse. Existing rates still bill actual models.
- Keep summary generation strict after the required cleanup: missing course
  follow-up selections are configuration errors rather than main-model fallbacks.
- Preserve migration provenance with one indexed read per Fast course field per
  request, including cached misses. Outlines and other tiers never need this
  ledger lookup; non-request jobs retain direct reads. Cleanup precedes traffic.
- Operator lists carry the current revision tier and display its configured model
  even when provider routing is unavailable; missing mappings stay empty.
- Keep real model details off teacher-facing controls; operator/legacy APIs may
  retain them. This is not a network-data secrecy boundary.

## Outcomes & Retrospective

The alias implementation passed 1917 related backend/configuration/golden tests
(95 skipped), including the new import/default regression cases.
The settings/model-selector Jest suites passed 65 tests. TypeScript, the full
lefthook gate, repository harness, architecture
boundaries and the unit-of-work ratchet passed. Production configuration and
cleanup execution remain a deployment operation; no production rows were changed.

Review follow-up preserves the approved Fast cleanup contract. The pre-existing
non-teacher preview admission behavior is outside this tier change and remains
open in PR #2840. The golden SSE seed now models the post-cleanup Fast follow-up
selection; recorded JSON/SSE fixtures remain unchanged.

## Context and Orientation

The shifu service owns model rows, revisions, publication and imports. Learning
resolves inherited settings and invokes the shared flaskr.api.llm wrappers.
ShifuSetting and AskSettingsSection own the teacher controls. Existing ModelList
also handles TTS and must retain its generic behavior.

## Plan of Work

1. Reuse existing model fields; add only a cleanup audit ledger, CLI and tests.
2. Add system tier mappings, options API, write normalization and runtime
   selection throughout preview, learning, follow-up and publication.
3. Add tier selectors, separate text/Live choice, translations and analytics.
4. Run targeted regressions, shared contract checks and repository hooks.

## Concrete Steps

Use LLM_TIER_FAST_MODEL, LLM_TIER_BALANCED_MODEL and LLM_TIER_ULTIMATE_MODEL.
Only LLM_TIER_FAST_MODEL is required at startup. Balanced and Ultimate remain
optional and unavailable until configured. None of the three has a default model.
Create with fast in both course fields. Omitted update fields preserve values;
empty course selections normalize to fast. Empty outline selections continue
inheriting. Existing API model/ask_model fields carry aliases or legacy names.

## Validation and Acceptance

Verify actual persisted cleanup values and audit records, rerun safety, blank
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

Cleanup only changes blank course model values. Preserve original values in the
audit ledger with table/row/field/batch/UTC time and old/new model selections.
Preview before apply and audit after. Schema and cleanup precede enabling tier
reads. Stop old writers during final deployment verification. Do not roll back
to code unaware of tiers after teachers start saving them.

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

From `src/api` in that configured deployment environment:

```bash
FLASK_APP=app.py flask db upgrade
FLASK_APP=app.py flask console shifu migrate-default-model-tiers > tiers-preview.json
FLASK_APP=app.py flask console shifu migrate-default-model-tiers --apply > tiers-applied.json
FLASK_APP=app.py flask console shifu migrate-default-model-tiers > tiers-verify.json
```

Review the preview count and per-table/row/field entries before apply. Archive
all three outputs with the deployment record. Verify that the applied count
matches the preview, the applied batch has that many audit rows in
`shifu_model_tier_migration_audit`, and the verification count is zero. The
cleanup reads historical revisions in keyset pages of at most 500 ORM rows; the
compact preview/apply identity report still grows with the number of changes.
The applying transaction remains atomic across pages so a later failure rolls
back all tiers and audit entries. This deliberately requires the documented
maintenance window rather than committing partial cleanup batches.
The applying transaction locks candidate course rows and writes audit entries
atomically; historical revisions, including deleted revisions, are included.
The command never contacts a model provider or changes billing history.

Then start the new API/workers, verify `/api/llm/model-tier-list` reports all
configured tiers as available, and release the new web assets/traffic. Validate
a cleaned Fast course and an explicit legacy course in both preview and learning.
The deployment is not complete just because the schema migration succeeded.

Before any new tier selections have been saved, an operator can use the audit
batch to restore only the recorded table/row/field pairs whose current tier
still equals `new_model`; restore `previous_model` while preserving `updated_at`.
Take a database snapshot first and keep the audit ledger. After new selections
exist, use a forward fix: an old binary cannot interpret them correctly.

Invocation metadata includes `model_tier`, `resolved_model`, the selection table,
field and row ID, and `model_selection_origin` (`tier`, `legacy_model`, or
`migrated_default`). A migrated revision also carries `model_migration_batch`.
When a cleanup is recovered and reapplied, provenance uses the latest matching
audit ID. New cloned revisions retain their tiers and have their own row identity; the
migration ledger continues identifying the original cleaned revisions. Provider
routing and metering use the same resolved identity for each invocation.

The unmerged schema revision now creates only the audit ledger. No tier columns
are added to course or outline tables; upgrade/downgrade remain covered. No
production configuration, schema upgrade or data cleanup has been executed by
this implementation task.
