from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from redis import Redis
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
import functools
import random
import sqlparse
import logging
import time
import traceback
import os

logger = logging.getLogger(__name__)

# create a global db object
db = None
redis_client = None

# MySQL error codes that indicate a transient locking conflict; the current
# transaction is already rolled back by the server, so re-running it is the
# documented remedy.
MYSQL_DEADLOCK_ERRNO = 1213
MYSQL_LOCK_WAIT_TIMEOUT_ERRNO = 1205


def _operational_errno(exc: OperationalError):
    orig = getattr(exc, "orig", None)
    args = getattr(orig, "args", None)
    return args[0] if args else None


def _is_retryable_operational_error(exc: OperationalError) -> bool:
    return _operational_errno(exc) in (
        MYSQL_DEADLOCK_ERRNO,
        MYSQL_LOCK_WAIT_TIMEOUT_ERRNO,
    )


def _rollback_quietly() -> None:
    """
    Roll back the current session after a failed transaction. An OperationalError
    leaves the session in a broken state, so this must run on every catch -
    including non-retryable errors and the final attempt - otherwise later
    operations in the same context raise InvalidRequestError. Best-effort: a
    rollback failure is logged rather than masking the original error.
    """
    if db is None:
        return
    try:
        db.session.rollback()
    except Exception as rollback_exc:  # noqa: BLE001 - best-effort cleanup
        logger.warning("retry_on_deadlock rollback failed: %s", rollback_exc)


def retry_on_deadlock(max_attempts: int = 3, backoff_seconds: float = 0.1):
    """
    Retry a transactional function when MySQL reports a deadlock (1213) or a
    lock wait timeout (1205). The failed transaction is rolled back on every
    caught error so the session is left clean; retryable errors are retried with
    exponential backoff plus jitter, while non-retryable errors and the final
    attempt propagate unchanged.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except OperationalError as exc:
                    attempt += 1
                    _rollback_quietly()
                    if attempt >= max_attempts or not _is_retryable_operational_error(
                        exc
                    ):
                        raise
                    logger.warning(
                        "retry_on_deadlock: retrying %s after MySQL errno %s "
                        "(attempt %d/%d)",
                        getattr(func, "__qualname__", func),
                        _operational_errno(exc),
                        attempt,
                        max_attempts,
                    )
                    # Exponential backoff with jitter to avoid re-colliding with
                    # the peer transaction under sustained lock contention.
                    delay = backoff_seconds * (2 ** (attempt - 1))
                    time.sleep(delay + random.uniform(0, backoff_seconds))

        return wrapper

    return decorator


def init_db(app: Flask):
    global db
    if app.debug:
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    # Flask-SQLAlchemy 3.x only reads pool settings from SQLALCHEMY_ENGINE_OPTIONS;
    # the standalone SQLALCHEMY_POOL_SIZE/TIMEOUT/RECYCLE/MAX_OVERFLOW keys are ignored.
    # QueuePool-only keys are skipped for SQLite (SingletonThreadPool / StaticPool
    # reject max_overflow / pool_timeout).
    _raw_engine_opts = app.config.get("SQLALCHEMY_ENGINE_OPTIONS")
    existing_options = (
        dict(_raw_engine_opts) if isinstance(_raw_engine_opts, dict) else {}
    )
    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
    is_sqlite = str(db_uri).startswith("sqlite")

    def _coerce_int(cfg_key: str, default: int) -> int:
        raw = app.config.get(cfg_key)
        if raw is None or raw == "":
            return default
        try:
            return int(raw)
        except (ValueError, TypeError):
            app.logger.warning(
                "Invalid %s=%r, falling back to %d", cfg_key, raw, default
            )
            return default

    if not is_sqlite:
        for opt, cfg, default in (
            ("pool_size", "SQLALCHEMY_POOL_SIZE", 20),
            ("max_overflow", "SQLALCHEMY_MAX_OVERFLOW", 20),
            ("pool_timeout", "SQLALCHEMY_POOL_TIMEOUT", 30),
            ("pool_recycle", "SQLALCHEMY_POOL_RECYCLE", 3600),
        ):
            if opt not in existing_options:
                existing_options[opt] = _coerce_int(cfg, default)

    # pool_pre_ping is default-on; callers can opt out by pre-setting
    # SQLALCHEMY_ENGINE_OPTIONS["pool_pre_ping"] = False.
    existing_options.setdefault("pool_pre_ping", True)

    # Force every MySQL connection to use the UTC session time zone so that
    # DB-side time evaluation (func.now()/CURRENT_TIMESTAMP/NOW()) stores UTC,
    # matching the UTC application process. Without this the session inherits
    # the server time zone (e.g. +08:00) and func.now() defaults would persist
    # local wall-clock values. SQLite (tests) has no session time zone.
    if not is_sqlite:
        connect_args = dict(existing_options.get("connect_args") or {})
        connect_args.setdefault("init_command", "SET time_zone = '+00:00'")
        existing_options["connect_args"] = connect_args

    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = existing_options

    if db is None:
        db = SQLAlchemy()
    db.init_app(app)

    # Enable formatted SQL output in the development environment
    if app.debug:

        def setup_sql_logging():
            @event.listens_for(db.engine, "before_cursor_execute")
            def before_cursor_execute(
                conn, cursor, statement, parameters, context, executemany
            ):
                stack = traceback.extract_stack()
                project_root = os.path.abspath(
                    os.path.join(os.path.dirname(__file__), "../../../")
                )
                caller_info = "Unknown location"

                for frame in reversed(stack[:-2]):
                    if (
                        project_root in frame.filename
                        and "site-packages" not in frame.filename
                    ):
                        caller_info = f"File: {os.path.relpath(frame.filename, project_root)}, Line: {frame.lineno}, Function: {frame.name}"
                        break

                # Format the SQL statement
                formatted_sql = sqlparse.format(
                    statement, reindent=True, keyword_case="upper", strip_comments=True
                )

                # If there are parameters, try formatting
                if parameters:
                    try:
                        # Try to format the parameters into the SQL statement
                        raw_sql = formatted_sql % parameters
                    except (TypeError, ValueError):
                        # If the formatting fails, the SQL and parameters will be displayed respectively
                        raw_sql = f"SQL:\n{formatted_sql}\nParameters: {parameters}"
                else:
                    raw_sql = formatted_sql

                app.logger.info(f"\nLocation: {caller_info}\n{raw_sql}\n")

        # Set the event listener in the application context
        with app.app_context():
            setup_sql_logging()


def init_redis(app: Flask):
    global redis_client

    host = app.config.get("REDIS_HOST")
    port = app.config.get("REDIS_PORT")

    if not host or port is None:
        app.logger.warning(
            "Redis not configured: REDIS_HOST or REDIS_PORT is None - running without Redis"
        )
        redis_client = None
        return

    app.logger.info(
        "init redis {} {} {}".format(
            app.config["REDIS_HOST"], app.config["REDIS_PORT"], app.config["REDIS_DB"]
        )
    )

    if (
        app.config.get("REDIS_PASSWORD") is not None
        and app.config["REDIS_PASSWORD"] != ""
    ):
        redis_client = Redis(
            host=host,
            port=port,
            db=app.config["REDIS_DB"],
            password=app.config["REDIS_PASSWORD"],
            username=app.config.get("REDIS_USER", None),
        )
    else:
        redis_client = Redis(
            host=host,
            port=port,
            db=app.config["REDIS_DB"],
        )
    app.logger.info("init redis done")


def run_with_redis(app, key, timeout: int, func, args):
    with app.app_context():
        app.logger.info("run_with_redis start {}".format(key))
        lock = redis_client.lock(key, timeout=timeout, blocking_timeout=timeout)
        if lock.acquire(blocking=False):
            app.logger.info("run_with_redis get lock {}".format(key))
            try:
                return func(*args)
            finally:
                try:
                    lock.release()
                except Exception:
                    pass
        else:
            app.logger.info("run_with_redis get lock failed {}".format(key))
            return None
