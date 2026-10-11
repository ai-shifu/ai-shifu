# Lesson Content Revision Comparison Performance

Recorded on 2026-10-12 for integer revision comparison. This report replaces
the previous full-text comparison benchmark: the implementation no longer extracts or
compares stored lesson text.

## Result

The helper compares the current revision supplied by the caller with the
session's saved `content_revision`. It selects only `outline_item_bid`,
`content_revision`, `turn`, and `finished` in one batch. It does not select
`session_data`, execute JSON functions, or join lesson-body tables. Existing
structure JSON is read by the caller; that work is outside this microbenchmark.

On local MySQL, comparing 100 sessions with 1 MiB histories took **4.45 ms p50**
and **4.83 ms sample p95**, returned 1,425 bytes of values, and used about 104 KB
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
| MySQL 26.7.0 | 10 | 100 | 0.939 | 1.052 | 144 | 26,954 |
| MySQL 26.7.0 | 100 | 100 | 4.508 | 4.592 | 1,425 | 109,432 |
| MySQL 26.7.0 | 10 | 1,024 | 0.802 | 0.983 | 144 | 26,834 |
| MySQL 26.7.0 | 100 | 1,024 | 4.451 | 4.831 | 1,425 | 103,776 |
| SQLite 3.54.0 | 10 | 100 | 0.336 | 0.587 | 144 | 22,165 |
| SQLite 3.54.0 | 100 | 100 | 2.209 | 2.640 | 1,425 | 76,100 |
| SQLite 3.54.0 | 10 | 1,024 | 1.972 | 2.210 | 144 | 21,397 |
| SQLite 3.54.0 | 100 | 1,024 | 12.503 | 12.857 | 1,425 | 76,100 |

`EXPLAIN` confirmed the existing unique `uq_learn_agent_sessions_active` index
on every final scenario in both engines. MySQL selected it without an index
hint; no new index or database-specific JSON implementation is needed. Plan
row counts are estimates, not measurements of physical reads.

The larger SQLite rows still affected latency despite the small projection and
correct index. The benchmark does not attribute that difference to a specific
storage mechanism; it demonstrates why avoiding a large column does not prove
that all row-storage costs disappear.

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
column using its `ALGORITHM=INPLACE, LOCK=NONE` statement; the old row remained
null, and a new positive revision round-tripped correctly. `downgrade()` removed
the column and preserved both rows. This is functional DDL verification on a
small fixture, not a production migration-duration or concurrent-lock test.
