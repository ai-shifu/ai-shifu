"""Read-only execution engine for creator-analytics queries.

If ``ANALYTICS_DATABASE_URI`` is set, a dedicated SQLAlchemy engine is built
against the read-only replica. Otherwise the primary application engine is
reused as a development / CI fallback, with a one-shot warning so production
deployments without the replica are still observable.

Use :func:`run_query` to execute the :class:`Select` produced by
:mod:`flaskr.service.creator_analytics.sql_builder`. The function returns a
plain ``{"columns": [...], "rows": [...]}`` dict suitable for the HTTP layer.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, Result
from sqlalchemy.sql import Select

from flaskr.dao import db


_FALLBACK_WARNED = False
_lock = threading.Lock()
_engine: Optional[Engine] = None
_engine_uri: Optional[str] = None


def get_analytics_engine(app: Flask) -> Engine:
    """Return the engine to use for creator-analytics DSL execution.

    A dedicated engine is built lazily from ``ANALYTICS_DATABASE_URI`` and
    cached for the process lifetime. When the URI is empty the primary
    Flask-SQLAlchemy engine is reused and a one-shot warning is emitted.
    """

    global _engine, _engine_uri, _FALLBACK_WARNED

    uri = (app.config.get("ANALYTICS_DATABASE_URI") or "").strip()

    if not uri:
        if not _FALLBACK_WARNED:
            app.logger.warning(
                "creator-analytics is falling back to the primary database; "
                "set ANALYTICS_DATABASE_URI to a read-only replica in production."
            )
            _FALLBACK_WARNED = True
        return db.engine

    with _lock:
        if _engine is None or _engine_uri != uri:
            pool_size = _coerce_int(app, "ANALYTICS_DATABASE_POOL_SIZE", 5)
            _engine = create_engine(
                uri,
                pool_size=pool_size,
                pool_pre_ping=True,
                future=True,
            )
            _engine_uri = uri
        return _engine


def run_query(app: Flask, stmt: Select) -> Dict[str, Any]:
    """Execute ``stmt`` against the analytics engine and return columns/rows."""

    engine = get_analytics_engine(app)
    with engine.connect() as connection:
        result: Result = connection.execute(stmt)
        columns = list(result.keys())
        rows: List[List[Any]] = [list(row) for row in result.fetchall()]
    return {"columns": columns, "rows": rows}


def reset_for_tests() -> None:
    """Clear the cached engine — used by the test suite between cases."""

    global _engine, _engine_uri, _FALLBACK_WARNED
    with _lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None
        _engine_uri = None
        _FALLBACK_WARNED = False


def _coerce_int(app: Flask, key: str, default: int) -> int:
    raw = app.config.get(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        app.logger.warning("Invalid %s=%r, falling back to %d", key, raw, default)
        return default
