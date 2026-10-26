# Atomic Sibling Reorder

## Purpose / Big Picture

The Course Creator CLI must reorder one sibling group without resubmitting an
outdated copy of other groups. The backend owns the locked read/merge/write.
The durable API and rollout contract is in
[Atomic Sibling Reorder](../../product-specs/atomic-sibling-reorder.md).

## Progress

- [x] 2026-09-28 CST: Inspect route, outline lock, version reads, history writer,
  unit-of-work rules, and the companion CLI review.
- [x] 2026-09-28 CST: Implement the optional sibling-order mode with current reads.
- [x] 2026-09-28 CST: Verify API, preservation, rollback, and MySQL repeatable-read cases.
- [x] 2026-09-28 CST: Run shifu tests and repository gates; complete independent
  implementation and acceptance review before archiving this code-change plan.
- [x] 2026-09-28 CST: Narrow the current-read lock footprint using the existing
  composite index and verify that historical revisions remain independently writable.
- [x] 2026-09-28 CST: Reject malformed affected descendant paths and final position
  collisions; verify row and history rollback, including previously rebased paths.

## Surprises & Discoveries

- A course lock does not refresh a transaction's earlier MySQL read snapshot.
  A normal MAX subquery or history read can still return the prior tree.
- The display-tree builder keys nodes by position and repairs orphans. The
  mutation instead needs a complete tree keyed by BID and explicit parent links.
- Locking every outline revision makes contention grow with revision history.
  A direct locking aggregate over the complete composite-index prefix can find
  current IDs without locking every historical row; an outer lock around a
  snapshot-reading aggregate subquery does not provide the same correctness.

## Decision Log

- Add mutually exclusive `order` and legacy `outlines` modes to the existing
  PATCH route. Do not introduce a new endpoint or change the legacy payload.
- After the course lock, select current outline IDs with a direct `MAX(id)`
  locking read grouped by `(shifu_bid, outline_item_bid)`, using the existing
  `ix_shifu_draft_outline_items_shifu_outline_id` index. Lock and refresh the
  selected rows, then exclude tombstones. This replaces the initial all-revision
  locking scan. Lock and refresh history too.
- Keep the aggregate in the locking SELECT itself, without a nested snapshot
  query. MySQL's leftmost-prefix GROUP BY optimization can skip older revisions;
  an optimizer choosing a wider scan retains current-read correctness but may
  reduce the contention benefit. No migration or dependency is needed.
- Keep scope to sibling-order merges. Other structural writers and the existing
  full-tree API retain their current behavior and are not claimed race-free.
- Reject affected descendants whose stored positions do not contain their
  original parent prefix plus a canonical positive ordinal. Do not infer or
  repair mixed old/new prefixes. Validate final positions against the current
  in-memory rows before saving history, and roll back on any collision.
- Deploy the backend capability before the companion CLI update in skills PR
  170. The CLI sends only `order`; older backends reject it without a full-tree
  fallback.

## Outcomes & Retrospective

The API now merges one sibling order into current locked state and preserves the
complete history. The legacy full-tree mode is unchanged. After review fixes,
the sibling service tests passed (36), the shifu suite passed (1157), and three
opt-in MySQL tests passed against separate connections under REPEATABLE READ.
The default suite skips those three tests unless explicitly enabled. The new
history-lock regression failed with a lock timeout before the optimization and
passed afterward. All 20 repository pre-commit
checks passed, including the repository, architecture, and unit-of-work gates.
Independent review accepted both the implementation and the real-database
evidence. Deployment is outside this code-change plan; the durable specification
records the backend-before-CLI rollout prerequisite.

## Context and Orientation

`src/api/flaskr/service/shifu/route.py` owns request selection and permissions.
`shifu_outline_funcs.py` owns validation and structure persistence.
`shifu_history_manager.py` preserves root metadata and legacy block children.
The Course Creator CLI lives in the separate `ai-shifu/skills` repository.

## Plan of Work

Add the sibling mode, reuse the existing course lock and persistence loop, and
make current history reads opt-in. Cover both routes and the locked data merge.

## Concrete Steps

1. Add the route/schema contract and sibling validation.
2. Merge a complete current tree under the existing course lock.
3. Preserve full history and prove rollback on a late failure.
4. Run SQLite service tests and an isolated local MySQL old-snapshot scenario.
5. Regenerate knowledge indexes and run devtools, Ruff, and all lefthook checks.

The reproducible local database check runs from `src/api`:

```bash
RUN_LOCAL_MYSQL_REORDER_TESTS=1 \
MYSQL_REORDER_TEST_ADMIN_URI=mysql+pymysql://root@127.0.0.1:3306 \
python -m pytest tests/service/shifu/test_reorder_outline_mysql.py -q
```

It rejects non-loopback URLs and preselected databases. Each test creates and
cleans up its own random schema. It first proves that an earlier ordinary read
cannot see another connection's newly committed row, then verifies the real
service preserves that row and the complete current history. A second case
checks stale ORM identity entries after another connection updates the same IDs.
A third case creates 200 versions of one outline, verifies that another
connection can update an interior historical row while the loader holds its
locks, and confirms that the current row still rejects a competing lock.

The local database evidence uses MySQL 26.7.0 (Homebrew). The deployment target
is MySQL 8.0, whose [GROUP BY optimization documentation](https://dev.mysql.com/doc/refman/8.0/en/group-by-optimization.html)
supports this index shape. MySQL 8.0 was not available locally; lock-footprint
improvement on that target remains subject to its execution plan. The regression
checks concurrent access rather than asserting a version-specific lock count.

## Validation and Acceptance

Reordering two different sibling groups preserves both changes, content,
children, root history metadata, and legacy block references. Invalid or partial
groups and unauthorized calls write nothing. A transaction that began reading
before another writer committed must retain that writer's changes. The legacy
full-tree request remains supported.

## Idempotence and Recovery

Repeating the same sibling order preserves structure. All cloned rows and the
full-tree history snapshot commit together or roll back together. MySQL checks
use only a new random local schema and remove that schema afterward.

## Interfaces and Dependencies

No database migration or dependency is introduced. The shared contract is the
new request key on the existing route; consumers must not combine both keys.
