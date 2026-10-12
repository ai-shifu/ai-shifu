# Lesson Content Revision Comparison Performance

Recorded on 2026-10-12 for integer revision comparison. This report replaces
the previous full-text comparison benchmark: the implementation no longer extracts or
compares stored lesson text.

## Result

The helper compares the current revision supplied by the caller with the
session's saved `content_revision`. It selects only `outline_item_bid`,
`content_revision`, `turn`, `finished`, and `schema_version` in one batch. Schema
eligibility does not discard scalar learning progress. It does not select
`session_data`, execute JSON functions, or join lesson-body tables. Existing
structure JSON is read by the caller; that work is outside this microbenchmark.

On local MySQL, comparing 100 sessions with 1 MiB histories took **4.61 ms p50**
and **5.17 ms sample p95**, returned 1,525 bytes of values, and used about 103 KB
of peak traced Python allocation. Increasing history size from 100 KiB to
1 MiB did not increase returned data or materially change MySQL latency in
this run. The query still performs indexed row reads; this is not a claim of
zero database I/O.

## Reproduction

From `src/api`, using the backend Python environment:

```bash
python scripts/benchmark_lesson_content_updates.py --mysql-env .env --iterations 7
```

Omit `--mysql-env` for SQLite alone. The script requires a local MySQL host,
creates a uniquely named disposable database containing only the session
table, and removes that database afterward. SQLite uses a temporary file. It
does not migrate or modify the configured development database.

Each scenario has 10 or 100 active sessions, plus 1,000 sessions belonging to
another user and 1,000 retired sessions for the target learner. Active histories
are 100 KiB or 1 MiB. The fixture mixes matching revisions, changed revisions,
legacy null baselines, and unknown zero baselines; it verifies expected update
flags and excludes unrelated or retired rows. SQLite fixture statistics are
refreshed with `ANALYZE` before measurement.

## Measurements

Two warmups precede seven timed calls. Every call issued **one SELECT** and
returned exactly the requested 10 or 100 rows. Captured SQL was checked for
absence of `session_data`, JSON functions, and lesson-body tables. Allocation
tracing ran separately from the latency samples.

| Database | Sessions | History KiB | p50 ms | Sample p95 ms | Returned value bytes | Python peak bytes |
| --- | --- | --- | --- | --- | --- | --- |
| MySQL 26.7.0 | 10 | 100 | 0.940 | 1.101 | 154 | 27,094 |
| MySQL 26.7.0 | 100 | 100 | 4.758 | 5.020 | 1,525 | 102,985 |
| MySQL 26.7.0 | 10 | 1,024 | 0.874 | 1.138 | 154 | 26,974 |
| MySQL 26.7.0 | 100 | 1,024 | 4.608 | 5.165 | 1,525 | 102,985 |
| SQLite 3.54.0 | 10 | 100 | 0.298 | 0.389 | 154 | 21,542 |
| SQLite 3.54.0 | 100 | 100 | 2.089 | 2.309 | 1,525 | 75,477 |
| SQLite 3.54.0 | 10 | 1,024 | 1.566 | 2.027 | 154 | 20,774 |
| SQLite 3.54.0 | 100 | 1,024 | 14.656 | 15.250 | 1,525 | 75,477 |

`EXPLAIN` confirmed the existing unique `uq_learn_agent_sessions_active` index
on every final scenario in both engines. MySQL selected it without an index
hint; no new index or database-specific JSON implementation is needed. Plan
row counts are estimates, not measurements of physical reads.

The larger SQLite rows still affected latency despite the small projection and
correct index. The benchmark does not attribute that difference to a specific
storage mechanism; it demonstrates why avoiding a large column does not prove
that all row-storage costs disappear.

## Legacy authoring initialization

Missing structure revisions are initialized only during authoring or publication,
not learner reads. Recovery now batches at most 20 lessons with 20 historical
versions each per query, selecting only source ID, version ID and content. Each
lesson stops at its first different normalized content, with the existing
1,000-active-version and exact physical-row bounds preserved. A query returns at
most 400 historical content rows; this is a row bound, not a fixed byte limit.

The 10/100-lesson regressions span two version pages. Authoring uses 3/15 outline
SELECTs, including exact-row loads; publication uses 2/10. Once metadata is
initialized, both paths make zero history-recovery queries. Worst-case recovery
for 100 lessons that each exhaust 1,000 versions uses 250 version queries, rather
than per-lesson point queries. The bounds trade database round trips against
loading many large content versions simultaneously.

## Boundaries and Migration Check

- These are serial, warm, local helper measurements. They exclude HTTP,
  authentication, complete directory/history responses, structure decoding,
  and production concurrency. The old synthetic HTTP route was removed.
- Seven samples give a **low-confidence p95**, not a production latency SLO.
- Returned bytes count UTF-8 scalar values, excluding protocol framing,
  metadata, SQL text, and request parameters. `tracemalloc` excludes database
  memory and allocations outside Python's traced allocator.
- Only the recorded database versions were executed. MySQL 8.0 was not run;
  the benchmark does not claim runtime verification on that version.

The real Alembic revision `f569f2199973` was separately exercised on an isolated
MySQL 26.7.0 legacy table. `upgrade()` successfully added the nullable BIGINT
column using `ALGORITHM=INSTANT`; the old row remained
null, and a new positive revision round-tripped correctly. `downgrade()` removed
the column and preserved both rows. This is functional DDL verification on a
small fixture, not a production migration-duration or concurrent-lock test.

The migration tries `INSTANT` without an incompatible `LOCK=NONE` clause. Only
explicit unsupported-algorithm errors 1845/1846 permit the existing
`INPLACE, LOCK=NONE` fallback, which can rebuild the table. Permission errors,
duplicate columns, lock timeouts and connection failures propagate without a
retry. The fallback preserves compatibility with the deployment build recorded
in migration `e5a7c9d1f3b4`; a read-only dev01 check still reported MySQL 8.0.36
Source distribution. No remote DDL was executed. Neither algorithm removes the
need for metadata locks. Offline-generated SQL contains only `INSTANT`: use the
normal online Alembic upgrade for runtime fallback, or review offline SQL for
the target environment before execution.
