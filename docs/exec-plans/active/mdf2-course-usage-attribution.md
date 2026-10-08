# Attribute MarkdownFlow model usage to its course and lesson

## Purpose / Big Picture

Make normal 2.0 classroom model requests discoverable in per-course/per-lesson
accounting and resolvable to the existing course owner. Teaching, summaries and
memory admission must carry the same authorized course/lesson identity while
preserving learner identity, provider counters and preview/read/listen boundaries.
This fixes a prerequisite discovered during complete-course cost acceptance.

## Progress

- [x] 2026-10-08 23:29 CST: Reproduced on deployed sim with a new dedicated
  internal learner. One lesson completed in two HTTP runs without teaching issues;
  all four LLM usage rows lacked course and lesson identities.
- [x] 2026-10-08 23:30 CST: Traced the omission to all three GatewayModel factories
  in lesson_entry.py. The shared recorder and course-ownership path already support
  the required context; normal 1.0 requests populate it.
- [x] 2026-10-08 23:31 CST: Entry regressions failed in all twelve combinations of
  scene, read/listen mode and termination. Four provider-stub integration tests
  failed on actual persisted empty course identities.
- [x] 2026-10-08 23:32 CST: Bound one immutable UsageContext to all three factories.
  Focused real-gateway/entry tests: 288 passed.
- [x] 2026-10-08 23:34 CST: Learning/profile/metering/settlement regressions:
  3,149 passed, one expected skip and four subtests passed. Focused entry/provider
  tests: 288 passed. Developer tools and repository gates passed.
- [ ] 2026-10-08 23:34 CST: Open one focused PR and deploy sim.
- [ ] 2026-10-08 23:33 CST: Deploy sim and verify HTTP classroom usage rows and
  existing billing ownership, plus read/listen and preview boundaries.
- [ ] 2026-10-08 23:33 CST: Audit reviews, inline comments and issue comments; reply
  to each independent AI opinion in its original discussion.
- [ ] 2026-10-08 23:33 CST: Await manual main merge and verify production selection.

## Surprises & Discoveries

PR #3054's numeric cache diagnostics were correct, but real classroom gateway calls
still used the default learner-only UsageContext. The baseline recorded four
requests (35,620 input, 34,688 cached input and 567 output tokens) with request and
trace IDs, yet no course or lesson. Those counters cannot establish an accounted
lesson cost: regular classroom ownership resolution needs the course identity.
The internal acceptance course contains 21 lessons; one completed lesson is not
full-course or long-term fee acceptance.

## Decision Log

- Reuse UsageContext, shared chat metering and existing course ownership resolution.
  Do not introduce a second ledger, settlement rules or price computation.
- Supply the same context to teaching, summary and admission factories. Preserve
  each generation name and model-selection metadata.
- Preserve preview as preview and derive read/listen from the authenticated host
  request. Do not claim progress/block identities before the host creates them.
- Scope the repair to new classroom requests. No historical usage backfill,
  production configuration switch or database migration is included.

## Outcomes & Retrospective

Local focused acceptance passes. Full deployed acceptance and final live checks
remain pending. Complete-course cache/cost and natural teaching validation remain
separate follow-up acceptance; this repair alone does not complete milestone 4.

## Context and Orientation

`src/api/flaskr/service/learn/agent/lesson_entry.py` constructs the teaching model,
summary factory model and admission model. GatewayModel forwards chat kwargs to
shared `chat_llm`; `UsageContext` and raw persistence live in `service/metering`.
Billing ownership is resolved in `service/billing/ownership.py`. The canonical
interpretation of cache diagnostics is [cache usage](../../references/markdownflow-cache-usage.md).

## Plan of Work

Reproduce missing ownership, bind the already authorized classroom identity at the
entry, verify actual normalized persisted records for all three request kinds,
and repeat HTTP read/listen/private ledger acceptance on deployed sim.

## Concrete Steps

1. Run entry contracts for preview/learning, read/listen and all termination paths.
2. Stub only the provider to invoke every entry-built adapter and the actual shared
   recorder; assert course/lesson/learner, scene, mode, request and token fields.
3. Run learning/profile/metering and settlement regressions, plus all repository gates.
4. Open a focused PR, sync sim, verify runtime fingerprints and real HTTP rows.
5. Audit all AI review surfaces and reply before requesting manual merge.

## Validation and Acceptance

Twelve entry contracts and four real gateway persistence cases must pass. All three
kinds retain distinct generation names, cache values and the authorized course and
lesson. Existing ownership resolves the course owner for each row. Preview never
becomes production usage. Actual sim HTTP rows must show the same attribution,
without changing natural teaching behavior or producing duplicate usage rows.

## Idempotence and Recovery

Use dedicated learners and the internal sim acceptance course only. Sim shares the
China production database. Private reports and credentials remain uncommitted;
query usage and settlement read-only. Do not replay historical settlement or alter
real learner state. Production remains 1.0 until separately authorized.

## Interfaces and Dependencies

No new interface, dependency, schema, environment variable or frontend behavior.
Only existing GatewayModel chat kwargs and immutable UsageContext are used.
