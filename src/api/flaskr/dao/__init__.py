from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from redis import Redis
from sqlalchemy import event
import sqlparse
import logging
import traceback
import os

# create a global db object
db = None
redis_client = None


def init_db(app: Flask):
    global db
    if app.debug:
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    # Flask-SQLAlchemy 3.x only reads pool settings from SQLALCHEMY_ENGINE_OPTIONS;
    # the standalone SQLALCHEMY_POOL_SIZE/TIMEOUT/RECYCLE/MAX_OVERFLOW keys are ignored.
    # QueuePool-only keys are skipped for SQLite (SingletonThreadPool / StaticPool
    # reject max_overflow / pool_timeout).
    existing_options = dict(app.config.get("SQLALCHEMY_ENGINE_OPTIONS") or {})
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

    redis_kwargs = {
        "host": host,
        "port": port,
        "db": app.config["REDIS_DB"],
        "socket_connect_timeout": app.config.get("REDIS_SOCKET_CONNECT_TIMEOUT", 1.0),
        "socket_timeout": app.config.get("REDIS_SOCKET_TIMEOUT", 1.0),
    }

    if (
        app.config.get("REDIS_PASSWORD") is not None
        and app.config["REDIS_PASSWORD"] != ""
    ):
        redis_kwargs["password"] = app.config["REDIS_PASSWORD"]
        redis_kwargs["username"] = app.config.get("REDIS_USER", None)
        redis_client = Redis(**redis_kwargs)
    else:
        redis_client = Redis(**redis_kwargs)
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
