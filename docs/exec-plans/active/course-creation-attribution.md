# Persist AI-assisted course creation attribution

## Purpose / Big Picture

AI Shifu must be able to distinguish users registered through the Lobster
authorization handoff and courses created through the Lobster course-creator
Skill. The attribution must be recorded in the correctness-oriented database
rather than inferred later from best-effort browser or CLI analytics. This
enables reliable registration, creation, publication, order, and learning
conversion analysis.

## Progress

- [x] 2026-09-11 16:10 CST: Confirmed that the current Skill create/import
  requests send no attribution fields and that AI Shifu has no receiving
  persistence path.
- [x] 2026-09-11 17:35 CST: Added the immutable backend attribution contract,
  model, migration, and focused regression tests.
- [x] 2026-09-11 17:35 CST: Added the matching Skill request producer and tests
  in the separate Skills repository.
- [x] 2026-09-11 17:35 CST: Ran focused and repository-required verification.
- [x] 2026-09-11 17:45 CST: Prepared one focused commit and pull request per
  repository.
- [x] 2026-09-11 20:40 CST: Reworked registration attribution around the exact
  browser handoff and explicit new-user result; made course handoffs safe for
  retries and concurrent Skill commands.

## Surprises & Discoveries

- The Skill already emits fail-open Umami events such as `cli_import`, but the
  event deliberately contains neither course identifiers nor command results.
  It is useful for adoption measurement but cannot be the course-attribution
  source of truth.
- GitHub and Gitee Skills `main` currently resolve to the same commit,
  `cf9cf1d0de76f626a3b24c2e5cfa1ab6f51fdc20`.
- Temporary guest accounts retain their original `created_at` when promoted,
  so account timestamps cannot reliably determine whether the browser handoff
  caused registration.

## Decision Log

- Decision: Store course attribution in a one-row-per-course table rather than on
  versioned draft rows. Rationale: draft edits create revisions, while course
  origin is immutable course-level metadata that must survive publication and
  ownership transfer without copying across every revision.
- Decision: Use one structured optional create payload named
  `creation_attribution`, containing `creation_source`, `source_product`, and
  `handoff_id`. Rationale: existing clients remain compatible and the three
  values are accepted or rejected atomically.
- Decision: Initially allow only `ai_assistant` plus `lobster`, with a UUID
  handoff identifier. Rationale: a narrow allowlist prevents uncontrolled
  analytics dimensions and leaves deliberate extension points.
- Decision: Treat the record as immutable. Rationale: origin is a creation-time
  fact and must not be rewritten by subsequent course edits.
- Decision: Carry the authorization handoff UUID into the first new course
  created after authorization. Rationale: this joins a newly registered user
  to their first Skill-created course without collecting contact details.
- Decision: Pass the device `user_code` through the browser login request and
  persist registration attribution only when the auth provider explicitly
  reports a new registration. Rationale: this identifies the exact handoff,
  handles guest promotion, and does not depend on the CLI polling afterward.
- Decision: Reserve a saved course handoff atomically and only when its saved
  token matches the token used for the request. Rationale: explicit-token and
  concurrent CLI invocations must not consume or duplicate another account's
  registration handoff.

## Outcomes & Retrospective

The backend now stores immutable Lobster registration and course-creation
facts, and the Skill supplies one cross-system handoff UUID without changing
existing-user or existing-course attribution. Focused backend tests passed
(430 tests), Skills validation passed (3 skills and 229 tests), Ruff passed,
and the repository harness, architecture-boundary checks, and full pre-commit
gate passed. The implementation is ready for review in one focused pull
request per repository.

## Context and Orientation

The authenticated create endpoint is `PUT /api/shifu/shifus` in
`src/api/flaskr/service/shifu/route.py`. Course creation and its transaction
are owned by `create_shifu_draft` in
`src/api/flaskr/service/shifu/shifu_draft_funcs.py`. Course models live in
`src/api/flaskr/service/shifu/models.py`; schema revisions live under
`src/api/migrations/versions/`.

The producer is `skills/ai-shifu-course-creator/scripts/shifu-cli.py` in the
Skills repository. Both `create` and `import --new` call the same AI Shifu
course creation endpoint.

## Plan of Work

Define and validate the structured attribution at the service boundary. Add an
immutable database row in the same transaction as course creation. Add the
schema migration and tests for absent attribution, valid Lobster attribution,
invalid enums/identifiers, and rollback behavior. Then update both Skill paths
that create courses to generate a UUID handoff and submit the agreed payload,
with request-contract tests proving existing-course imports do not rewrite
origin.

## Concrete Steps

1. Add the backend registration/course models and migration.
2. Add a narrow parser/value object and wire it through the create route and
   creation transaction.
3. Add focused backend tests and run the Shifu test subset.
4. Update the Skills CLI producer and its unit tests/documented deployment
   contract.
5. Run each repository's required checks, commit with compliant messages,
   push both branches, and open both PRs with their dependency documented.

## Validation and Acceptance

- Existing create requests without `creation_attribution` behave unchanged and
  create no attribution row.
- A valid Lobster request creates exactly one attribution row with the course
  BID, teacher BID, stable enum values, UUID handoff, and UTC creation time.
- Malformed or unsupported attribution is rejected before course creation.
- A failed course transaction leaves no attribution row.
- Skill `create` and `import --new` send valid attribution; importing into an
  existing course does not send or mutate it.
- A browser authorization started by the Skill attributes a user only when the
  linked login operation explicitly creates or promotes that user; the same
  handoff UUID is reserved for the first subsequent new course and restored if
  that request fails.

## Idempotence and Recovery

The migration is a normal Alembic upgrade/downgrade and must run before the
backend code is deployed. Attribution insertion is part of the course creation
transaction, so rollback removes both records. The table has uniqueness
constraints on course BID and handoff ID; retrying an identical course handoff
returns its original course, while conflicting ownership is rejected.

## Interfaces and Dependencies

The cross-repository course request contract is:

```json
{
  "creation_attribution": {
    "creation_source": "ai_assistant",
    "source_product": "lobster",
    "handoff_id": "<canonical UUID>"
  }
}
```

The device authorization endpoint accepts the same object under
`registration_attribution`. The Skill stores the generated handoff UUID in its
owner-only credentials file only until the first new course succeeds.

The Skills PR depends on the AI Shifu backend accepting this optional field,
but older backends currently ignore unknown JSON members, so rollout remains
backward compatible. Umami remains best-effort and is not used as the source
of truth.
