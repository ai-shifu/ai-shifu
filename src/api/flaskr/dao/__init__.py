import collections
import contextlib
import itertools

from flask import Flask
from flask.globals import app_ctx
from flask_sqlalchemy import SQLAlchemy
from redis import Redis
from sqlalchemy import event
from sqlalchemy import pool as sa_pool
from sqlalchemy.engine import Engine
from sqlalchemy.exc import (
    DisconnectionError,
    InterfaceError,
    OperationalError,
    ResourceClosedError,
    SQLAlchemyError,
)
import functools
import random
import select as select_module
import sys
import sqlparse
import logging
import time
import traceback
import os

logger = logging.getLogger(__name__)

# create a global db object
db = None
redis_client = None

# Session scope tokens must never repeat. Flask-SQLAlchemy's stock scope
# function keys the scoped-session registry on id(app_ctx) - a CPython memory
# address that is recycled as soon as a context is garbage collected. With
# high-frequency context churn (streaming requests plus nested app contexts
# in hot paths), a new context can be allocated at the address of a dead one;
# if the dead context's session ever escaped teardown (an interrupted
# cleanup under gevent), the new context SILENTLY ADOPTS the leftover session
# and its checked-out connection. Two greenlets then interleave commands on
# one MySQL connection - observed in production as paired failures in the
# same second: an INSERT losing its OK packet (FlushError: NULL identity
# key) while another context's SELECT consumed it (ResourceClosedError),
# followed by 2014 Command Out of Sync. A monotonically increasing token
# stamped on each context makes scope keys unique for the process lifetime:
# a leaked session can no longer be adopted, only leak - which pool
# recycling and the desync probes already handle.
_app_ctx_scope_counter = itertools.count(1)


def _unique_app_ctx_scope() -> int:
    ctx = app_ctx._get_current_object()
    token = ctx.__dict__.get("_dao_session_scope_token")
    if token is None:
        token = next(_app_ctx_scope_counter)
        ctx.__dict__["_dao_session_scope_token"] = token
    return token


def _socket_has_unread_data(dbapi_connection) -> bool:
    """Return True when the DBAPI connection's socket has readable bytes.

    A healthy pooled MySQL connection is silent between transactions: every
    response has been consumed and the server never pushes unsolicited data.
    Readable bytes therefore mean either an unread response left behind by an
    interrupted operation (the protocol stream is desynced - the next query
    on this connection would read the stale packet and fail with
    ResourceClosedError / pymysql 2014 "Command Out of Sync") or a
    server-initiated shutdown packet. Both make the connection unusable.

    Only pymysql exposes the socket as ``_sock``; other drivers (e.g. SQLite
    in tests) return False and are left to pool_pre_ping.
    """
    sock = getattr(dbapi_connection, "_sock", None)
    if sock is None:
        return False
    try:
        readable, _, _ = select_module.select([sock], [], [], 0)
    except (OSError, ValueError, TypeError):
        # Closed, detached, or fd-less socket object; pre_ping handles plain
        # disconnects, and event dispatch must never fail on the probe.
        return False
    return bool(readable)


def _server_thread_id(dbapi_connection):
    """Best-effort MySQL server-side connection id for log correlation."""
    try:
        return dbapi_connection.thread_id()
    except Exception:  # noqa: BLE001 - diagnostics only
        return None


def _pool_diagnostics_logger():
    """Log through the app logger when available.

    The app logger carries the RequestFormatter (request-id / trace context)
    and the alerting handlers; the bare module logger only reaches stderr.
    Pool events usually fire inside an app context, but engine use outside
    one (scripts, tests) must not break on logging.
    """
    try:
        from flask import current_app

        return current_app.logger
    except Exception:  # noqa: BLE001 - outside app context
        return logger


@event.listens_for(sa_pool.Pool, "checkin")
def _invalidate_desynced_connection_on_checkin(dbapi_connection, connection_record):
    if dbapi_connection is None:
        return
    if _socket_has_unread_data(dbapi_connection):
        # stack_info identifies the code path that returned the poisoned
        # connection - i.e. the request that interrupted a protocol exchange.
        _pool_diagnostics_logger().error(
            "DB connection returned to pool with unread protocol data; "
            "invalidating it (pid=%s server_thread_id=%s). The stack below "
            "is the checkin path of the request that desynced this "
            "connection.",
            os.getpid(),
            _server_thread_id(dbapi_connection),
            stack_info=True,
        )
        connection_record.invalidate()


@event.listens_for(sa_pool.Pool, "checkout")
def _reject_desynced_connection_on_checkout(
    dbapi_connection, connection_record, connection_proxy
):
    if _socket_has_unread_data(dbapi_connection):
        _pool_diagnostics_logger().warning(
            "Rejecting pooled DB connection with unread protocol data at "
            "checkout (pid=%s); the pool will retry with a fresh connection.",
            os.getpid(),
        )
        # DisconnectionError makes the pool discard this connection and
        # transparently retry the checkout with another one.
        raise DisconnectionError(
            "pooled connection has unread protocol data (desynced stream)"
        )
    # Protected liveness ping, replacing pool_pre_ping. The stock pre_ping
    # path is the one wire operation with NO BaseException protection: a
    # GreenletExit landing in COM_PING's recv escapes every layer, leaks the
    # checkout, and the leaked fairy's GC finalizer later emits a ROLLBACK
    # that consumes the stale PING OK - leaving the connection permanently
    # off by one response. Pinging here keeps dead-connection detection while
    # invalidating BEFORE any interruption propagates, so the GC finalizer
    # sees an already-invalidated record and never touches the wire.
    ping = getattr(dbapi_connection, "ping", None)
    if ping is None:
        return
    try:
        ping(False)
    except BaseException as ping_exc:
        connection_record.invalidate(
            e=ping_exc if isinstance(ping_exc, Exception) else None
        )
        if isinstance(ping_exc, Exception):
            # Dead connection: let the pool retry with a fresh one.
            raise DisconnectionError(
                "pooled connection failed the checkout liveness ping"
            ) from ping_exc
        # GreenletExit and friends propagate; the record is already
        # invalidated so nothing dirty can reach the pool.
        raise


# Ring buffer of recent statements per DBAPI connection, plus a pre-execute
# probe. Production forensics (2026-08-04 12:20) proved the desync happens
# WITHIN one connection: a statement's response goes unread (an interrupted
# exchange whose exception was swallowed somewhere), and every later command
# silently consumes the PREVIOUS command's response - an INSERT reading an
# INSERT's OK packet looks perfectly normal - until a SELECT meets an OK
# packet (ResourceClosedError) or an INSERT meets a result set (FlushError:
# NULL identity key). Probing the socket immediately before each execute
# catches the off-by-one at the first statement after it arises, and the
# journal's tail names the statement whose exchange was interrupted.
_STATEMENT_JOURNAL_KEY = "dao_statement_journal"
_STATEMENT_JOURNAL_SIZE = 25
_STATEMENT_SNIPPET_CHARS = 90


def _statement_journal(connection) -> collections.deque:
    journal = connection.info.get(_STATEMENT_JOURNAL_KEY)
    if journal is None:
        journal = collections.deque(maxlen=_STATEMENT_JOURNAL_SIZE)
        connection.info[_STATEMENT_JOURNAL_KEY] = journal
    return journal


@event.listens_for(Engine, "before_cursor_execute")
def _intercept_desync_before_execute(
    conn, cursor, statement, parameters, context, executemany
):
    dbapi_connection = getattr(conn.connection, "dbapi_connection", None)
    if dbapi_connection is None:
        return
    if _socket_has_unread_data(dbapi_connection):
        journal = list(_statement_journal(conn))
        _pool_diagnostics_logger().error(
            "DB connection has an unread response before executing a new "
            "statement (off-by-one protocol desync, pid=%s "
            "server_thread_id=%s). The LAST journal entry is the statement "
            "whose exchange was interrupted. journal=%s next_statement=%r",
            os.getpid(),
            _server_thread_id(dbapi_connection),
            journal,
            statement[:_STATEMENT_SNIPPET_CHARS],
        )
        with contextlib.suppress(Exception):
            conn.invalidate()
        raise DisconnectionError(
            "connection has an unread response from a previous statement "
            "(interrupted exchange); refusing to execute on a desynced stream"
        )


@event.listens_for(Engine, "after_cursor_execute")
def _journal_statement_after_execute(
    conn, cursor, statement, parameters, context, executemany
):
    with contextlib.suppress(Exception):
        _statement_journal(conn).append(
            (
                statement[:_STATEMENT_SNIPPET_CHARS],
                getattr(cursor, "rowcount", None),
                getattr(cursor, "lastrowid", None),
            )
        )


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


# MySQL client-side error codes whose presence means the connection's
# response stream can no longer be trusted:
#   2013 Lost connection during query - the response was half read
#   2014 Command Out of Sync - a response was consumed out of order (the
#        direct symptom of an off-by-one desynced stream)
_PROTOCOL_INTERRUPT_ERRNOS = frozenset({2013, 2014})


def is_protocol_interrupt_error(exc: BaseException) -> bool:
    """Return True when the exception implies a desynced response stream.

    Such a connection must be discarded, never rolled back: a ROLLBACK on a
    desynced stream consumes another stale packet and perpetuates the
    off-by-one.
    """
    if isinstance(exc, (ResourceClosedError, DisconnectionError)):
        return True
    # gevent interruptions frequently surface as driver interface or raw
    # socket errors rather than clean MySQL errnos; all of them mean the
    # exchange on this connection did not complete.
    for candidate in (exc, getattr(exc, "orig", None)):
        if isinstance(candidate, (InterfaceError, OSError)):
            # OSError covers BrokenPipeError / ConnectionResetError / timeouts.
            return True
        if type(candidate).__name__ == "InterfaceError":
            # pymysql.err.InterfaceError is not SQLAlchemy's InterfaceError;
            # match the driver-level one by name to avoid a driver import.
            return True
        args = getattr(candidate, "args", ())
        if args and isinstance(args[0], int) and args[0] in _PROTOCOL_INTERRUPT_ERRNOS:
            return True
    return False


def is_abnormal_stream_termination(exc: BaseException | None) -> bool:
    """Return True for terminations that may have interrupted a DB exchange.

    GeneratorExit (client walked away from a streaming generator) and
    non-Exception BaseExceptions (GreenletExit from a rolling deploy,
    SystemExit, KeyboardInterrupt) can be injected at any gevent IO switch
    point - including mid-exchange, leaving an unread response owed on the
    wire. Protocol-interrupt errors are the same condition already observed.
    Server-delivered errors (IntegrityError, deadlocks, business exceptions)
    are NOT abnormal: the response arrived intact and rollback stays safe.
    """
    if exc is None:
        return False
    if isinstance(exc, GeneratorExit):
        return True
    if not isinstance(exc, Exception):
        return True
    return is_protocol_interrupt_error(exc)


def invalidate_session(*, source: str, session=None) -> bool:
    """Discard the session's connection instead of returning it to the pool.

    ``Session.invalidate()`` rolls back the session state WITHOUT emitting
    anything on the wire and marks the raw DBAPI connection as discarded -
    the documented remedy for gevent-style interruptions. The scoped_session
    proxy does NOT forward ``invalidate`` (SQLAlchemy 2.0.x), so the real
    Session must be resolved by calling the registry first; a plain
    ``db.session.invalidate()`` raises AttributeError and silently does
    nothing when wrapped in a broad except.
    """
    target = (
        session if session is not None else (db.session if db is not None else None)
    )
    if target is None:
        return False
    try:
        if not hasattr(target, "invalidate") and callable(target):
            target = target()
        target.invalidate()
        return True
    except Exception:  # noqa: BLE001 - termination cleanup must not raise
        _pool_diagnostics_logger().warning(
            "%s: session invalidate failed", source, exc_info=True
        )
        return False


def cleanup_session_after(
    exc: BaseException | None, *, source: str, session=None
) -> str:
    """Classify a termination and clean the session accordingly.

    Abnormal (stream-interrupting) terminations invalidate the connection;
    everything else rolls back as before. A rollback that itself fails means
    the connection is already broken, so it escalates to invalidate. Returns
    "invalidated" | "rolled_back" | "noop" for test assertions.
    """
    if exc is not None and is_abnormal_stream_termination(exc):
        invalidate_session(source=source, session=session)
        return "invalidated"
    target = (
        session if session is not None else (db.session if db is not None else None)
    )
    if target is None:
        return "noop"
    try:
        target.rollback()
        return "rolled_back"
    except Exception:  # noqa: BLE001 - escalate, never raise from cleanup
        _pool_diagnostics_logger().warning(
            "%s: rollback failed; escalating to session invalidate",
            source,
            exc_info=True,
        )
        invalidate_session(source=source, session=session)
        return "invalidated"


def release_session_classified(*, source: str) -> None:
    """Remove the scoped session, discarding the connection first when a
    stream-interrupting exception is propagating.

    Designed for ``finally`` blocks: ``sys.exc_info()`` still sees the
    in-flight exception there - including BaseExceptions like GreenletExit
    that never hit an ``except GeneratorExit`` handler because they were
    injected into IO deep inside the generator's own frame. Without this,
    the closing ``remove()`` emits a ROLLBACK on a possibly desynced
    connection (and runs BEFORE the app-context teardown guard could act).
    """
    exc = sys.exc_info()[1]
    if exc is not None and is_abnormal_stream_termination(exc):
        invalidate_session(source=source)
    try:
        db.session.remove()
    except Exception:  # noqa: BLE001 - cleanup must not mask the original
        _pool_diagnostics_logger().warning(
            "%s db session cleanup failed", source, exc_info=True
        )


def _rollback_quietly() -> bool:
    """
    Roll back the current session after a failed transaction. An OperationalError
    leaves the session in a broken state, so this must run on every catch -
    including non-retryable errors and the final attempt - otherwise later
    operations in the same context raise InvalidRequestError. A rollback
    failure means the connection itself is broken: escalate to invalidate and
    report failure so the caller stops retrying on it.
    """
    if db is None:
        return True
    try:
        db.session.rollback()
        return True
    except SQLAlchemyError as rollback_exc:
        # A database-layer rollback failure means the connection itself is
        # broken; escalate to invalidate and tell the caller to stop
        # retrying on it.
        logger.warning(
            "retry_on_deadlock rollback failed: %s; invalidating session",
            rollback_exc,
        )
        invalidate_session(source="retry_on_deadlock rollback failure")
        return False
    except Exception as rollback_exc:  # noqa: BLE001 - best-effort cleanup
        # Environmental failures (e.g. no app context in unit tests) keep the
        # legacy tolerant behavior: log and let the retry loop proceed.
        logger.warning("retry_on_deadlock rollback failed: %s", rollback_exc)
        return True


def retry_on_deadlock(max_attempts: int = 3, backoff_seconds: float = 0.1):
    """
    Retry a transactional function when MySQL reports a deadlock (1213) or a
    lock wait timeout (1205). The failed transaction is rolled back on every
    caught error so the session is left clean; retryable errors are retried with
    exponential backoff plus jitter, while non-retryable errors and the final
    attempt propagate unchanged. Protocol-interrupt errors (2013/2014) mean the
    connection's response stream is desynced: the session is invalidated and
    the error propagates immediately - neither rollback nor retry is safe on
    that connection.
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
                    if is_protocol_interrupt_error(exc):
                        invalidate_session(
                            source="retry_on_deadlock protocol interrupt"
                        )
                        raise
                    if not _rollback_quietly():
                        raise
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

    # pool_pre_ping is OFF by default: the stock pre-ping runs before the
    # checkout event with no BaseException protection, so a gevent
    # interruption inside COM_PING leaks a permanently desynced connection
    # back to the pool (see _reject_desynced_connection_on_checkout, which
    # performs a protected ping instead). Callers can still opt back in by
    # pre-setting SQLALCHEMY_ENGINE_OPTIONS["pool_pre_ping"] = True.
    # NOTE: the protected checkout ping relies on the DBAPI connection
    # exposing ``ping`` (pymysql does). If this deployment ever switches to
    # a driver without it, re-enable pool_pre_ping explicitly or liveness
    # checking at checkout is silently lost.
    existing_options.setdefault("pool_pre_ping", False)

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
        db = SQLAlchemy(session_options={"scopefunc": _unique_app_ctx_scope})
    db.init_app(app)

    # Global last-resort guard: any interrupted path not covered by an
    # explicit termination handler still funnels through the app-context
    # teardown, where Flask-SQLAlchemy's remove() would roll back on the
    # possibly desynced connection. Flask runs teardown callbacks in
    # REVERSE registration order, so registering AFTER db.init_app makes
    # this run BEFORE the extension's session removal.
    @app.teardown_appcontext
    def _invalidate_session_on_interrupted_teardown(exc):
        if exc is not None and is_abnormal_stream_termination(exc):
            invalidate_session(source="appcontext teardown interrupt")

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
