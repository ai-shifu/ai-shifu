# Course Slug Primary Links

## Purpose / Big Picture

Give every course one globally unique, human-readable current slug and use
`/c/<slug>` as its public learner link. Existing `/c/<shifu_bid>` links remain
valid and converge to the current slug URL after the course is resolved. The
storage model is ready to retain future slug versions as permanent aliases,
although v1 does not expose editing or regeneration. Internal orders,
permissions, progress, metering, authoring, and operations continue to use
`shifu_bid`.

## Progress

- [x] 2026-07-12 08:00 CST: Inspected current course creation, versioned draft
  and publish models, learner routes, public URL builders, payment return, and
  frontend bootstrap behavior.
- [x] 2026-07-12 09:10 CST: Added slug persistence, generation, migration, and
  resumable backfill tooling.
- [x] 2026-07-12 09:10 CST: Integrated slug creation with every new-course path
  while preserving slug identity on updates.
- [x] 2026-07-12 09:10 CST: Resolved slug or legacy BID at the learner boundary
  before permissions and business logic execute.
- [x] 2026-07-12 09:15 CST: Bootstrapped the learner frontend through the public
  identifier, retained canonical BID state, and canonicalized links.
- [x] 2026-07-12 09:26 CST: Added lifecycle, collision, transaction, route,
  canonical URL, retry, and backfill tests; passed full backend, focused
  frontend, formatting, lint, type, architecture, and repository checks.
- [x] 2026-07-12 09:53 CST: Prepared slug storage for future changes with
  versioned current and historical records while retaining v1's no-edit
  behavior; passed focused and full backend verification.
- [ ] 2026-07-12 09:26 CST: Run the fresh-MySQL migration smoke with an external
  MySQL DSN; this checkout does not provide `TEST_SQLALCHEMY_DATABASE_URI`.
- [ ] 2026-07-12 09:27 CST: Run browser E2E against the default dev stack;
  Playwright launches outside the sandbox, but no server is running on port
  8080 and Docker is unavailable in this environment.

## Surprises & Discoveries

- `DraftShifu` and `PublishedShifu` are append-only version tables, so a
  globally unique slug cannot live on either table.
- LLM usage persistence commits the scoped SQLAlchemy session. Slug generation
  must therefore finish before any course mutation is staged.
- The learner frontend currently propagates the route segment into API paths,
  tracking, payment, and local-storage keys. Canonical BID resolution must
  complete before learner children start.
- Flask-SQLAlchemy scopes sessions to the active app context. Pushing another
  context inside slug allocation moved the binding to a different session and
  would roll it back when that context exited. Allocation now fails fast unless
  it shares the caller's app context and transaction.
- MySQL `REPEATABLE READ` can retain a pre-conflict snapshot after a unique-key
  wait. The same-BID race therefore uses a `FOR UPDATE` current read after the
  savepoint rolls back.
- Python 3.11 SQLite legacy transaction mode can make a first savepoint act as
  the outer transaction. Tests explicitly begin the outer transaction so a
  rollback exercises production-like semantics.
- The legacy query parser included the URL fragment in the final query value.
  Canonicalization exposed this for `preview=true#fragment`; query parsing now
  strips the fragment first.

## Decision Log

- Store every slug version in `shifu_course_slugs`. Keep `slug` globally unique
  so historical values stay permanently reserved; enforce one current record
  per BID with a nullable current marker and a `(shifu_bid, version)` sequence.
- Generate one current slug per course in v1. Renaming, publishing,
  transferring, archiving, and updating an import do not regenerate it, and no
  edit API is exposed yet. A future rotation will retire the current record and
  add a new version without invalidating the old slug.
- Normal slugs contain 3-6 English semantic words, are 18-48 characters long,
  and use lowercase ASCII kebab-case. A uniqueness suffix does not count as a
  semantic word but must remain inside the 48-character limit.
- Retry one invalid model response. If generation still fails, create a stable
  technical fallback and record `generation_source=fallback` so course
  creation is not blocked by model availability.
- Keep the public identifier namespace global. Existing BIDs win during
  resolution and future slug/BID allocation rejects cross-namespace clashes.
- Keep authoring and operations routes BID-only. Only learner/public links gain
  slug aliases.
- Canonicalization uses browser replace semantics and preserves all query
  parameters, `lessonid`, and fragments. No SEO canonical metadata is added in
  this version.
- Cross-service consumers use `flaskr.service.shifu.api` as the stable public
  course-identity boundary; slug allocation remains owned by the shifu service.
- Backfill uses database keyset pages. A legacy course with no usable title
  receives the deterministic technical fallback directly so a completed run
  can still reach `missing=0`.
- A transient learner bootstrap error keeps downstream requests gated and
  presents an i18n-backed retry action instead of leaving a permanent blank
  page.

## Outcomes & Retrospective

The implementation is complete in the working tree. New courses receive a
current slug before any course row is staged; every learner route resolves a
current or historical slug, or a legacy BID, to the canonical BID; all public
URL producers prefer the current slug; and the learner frontend does not mount
course consumers until canonical identity is available. The backfill is
idempotent, keyset-paged, resumable, and reports remaining coverage.

Verification completed locally:

- backend full suite: 2056 passed, 6 skipped;
- focused slug history and constraint suite: 39 passed;
- expanded shifu/learn/payment/migration suite: 661 passed, 6 skipped;
- frontend focused slug suites: 33 passed;
- frontend type-check, lint, and full Prettier check;
- Ruff check/format, repository harness, architecture boundaries, shared i18n,
  and the full lefthook pre-commit gate.

Two environment-dependent rollout checks remain. The fresh-MySQL test now
asserts the version/history columns, three unique constraints, and state checks
but needs an external DSN.
Playwright launches when run outside the sandbox, but the smoke suite needs the
default application stack at `http://localhost:8080`; Docker is not installed
in this environment.

## Context and Orientation

Backend course lifecycle code lives under `src/api/flaskr/service/shifu/`;
learner APIs live under `src/api/flaskr/service/learn/`; public payment details
live under `src/api/flaskr/service/order/`. The learner application route is
`src/cook-web/src/app/c/[[...id]]/`, with shared course state and API adapters
under `src/cook-web/src/c-store/` and `src/cook-web/src/c-api/`.

## Plan of Work

1. Add an identity-level slug binding model, Alembic migration, strict local
   validator/allocator, LLM prompt, and non-billable traced generator.
2. Call generation before mutations in manual creation, copy, new import,
   explicit-BID import, demo creation, and defensive publish paths. Preserve
   bindings on all update paths.
3. Add an idempotent CLI backfill that prefers the current published title,
   falls back to the current draft title, commits per course, and reports
   coverage and generation outcomes.
4. Resolve learner path identifiers to canonical BIDs before context,
   permissions, or service calls. Extend course and payment responses with
   canonical slug/link data while retaining existing fields.
5. Resolve the route identifier before learner children render, keep BID in
   state and downstream requests, replace legacy paths with the slug, and use
   canonical links for publishing, previews, QR sharing, and payment return.

## Concrete Steps

- Create `shifu_course_slugs` with versioned current/history records, permanent
  slug reservation, one-current-per-BID constraints, and UTC application-side
  timestamps; update the migration-head test.
- Add `course_slug.md` and a service helper that validates 3-6 words and the
  18-48 character envelope, retries invalid output once, allocates collisions
  atomically, and emits a deterministic fallback.
- Register `flask console backfill_course_slugs` with dry-run, batch size, and
  single-course options.
- Extend Shifu and learner DTOs with `slug` and canonical URL/path fields; add
  `course_url` to payment detail responses.
- Update learner initialization and URL helpers while keeping `/c` custom
  domain behavior and all BID-based internal routes intact.

## Validation and Acceptance

- Unit-test 3/6-word boundaries, 17/18/48/49-character boundaries, mixed
  language and emoji titles, prompt-like titles, invalid JSON, retry, fallback,
  collision truncation, and namespace conflicts.
- Test manual creation, rename stability, copy, import create/update, demo,
  publish, preview, and idempotent backfill.
- Parameterize learner route coverage across course info, outline, run,
  records, feedback, generated content, and TTS for both slug and BID.
- Test frontend bootstrap gating, canonical BID state, parameter-preserving
  replacement, publish/copy/QR/payment URLs, and unchanged author/admin BID
  navigation.
- Run migration single-head and optional fresh-MySQL smoke, targeted and full
  backend pytest, focused frontend Jest, type-check, lint, architecture checks,
  repository harness checks, and browser E2E.

## Idempotence and Recovery

Slug allocation first returns the current record for the same `shifu_bid`.
The backfill skips courses with a current slug and commits each successful
course separately, so interruption or provider failure is recoverable by
rerunning it. Historical slugs and legacy BID resolution remain available
indefinitely. The migration is additive; after slug links are exposed,
recovery should roll forward rather than drop the slug table.

## Interfaces and Dependencies

- Public learner route identifiers accept either slug or legacy BID.
- Course DTOs add `slug`; learner course info adds canonical path data; payment
  details add `course_url` while retaining `course_id`.
- Slug generation reuses `DEFAULT_LLM_MODEL`, the shared LiteLLM wrapper,
  Langfuse, and non-billable metering. No new runtime dependency is introduced.
