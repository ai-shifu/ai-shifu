---
title: Numbered course models
---

## Purpose / Big Picture

Offer up to nine independently configured course text models. Teachers see
administrator-defined names, or the configured model IDs when names are absent,
and credit multipliers; stable numeric selections are stored in the existing
llm and ask_llm strings. Historical selections need
no cleanup: invalid selections resolve to model 1 without rewriting the rows.

## Progress

- [x] 2026-09-19 UTC: Confirmed the numbered configuration and runtime fallback
  contract with the user; fetched the current PR branch before implementation.
- [x] 2026-09-19 UTC: Implement registry, configuration, routing and catalogs.
- [x] 2026-09-19 UTC: Preserve raw selections through reads, unrelated saves,
  imports and publication; update selectors and analytics.
- [x] 2026-09-19 UTC: Remove cleanup tooling, update deployment guidance and Arena.
- [x] 2026-09-19 UTC: Complete regression checks and prepare the PR #2840 update.
- [x] 2026-09-19 UTC: Replace the stale preview test with numbered-model
  resolution and unchanged-selection coverage after the full backend CI run.
- [x] 2026-09-19 UTC: Guard both settings submission paths against course changes
  during validation and replacement-detail loading; verify 81 settings tests.
- [x] 2026-09-19 UTC: Remove both unapplied cleanup-audit migrations after the
  user confirmed the table-creation migration had never run.
- [x] 2026-09-19 UTC: Align operator course model keys with the numbered label
  catalog; verify 33 backend course-list tests and 22 operator-page tests.
- [x] 2026-09-19 UTC: Document optional names for every model number; only the
  model 1 ID is required, and unnamed options display their configured IDs.
- [x] 2026-09-19 UTC: Validate effective primary selections during publication,
  copying and import/export so retained Live IDs follow the numbered fallback;
  preserve raw stored values and active Live follow-up validation.
- [x] 2026-09-19 UTC: Use model 1 for the gateway default alias when the legacy
  default setting is blank; preserve explicit overrides and rate eligibility.
- [x] 2026-09-19 UTC: Defer preview provider resolution until an LLM block runs,
  preserving static previews and actual-call model metadata and error behavior.

## Surprises & Discoveries

- Both model fields are submitted on every frontend save today. Displaying a
  fallback directly would overwrite historical choices unless model edits are
  tracked independently and omitted fields preserve their exact stored values.
- Generic LLM wrappers also serve direct physical-model calls. Course fallback
  must be explicitly scoped, not applied indiscriminately in provider code.
- The old allowed-model catalog also feeds rates, the external gateway and
  Arena. These retain physical identities using a projection of numbered slots.
- Optional slot reads must use environment configuration directly; the old
  database-backed accessor repeatedly probed absent keys during metadata reads.
- Operator listings previously filled blank model values from historical rows.
  Remove that LLM backfill so reads preserve blanks and agree with runtime model 1.
- Serialize settings writes and align model values with edit-version snapshots
  across async validation and saves; stale requests cannot acknowledge newer edits.
- A latest-callback ref can switch course identity during asynchronous form
  validation. Cancel the old submission before reading the next course's callback,
  for both close-to-save and native form submission.
- Operator course summaries must expose the same effective numeric key as the
  course model catalog so display labels resolve correctly. Selection keys stay
  numeric even when a configured model ID serves as the fallback display label.
- Live validation previously rejected a retained Live-only primary ID before
  course fallback could take effect. Authoring transfers must validate the
  effective primary number while keeping the follow-up ID available for Live
  provider validation and copying both saved selections exactly.
- The physical catalog formerly marked a default only through DEFAULT_LLM_MODEL.
  Numbered-only deployments need the gateway alias to use model 1 when that
  optional setting is blank, while preserving explicit gateway defaults and
  the existing route and rate eligibility checks.
- Eager preview model resolution rejected static MarkdownFlow documents when
  their configured provider was unavailable. Carry selection metadata through
  preview setup and resolve the physical binding only at the shared LLM call
  boundary, as learner execution already does.

## Decision Log

- 2026-09-19: Supersede fixed Fast/Balanced/Ultimate tiers and all cleanup plans.
  Only LLM_MODEL_1_ID is required and has no default. Nonblank IDs enable optional
  numbers 2-9. Names for all numbers are optional; absent or blank names display
  the configured model ID. Names without IDs do not enable options. Numeric
  identifiers may have gaps.
- 2026-09-19: Keep llm and ask_llm as strings. New courses store "1" in both.
  Existing blank values, physical IDs, old aliases and unconfigured numbers
  resolve to 1 at runtime. Only explicit model saves normalize stored values.
- 2026-09-19: Removing a slot causes fallback; restoring it reactivates existing
  references. Do not automatically renumber, migrate, or repair course rows.
- 2026-09-19: Configured provider failures are errors, not fallback triggers.
  Live voice and direct physical-model calls retain their separate contracts.
- 2026-09-19: Remove both LLM_ALLOWED variables, their legacy database readers,
  and the three LLM_TIER variables. Never enumerate all discovered models as a
  fallback catalog. The external gateway retains its default-alias and admission
  semantics, and billing continues to use physical model identities.
- 2026-09-19: The user confirmed the cleanup-audit table was never created.
  Remove both unapplied audit revisions and their tests. This feature reuses
  existing schema and requires no database migration or data-cleanup command.
- 2026-09-19: Keep PR #2840 stacked on #2853. Preserve course-only model and
  temperature settings, chapter prompts and owner-billed settings previews.

## Outcomes & Retrospective

Combined backend regression passed 1,050 cases. All 138 frontend cases across
12 suites passed, with TypeScript and lint checks. Gateway/golden behavior and
physical billing identity are covered. The full repository pre-commit gate,
repository harness, architecture boundaries and unit-of-work checks passed. The
26 Arena worker tests pass. A broader Arena run passed 174 tests with four
pre-existing observer mocks failing because their signatures omit the existing
`tool_calls_are_output` keyword; those unrelated tests and production calls are
unchanged from the starting commit. No production data or deployment configuration
has been changed by this work.

Review follow-up corrected a stale preview-model assertion found by backend CI;
the full preview context module now passes 80 tests with four skipped. Settings
review reproduced old-course data being submitted to a newly selected course
during validation. Both submission paths now cancel when the context changes,
and native submissions are blocked while replacement details load. All 81
settings tests and TypeScript checks pass, including same-course edits during
validation and absence of save callbacks or analytics for canceled submissions.

## Context and Orientation

The LLM module owns slot configuration, physical routing and usage metadata.
The shifu service owns persistence, publication, imports and DTOs. Learning
services resolve course choices before invocation. ShifuSetting owns explicit
model edits; the shared model selector renders server-provided names.

## Plan of Work

1. Add numbered registry and separate course selection from physical routing.
2. Expose effective choices and fallback flags while preserving stored values.
3. Update UI, analytics, internal catalogs and Arena; remove cleanup tooling.
4. Verify the contracts and publish the focused change to the existing PR.

## Concrete Steps

Configure LLM_MODEL_<1..9>_ID, with optional LLM_MODEL_<1..9>_NAME labels.
Only a nonblank ID is needed for a slot; slot 1 is mandatory and always the
course default. Missing, empty or whitespace-only names use the corresponding
configured model ID as the label; names without IDs do not enable slots. Resolve
valid configured numbers as themselves and everything else as 1. Provider routing
errors do not change the chosen slot. Follow-up blanks use 1 independently of
the main course choice. Live-only follow-up IDs retain their existing meaning.

Reads never write. Unrelated saves preserve exact strings, including blanks.
Explicit model saves store a configured numeric choice or 1. Copies, exports,
publication and supplied import selections preserve raw values; missing or null import
fields default to 1. Keep original/effective/physical identities in invocation
metadata, with a bounded fallback reason and course revision identity.

## Validation and Acceptance

Cover sparse configuration, mandatory model 1 ID, omitted/blank/whitespace-only
names, name-only slots, legacy values, deletion and restoration, direct physical
calls and Live isolation. Verify reads and
unrelated saves do not change stored values; explicitly selecting the displayed
fallback 1 must save it. Check edits made while saving are not lost. Cover both
learning engines, preview, follow-up, credit estimate, imports, gateway and
physical-rate identity. Verify old variables/DB keys no longer affect catalogs.

Settings-save analytics remain best-effort and fire once after an editable save
succeeds. Record effective indexes and fallback booleans only; omit text-model
selection for Live. Never send raw IDs, configured names or provider data,
including model IDs displayed as fallback labels. Update producers, consumers
and compatibility documentation together; historical tier
payloads retain their original meaning.

## Idempotence and Recovery

No data cleanup is required. Configuration removal and restoration affect future
invocations, without rewriting stored selections or historical usage. Configure
slot 1 before launching the new build. An invalid slot 1 is an explicit error.
Do not roll back to code that interprets saved numeric choices as physical IDs.

## Interfaces and Dependencies

Keep GET /api/llm/model-tier-list as the course option endpoint; options contain
index, display_name, available, is_default and credit_multiplier. Older teacher
text catalogs return numeric values in their existing model field. Course detail
returns effective model/ask_model and model_fallback/ask_model_fallback booleans.
Raw saved values remain in persisted fields and export files. Teacher model
controls use numeric option values and show the configured name, falling back
to the configured model ID when the name is absent or blank.

Internal physical catalogs deduplicate identical bindings by the lowest slot
number, while course choices retain every slot. Existing gateway client
allowlisting, provider wrappers and physical-rate accounting remain in place.
The gateway default alias preserves an explicit DEFAULT_LLM_MODEL; when absent
or blank, it uses model 1's physical binding. An unavailable or unrated default
does not select another physical model.

## Deployment Runbook

1. Set a provider credential plus LLM_MODEL_1_ID; configure optional IDs through
   9. Names are optional for all numbers; missing or blank names display the
   configured model IDs. Remove obsolete tier/allowed variables.
2. No database migration or course-data cleanup is needed for this change.
3. Deploy matching API/workers and web. Verify a legacy course falls back to 1,
   sparse configured choices work, and unrelated saves preserve old selections.
4. Inspect invocation metadata for selected/effective/physical identity and
   verify usage is billed to the actual invoked model.
