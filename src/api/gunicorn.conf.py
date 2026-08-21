# Gunicorn configuration. Loaded automatically because the container runs
# gunicorn from /app (this file's directory); command-line flags from the
# deployment entrypoint (e.g. -w) still take precedence over values here.

"""Configure Gunicorn worker startup and lifecycle hooks."""

import os
import sys


def _gevent_worker_requested(argv) -> bool:
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


def post_fork(server, worker) -> None:
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

    # Langfuse SDK v3 keeps per-public-key ResourceManager singletons and
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
