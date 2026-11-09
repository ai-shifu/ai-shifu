# Harness Gardening Document Review

## Purpose / Big Picture

Restore the scheduled documentation freshness check by reviewing its 23 flagged
design documents and product specifications against the current `main` checkout.

## Progress

- [x] 2026-11-10 06:16 CST: Reproduced 23 stale or undated documents at `9ba3bdeb0`.
- [x] 2026-11-10 06:21 CST: Checked all 23 documents against implementation,
  existing tests, or the relevant removal commit.
- [x] 2026-11-10 06:22 CST: Corrected drift and confirmed zero findings from
  the gardening scan.
- [x] 2026-11-10 06:23 CST: Regenerated indexes and passed the repository
  harness and gardening checks. The related suites passed 805 backend and
  195 frontend tests.

## Surprises & Discoveries

The current checkout has no retired-term hits or stale boundary entries.

## Decision Log

- Use the UTC review date in document metadata, matching the repository
  validators. The progress timestamps above use China Standard Time.
- Keep this review in a dedicated documentation PR. Preserve historical design
  context, identify unshipped proposals, and leave the freshness rule intact.

## Outcomes & Retrospective

The freshness scan now has zero stale documents, retired terms, or stale
baseline entries. The review refreshed 22 current records and moved the
retired MarkdownFlow element backfill to history. The remaining OAuth
sequencing work and proposed payment-attribution reporting are labeled as
such. The broad billing design still distinguishes its historical proposals
from the current capability registry.

### Evidence by area

| Reviewed documents | Repository evidence |
| --- | --- |
| Agent-first harness, fresh MySQL migration | Static Checks and Runtime Harness workflows, the repository knowledge generator, Alembic revision `6b603528dac8`, and `test_fresh_mysql_upgrade.py` |
| Mobile 404, language analytics, element backfill | Course layout and API suites, `LanguageSelect` producer and tests, and removal commit `275311933` |
| Credit notification design and product scope, notification analytics | `billing/credit_notifications.py`, operator template/rule tracking and page tests, and the active email delivery plan |
| Billing design, preorder, purchase SMS, native payments, referrals | Billing capability registry and models, preorder/renewal and paid-order side effects, native adapters and callback routing, referral runtime and campaign tests |
| Operator request optimization, course detail, users, follow-ups, creator transfer | `shifu/admin_operations` services and corresponding Cook Web pages, `test_admin_courses.py`, and `test_admin_course_detail.py` |
| Operator orders, promotions, role, credit reads and grants | Order and promo services, role bootstrap, user credit summary and write services, operator page tests, and validity/idempotency tests |

This was a source and test review. Deployment-only checks such as SMTP
acceptance and the fresh-MySQL replay require their own environments.

## Context and Orientation

`scripts/run_harness_gardening.py` checks review dates in `docs/design-docs/`
and `docs/product-specs/`. The initial report is available as the artifact of
[the failing scheduled run](https://github.com/ai-shifu/ai-shifu/actions/runs/42618730222).

## Plan of Work

Review the flagged documents in three groups: harness and learning, billing and
payments, and operator tools. Cross-check source, tests, and newer canonical
documentation. Update each document only after reviewing its claims and scope.

## Concrete Steps

1. Run the gardening scan and capture the flagged paths.
2. Check feature status, references, and behavior against repository evidence.
3. Record the review dates and regenerate the knowledge index.
4. Verify the gardening scan and repository harness. Record remote checks on
   the pull request.

## Validation and Acceptance

`python scripts/run_harness_gardening.py --fail-on-drift` exits zero with no
stale docs, retired terms, or stale baseline entries.
`python scripts/check_repo_harness.py` passes with regenerated indexes.

## Idempotence and Recovery

Both generators can be rerun. Keep the source documentation and generated
indexes together in the PR.

## Interfaces and Dependencies

The review uses the current repository, existing tests, and generated knowledge
indexes. No application or workflow changes are required.
