---
title: Keep course temperatures internal
status: completed
owner_surface: shared
last_reviewed: 2026-10-08
---

# Keep course temperatures internal

## Purpose / Big Picture

Remove course temperature settings from user interfaces and public authoring
APIs while preserving stored generation behavior. The durable contract is
[Internal Course Temperature Settings](../../product-specs/course-temperature-settings.md).

## Progress

- [x] 2026-10-08 08:49 UTC: Inspect UI, detail DTO/Swagger, save, preview,
      backup, copy, publication, learner, and independent gateway boundaries.
- [x] 2026-10-08 08:49 UTC: Confirm the user's backup-format exception so
      export/import preserves non-default values across deployments.
- [x] 2026-10-08 08:49 UTC: Remove frontend temperature ownership and public
      detail fields; make save/preview requests use server-owned configuration.
- [x] 2026-10-08 08:56 UTC: Verify schema/response omissions and stored values;
      authoring/affected learning tests: 1299 passed, 3 skipped. Frontend: 80 passed.
- [x] 2026-10-08 08:56 UTC: Developer tools and full repository gates passed;
      prepare the follow-up commit and existing PR #3045 update.

## Surprises & Discoveries

Swagger registration reads DTO annotations, so excluding JSON fields alone
does not remove the documented response contract. Historical backup files need
their temperature fields to retain generation behavior on portable import.

## Decision Log

- 2026-10-08: Remove course temperature DTO fields and browser state together.
  Ignore legacy request fields rather than reject otherwise valid client saves.
- 2026-10-08: Preview reads the stored draft follow-up value, retaining zero and
  precision; existing runtime defaults remain server-owned.
- 2026-10-08: User explicitly approved preserving backup format compatibility.
  The unrelated OpenAI-compatible gateway remains within its existing protocol.

## Outcomes & Retrospective

Public course configuration is server-owned, and saved runtime values remain
intact. All targeted backend/frontend regressions and full repository gates
passed. Full frontend type-check reproduces the same two existing errors in
`src/app/admin/operations/users/[user_bid]/page.test.tsx` as the unchanged HEAD
baseline. The earlier UI-only commit is already in PR #3045; this verified
extension is ready for its follow-up commit. Merge and deployment remain outside
this implementation plan.

## Context and Orientation

`shifu/dtos.py` and `shifu_draft_funcs.py` produce detail responses;
`shifu/route.py` owns save and follow-up preview inputs. `ShifuSetting.tsx`
and the shared `types/shifu.ts` own frontend consumption. Database columns,
internal service arguments, import/export, copy, and publish retain ownership
of the persisted values.

## Plan of Work

Remove response/schema fields and their producers, retire request parsing,
read preview values from the course, and remove the frontend copy. Test the
public boundaries and persisted values without changing the runtime engine.

## Concrete Steps

Run focused Jest settings tests and pytest shifu tests. Verify the learning
model-selection and publication tests. Run developer-tool checks, repository
harness, architecture boundaries, and the full lefthook pre-commit gate.

## Validation and Acceptance

Course settings and public authoring schemas/responses contain no temperature
fields. Saves cannot override stored temperatures, including zero/non-default
values; previews use them without rounding. Backup portability, internal
copy/publication, learning, and existing provider behavior remain intact.

## Idempotence and Recovery

The change does not migrate or rewrite stored temperature values. Repeated
saves preserve them. Reverting the implementation restores public exposure
without needing a database recovery operation.

## Interfaces and Dependencies

The detail DTO and save/preview public contracts are coordinated across
backend, frontend, documentation, and regression tests. No new dependency,
provider wrapper, migration, or analytics contract is introduced.
