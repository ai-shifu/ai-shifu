# API capacity metrics

Gunicorn aggregates all workers in each Pod at the existing internal metrics
endpoint (default `/internal/metrics`). A collector must scrape every Pod and
retain Pod identity before summing replicas. Scraping a Service IP can repeatedly
select one Pod and does not measure the whole deployment.

## Storage and lifecycle

`gunicorn.conf.py` prepares `PROMETHEUS_MULTIPROC_DIR` before application preload
imports Prometheus. By default it creates a private directory with mode 0700 per
master. Forked workers share the directory; a new USR2 master gets fresh storage.
The master removes dead workers' **live gauges**, while retaining their counters
and histograms until that master exits. Only the exiting master's automatically
allocated directory is deleted. Existing preload, worker class selection, database
pool resets, and exporter initialization remain in place.

An explicit environment variable must be set before Gunicorn starts, point to a
fresh dedicated writable directory, and contain no old `*.db` files. Startup
rejects stale files or an earlier Prometheus import. Explicit directories are
never cleared automatically; prepare a new directory between master generations.
Do not share one explicit directory between independent masters or Pods. A value
loaded only from Flask's `.env` is too late for the Gunicorn bootstrap.

For single-process Flask development, leave the variable **unset**. Prometheus
interprets even an empty exported value as enabling multiprocess writers, so the
full generated environment example comments this assignment out. Without the
variable, the endpoint retains its ordinary process registry. The multiprocess
endpoint exports mmap-backed application metrics; Python's default process/GC
collectors and custom collectors are not aggregated there. Use container metrics
for Pod CPU, working set, RSS, OOM, and restart measurements.

Counters reset when the master changes. Use `rate`/`increase`, retaining instance
identity until after reset handling. Dead workers' live gauge samples can disappear
entirely rather than remain as an explicit zero. Dashboards may display absent
activity as zero, but require independent `up` and Kubernetes readiness alerts.
Abrupt process/node death cannot emit a final SSE outcome; cleanup removes the live
count without inventing a completed/closed/error event. Counter/histogram files
remain for reaped workers, so monitor temporary-storage usage if configuring frequent
worker recycling during a long-lived master.

## Measurement contract

| Metric | Meaning |
| --- | --- |
| `ai_shifu_http_requests_total` | Response-header status counts, preserving existing behavior. |
| `ai_shifu_http_request_duration_seconds` | Request entry to response headers; not full SSE duration. |
| `ai_shifu_http_in_progress` | Requests awaiting headers plus streamed SSE bodies still active. Non-SSE downloads finish accounting at headers. |
| `ai_shifu_sse_active` | Streamed `text/event-stream` bodies not yet completed, closed, or failed. |
| `ai_shifu_sse_responses_total` | Observed terminal outcomes: `completed`, `closed`, or `error`. |
| `ai_shifu_sse_duration_seconds` | Request entry through observed SSE body termination, including header work. |
| `ai_shifu_sse_first_chunk_seconds` | Request entry to first nonempty body chunk; metadata/heartbeats can precede model output. This is not first-model-token latency. |

New capacity gauges exclude metrics, observability health, `/ping`, and `/health`
requests. Existing HTTP counters still include them. Paths use matched route
templates; unmatched requests use `<unmatched>` for both old and new metrics.
Labels contain method, route, header status, and bounded terminal outcome as
applicable. They contain no request ID, user/content data, or raw unmatched path.

SSE instrumentation never parses events, buffers chunks, or waits for the next
chunk early. The wrapper keeps original chunks and exceptions, closes the original
iterable once, and preserves Flask response close callbacks. State survives beyond
Flask's request context. Repeated close/teardown cannot decrement the same request
twice. Metric update failures do not interrupt body delivery. A business error
encoded inside a normal SSE event is not classified by this wrapper; a Python body
exception is `error`, while the HTTP status can remain 200 because headers were
already sent. `closed` means the server closed an unfinished iterable; it does not
prove which peer initiated the disconnect.

## Production acceptance before reducing replicas

The source change does not enable a collector or change replicas, worker/thread
counts, requests, or limits. Protect the existing internal endpoint through the
cluster's ingress/network/access policy before collecting; do not expose it as a
public capacity dashboard. Verify all four workers contribute to one Pod scrape,
then collect all six Pods through at least a full peak cycle and the agreed
observation window. Compare active SSE, first-chunk latency, full-stream outcomes,
HTTP latency/errors, container memory peaks, CPU, and node replacement headroom.

Keep the planned 6 → 5 → 4 experiment separate from worker/process or memory-request
changes. Define rollback thresholds from baseline measurements first, verify
placement and release capacity at each step, and keep production acceptance in the
[active execution plan](../exec-plans/active/api-capacity-observability.md). Passing
local tests alone does not establish that four Pods are sufficient.
