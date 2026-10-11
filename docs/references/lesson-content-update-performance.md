# Lesson Content Update Comparison Performance

Recorded on 2026-10-11 for the snapshot-based lesson-update implementation.
These measurements cover the comparison helper in an isolated local database,
not production traffic or the existing timestamp-based implementation.

## Result and Tradeoff

The final query returns identifiers and boolean values without transferring
lesson sources or conversation histories to Python. On local MySQL, the largest
fixture (100 active sessions, each with a 1 MiB document) returned 1,400 bytes of
values instead of 107,930,733 bytes for a full-session comparison. Python's
measured allocation peak fell from 111,246,154 to 197,098 bytes.

The database still reads and parses the stored `LONGTEXT` documents. The same
100-session query took about **0.60 seconds** on warm local MySQL. Transferring
and comparing the full histories on this machine took about 0.19 seconds. The
chosen approach reduces returned data and Python memory; it does not eliminate
database work or guarantee lower latency on a fast local connection.

Both implementations in this report perform the new, accurate comparison. The
full-session baseline is an alternative implementation, not the currently
deployed timestamp comparison. These results therefore do not claim a speedup
over existing production behavior.

## Reproduction and Measurement Boundaries

Run from `src/api` using the backend Python environment:

```bash
python scripts/benchmark_lesson_content_updates.py --mysql-env .env --iterations 7
```

Omit `--mysql-env` to run SQLite alone. The script reads only the configured
database connection from the supplied environment file, requires a local MySQL
host, creates a uniquely named disposable database, and removes that database
afterward. It does not migrate or alter the configured development database.
SQLite uses a temporary file. Only the three required fixture tables are
created, using their declared model definitions.

The fixture matrix uses 10 or 100 eligible sessions, 7 or 30 KiB source bodies,
and 100 KiB or 1 MiB session documents. Bodies remain within the current MySQL
`TEXT` limit. Each batch also includes 1,000 unrelated session and outline rows
and 1,000 retired sessions belonging to the same learner and target lessons.
Retired documents are 100 KiB each, alternating valid and malformed JSON; their
active keys are null.
The comparison mix contains unchanged bodies, different bodies of the same
length, and bodies whose lengths differ. Histories contain synthetic padding;
this is a size stress test, not a sampled production conversation distribution.

Each operation receives two warmups and seven timed samples. Allocation
tracing runs separately so its overhead is excluded from the latency samples.
The reported p95 is an interpolated sample percentile with **low confidence
from only seven measurements**; it is not a production tail-latency estimate.

- Direct-query timings call the real helper in a minimal Flask application
  context. A separate synthetic HTTP-route measurement uses Flask's in-process
  test client to dispatch that helper and serialize its result as JSON. It
  includes no real network, authentication, full directory/history generation,
  or browser rendering. Neither measurement is a production API benchmark.
- `returned_value_bytes` counts UTF-8 scalar values from the database result.
  It excludes protocol framing, metadata, SQL text, and request parameters.
- Python peak memory uses `tracemalloc`. It excludes database-server memory,
  database buffers, and memory allocated outside Python's traced allocator.
- The measurements are local, serial, and warm. They do not measure disk reads,
  database CPU utilization, cold caches, concurrent users, or production capacity.
- Database versions were SQLite 3.53.4 and MySQL 26.7.0. Repository deployment
  configurations target MySQL 8.0; that server version was not run here. Docker,
  Docker Desktop, Podman, and Colima were unavailable locally; no runtime was
  installed or downloaded for this benchmark.

The script emits the complete machine-readable matrix and execution plans as
JSON. Its progress messages go to standard error, allowing stdout to be saved
as a report.

## Final Latency Matrix

Times are milliseconds. Every measured comparison issued **one SQL query** and
returned exactly the 10 or 100 eligible rows, excluding the 2,000 unrelated or
retired sessions. Query counts and allocation peaks are measured separately
from the synthetic route timings.

### MySQL 26.7.0

| Sessions | Body KiB | Session KiB | Scalar query p50 | Scalar query p95 | Full-session p50 | Full-session p95 |
| --- | --- | --- | --- | --- | --- | --- |
| 10 | 7 | 100 | 8.497 | 8.838 | 5.450 | 6.232 |
| 100 | 7 | 100 | 71.636 | 84.893 | 17.625 | 19.453 |
| 10 | 30 | 1,024 | 79.798 | 94.383 | 40.227 | 44.195 |
| 100 | 30 | 1,024 | 603.326 | 628.454 | 186.663 | 203.339 |

### SQLite 3.53.4

| Sessions | Body KiB | Session KiB | Scalar query p50 | Scalar query p95 | Full-session p50 | Full-session p95 |
| --- | --- | --- | --- | --- | --- | --- |
| 10 | 7 | 100 | 1.765 | 2.039 | 1.693 | 1.934 |
| 100 | 7 | 100 | 14.004 | 14.372 | 17.078 | 17.700 |
| 10 | 30 | 1,024 | 10.533 | 11.769 | 14.935 | 15.253 |
| 100 | 30 | 1,024 | 78.296 | 80.370 | 142.414 | 149.472 |

### Synthetic Comparison HTTP Route

This is `/benchmark/lesson-content-updates` in the standalone script's minimal
application, dispatched with Flask's test client. It is not an installed
product endpoint. The response contains the helper's three flags for each
lesson. Response bodies were 736 bytes for 10 lessons and 7,336 bytes for 100.
No real TCP/TLS request is included. The actual directory/history routes have
separate regression coverage; their complete latency was not measured here.

| Database | Sessions | Session KiB | Synthetic route p50 ms | Synthetic route p95 ms |
| --- | --- | --- | --- | --- |
| MySQL | 10 | 100 | 14.773 | 15.715 |
| MySQL | 100 | 100 | 71.090 | 76.886 |
| MySQL | 10 | 1,024 | 80.299 | 96.091 |
| MySQL | 100 | 1,024 | 659.603 | 840.094 |
| SQLite | 10 | 100 | 2.138 | 2.167 |
| SQLite | 100 | 100 | 14.658 | 16.037 |
| SQLite | 10 | 1,024 | 9.835 | 10.567 |
| SQLite | 100 | 1,024 | 85.333 | 87.829 |

The direct and route samples were taken in separate sequences. Small timing
differences, including a route sample faster than the direct query, reflect
run-to-run variation rather than a reduction in required work.

### Result Values and Python Memory

Returned-value sizes were identical across both database engines. Python peaks
below are from MySQL; the emitted report also contains the SQLite peaks.

| Sessions | Session KiB | Scalar result bytes | Full-session result bytes | Scalar Python peak bytes | Full-session Python peak bytes |
| --- | --- | --- | --- | --- | --- |
| 10 | 100 | 140 | 1,095,793 | 62,384 | 1,443,860 |
| 100 | 100 | 1,400 | 10,957,933 | 207,234 | 11,364,170 |
| 10 | 1,024 | 140 | 10,793,073 | 62,312 | 14,050,324 |
| 100 | 1,024 | 1,400 | 107,930,733 | 197,098 | 111,246,154 |

## Query Design and Verification

The final MySQL path uses `JSON_TABLE` on a validity-guarded document. It
extracts the source as JSON, preserves its type, and checks for a nonempty
message array with `EXISTS PATH '$.messages[*]'`. It does not materialize the
message history as a result column. The loader enables this path for known
MySQL versions at least 8.0.21; SQLite, MariaDB, and older or unidentified
versions retain guarded extraction. The real public loader was rechecked after
the version guard was added and selected the MySQL fast path on 26.7.0.

Compatibility of native JSON-typed columns is also supported by the tagged
[MySQL 8.0.21 expected test results](https://github.com/mysql/mysql-server/blob/mysql-8.0.21/mysql-test/suite/json/r/json_table.result#L74-L92),
which preserve string, numeric and object values as their original JSON types.
The [MySQL manual](https://dev.mysql.com/doc/refman/8.0/en/json-table-functions.html)
documents JSON-null handling from 8.0.21. This source-level check complements
the local runtime validation; it is not an additional MySQL 8.0 server run.

Reducing repeated parsing mattered more than string equality. An early query
that repeated guarded JSON expressions took roughly 4.83 seconds for the
100-by-1-MiB MySQL fixture without unrelated rows; reducing duplicated flags
brought that to about 1.95 seconds. The final path avoids those repeated
expressions. Those intermediate runs had different fixture details and are
diagnostic evidence, not the final comparison matrix.

The MySQL query supplies a scoped `FORCE INDEX` hint for the existing unique
`uq_learn_agent_sessions_active` index. `EXPLAIN` confirmed an active-key range
scan, alongside an outline primary-key or business-key lookup and table-function
materialization, with the same learner's 1,000 retired sessions present. The
hint prevents a user-index scan from expanding with retired session history.
No new index was needed. Execution-plan row counts are estimates and do not
measure physical reads or production rows examined.

The benchmark validated 25 cases on both formal learning and teacher preview,
on both engines: **100 case/surface/database checks passed**. It covers
same-length edits, case and accent changes, trailing spaces, cleared bodies,
CRLF and bare-CR normalization, embedded NUL characters, malformed JSON,
unrecognized schema versions, retired sessions, missing or non-string source
values, and empty, scalar, object, boolean, or null message values. It also
checks started/completed flags and isolation between the two learning surfaces.

## Operational Interpretation

One selected lesson reads one selected session; a course-wide compatibility
response may process every eligible session. The latter retains a cost
proportional to stored document volume even though its result is small. A
100-by-1-MiB course can therefore add hundreds of milliseconds of database work
under the measured conditions. The result must not be described as free or as
an independently stored snapshot read.

Comparing lengths in a separate request would still require extracting the
source and would add a second round trip for equal lengths, including unchanged
lessons. Equal lengths also cannot establish equality. Computing or storing a
hash inside the same `LONGTEXT` document does not remove its read/parse cost.

The next optimization should be chosen from actual endpoint telemetry and
session-size distributions. If course-wide comparisons are a bottleneck,
reduce their invocation scope or introduce a correctly versioned digest cache;
do not silently weaken the exact-comparison or session-isolation contract. A
separate compact database field would require a separate schema decision.
