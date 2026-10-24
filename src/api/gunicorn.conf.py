# Gunicorn configuration. Loaded automatically because the container runs
# gunicorn from /app (this file's directory); command-line flags from the
# deployment entrypoint (e.g. -w) still take precedence over values here.

"""Configure Gunicorn worker startup and lifecycle hooks."""

import ctypes
import gc
import os
import sys

from flaskr.metrics_runtime import (
    cleanup_metrics_directory,
    mark_worker_exit,
    prepare_metrics_directory,
)


def _gevent_worker_requested(argv: object) -> bool:
    """Report whether the command line selects the gevent worker class.

    Monkey-patching must match the worker class. The production deployment
    runs ``-k gthread``; patching gevent onto gthread workers turns their
    request threads into hub-scheduled greenlets and swaps subprocess for
    gevent's fork implementation - a hybrid that produced hub crashes
    (AbstractLinkable._notify_links) which silently interrupted in-flight
    DB exchanges (MySQL off-by-one protocol desync) and corrupted shared
    TLS records. Only a real gevent worker gets patched, and it must be
    patched HERE (the preload master) because with preload_app the app is
    imported before the worker's own patching would run.
    """

    def _is_gevent(value: str) -> bool:
        # Accept every gunicorn spelling of the bundled gevent worker: the
        # alias, the import path (module gunicorn.workers.ggevent), and the
        # legacy egg form.
        value = value.strip()
        return value == "gevent" or value.endswith("#gevent") or "ggevent" in value

    for index, arg in enumerate(argv):
        if arg in ("-k", "--worker-class"):
            if index + 1 < len(argv):
                return _is_gevent(argv[index + 1])
        elif arg.startswith("--worker-class="):
            return _is_gevent(arg.split("=", 1)[1])
        elif arg.startswith("-k") and len(arg) > 2:
            return _is_gevent(arg[2:])
    return False


if _gevent_worker_requested(sys.argv):
    from gevent import monkey

    monkey.patch_all()

# glibc gives each thread that allocates its own malloc arena (up to 8 per CPU), and
# freed memory stays in those arenas. Each gthread worker accumulates arenas as request,
# engine-bridge and SDK threads come and go, so a worker's memory only grows. Two arenas
# keep that bounded. Set before any thread exists; an explicit MALLOC_ARENA_MAX wins.
M_ARENA_MAX = -8
MALLOC_ARENAS = 2


def _limit_malloc_arenas() -> bool:
    """Cap glibc malloc arenas for this process and the workers it forks."""
    if os.environ.get("MALLOC_ARENA_MAX"):
        return False
    try:
        libc = ctypes.CDLL("libc.so.6")
    except OSError:  # not glibc (e.g. macOS development)
        return False
    return bool(libc.mallopt(M_ARENA_MAX, MALLOC_ARENAS))


_limit_malloc_arenas()

# Bootstrap before preload imports prometheus_client and fixes its writer class.
prepare_metrics_directory()

# Mark the preload master so import-time initializers skip anything that
# would start background threads here (e.g. the Langfuse/OTel batch
# exporter). A thread started in the master registers an at-fork restart
# hook; after fork each worker revives the orphaned processor's thread,
# whose gevent threading bookkeeping crashes the hub (KeyError in
# AbstractLinkable._notify_links) and can interrupt unrelated in-flight DB
# exchanges. post_fork clears the flag and re-runs the deferred inits.
os.environ["AI_SHIFU_PRELOAD_MASTER"] = "1"

# Import the app once in the master and share its read-only memory (imports,
# model tables, litellm's cost map, ...) with every worker via copy-on-write.
# Without this each worker pays the full ~350MB import cost separately.
preload_app = True

# Recycle each worker after a bounded number of requests, so memory a worker cannot
# return to the system is released periodically. The jitter keeps workers from
# restarting together. A recycled worker finishes its in-flight requests first,
# including long lesson streams, for up to the deployment's request timeout.
max_requests = 2000
max_requests_jitter = 500
graceful_timeout = 300


def pre_fork(server: object, worker: object) -> None:
    """Keep the preloaded app's objects shared with the forked worker.

    Without this, the garbage collector touching inherited objects in a worker
    copies the master's pages one by one, and each idle worker grows to about
    100 MB of private memory. Frozen objects are never examined again.
    """
    _ = (server, worker)
    gc.freeze()


def post_fork(server: object, worker: object) -> None:
    """Reset per-process resources that must not be shared across fork.

    SQLAlchemy connection pools created in the master (the DB init in
    create_app validates connections) would otherwise be shared by all
    workers, interleaving protocol streams. dispose(close=False) drops the
    pool without closing the parent's file descriptors. redis-py connection
    pools are fork-safe already (pid check on checkout) and need no handling.
    """
    _ = server
    os.environ.pop("AI_SHIFU_PRELOAD_MASTER", None)

    try:
        from app import app as flask_app
        from flaskr.dao import db

        with flask_app.app_context():
            for engine in db.engines.values():
                engine.dispose(close=False)
    except Exception:  # pragma: no cover - defensive: never kill a booting worker
        worker.log.exception("post_fork engine dispose failed")

    # The Langfuse SDK keeps per-public-key ResourceManager singletons and
    # registers a global OpenTelemetry TracerProvider during master preload.
    # Both carry live httpx/TLS connections and a batch-export worker that
    # were created in the master; inherited across fork they are shared by
    # every worker, interleaving TLS records on the exporter connection
    # (observed as "SSL: DECRYPTION_FAILED_OR_BAD_RECORD_MAC") and leaving
    # stale IO watchers behind. Drop the inherited singletons WITHOUT
    # flushing (a flush would write to the shared connection, which is the
    # exact failure being prevented), reset the OTel global so a fresh
    # provider can be registered, then rebuild the client in this worker.
    # Hub-level callback crashes (e.g. AssertionError in
    # AbstractLinkable._notify_links) are printed to stderr by gevent and
    # bypass every application except-block, yet they can break a greenlet
    # wakeup and silently interrupt an in-flight DB exchange (observed as
    # off-by-one protocol desync). Mirror them into the app logger with the
    # failing context object named so the culprit primitive is attributable.
    try:
        from flaskr.common.gevent_hub_observer import install_hub_error_observer

        install_hub_error_observer(flask_app.logger)
    except Exception:  # pragma: no cover - defensive: never kill a booting worker
        worker.log.exception("post_fork hub observer install failed")

    try:
        from flaskr.api.langfuse import init_langfuse
        from langfuse._client.resource_manager import LangfuseResourceManager
        from opentelemetry import trace as otel_trace_api
        from opentelemetry.util._once import Once

        LangfuseResourceManager._instances.clear()
        otel_trace_api._TRACER_PROVIDER = None
        otel_trace_api._TRACER_PROVIDER_SET_ONCE = Once()

        init_langfuse(flask_app)
    except Exception:  # pragma: no cover - defensive: never kill a booting worker
        worker.log.exception("post_fork langfuse reinit failed")

    # Live readiness may launch bounded retries. Like the exporter above,
    # those threads belong to a worker, never to the preload master.
    try:
        from flaskr.service.learn.live_follow_up_routes import (
            init_live_follow_up_readiness,
        )

        init_live_follow_up_readiness(flask_app)
    except Exception:  # pragma: no cover - defensive: never kill a booting worker
        worker.log.warning("post_fork Live readiness initialization unavailable")


def child_exit(server: object, worker: object) -> None:
    """Remove a reaped worker's live capacity gauges in the master."""
    try:
        mark_worker_exit(worker.pid)
    except Exception:
        server.log.exception("Prometheus worker cleanup failed")


def on_exit(server: object) -> None:
    """Release only this master's private metrics storage after workers exit."""
    try:
        cleanup_metrics_directory()
    except Exception:
        server.log.exception("Prometheus master cleanup failed")
