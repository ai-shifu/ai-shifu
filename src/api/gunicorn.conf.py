# Gunicorn configuration. Loaded automatically because the container runs
# gunicorn from /app (this file's directory); command-line flags from the
# deployment entrypoint (e.g. -w) still take precedence over values here.

# With preload_app the master imports the application BEFORE forking workers,
# so gevent's monkey-patching must happen here, in the master, before any of
# the app's imports touch socket/ssl. The gevent worker class re-patches in
# the child, which is a no-op.
from gevent import monkey

monkey.patch_all()

# Import the app once in the master and share its read-only memory (imports,
# model tables, litellm's cost map, ...) with every worker via copy-on-write.
# Without this each worker pays the full ~350MB import cost separately.
preload_app = True


def post_fork(server, worker):
    """Reset per-process resources that must not be shared across fork.

    SQLAlchemy connection pools created in the master (the DB init in
    create_app validates connections) would otherwise be shared by all
    workers, interleaving protocol streams. dispose(close=False) drops the
    pool without closing the parent's file descriptors. redis-py connection
    pools are fork-safe already (pid check on checkout) and need no handling.
    """
    try:
        from app import app as flask_app
        from flaskr.dao import db

        with flask_app.app_context():
            for engine in db.engines.values():
                engine.dispose(close=False)
    except Exception:  # pragma: no cover - defensive: never kill a booting worker
        worker.log.exception("post_fork engine dispose failed")
