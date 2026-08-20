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
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from flaskr.dao import db
from sqlalchemy import create_engine

if TYPE_CHECKING:
    from flask import Flask
    from sqlalchemy.engine import Engine, Result
    from sqlalchemy.sql import Select


@dataclass(slots=True)
class _AnalyticsEngineState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    engine: Engine | None = None
    uri: str | None = None
    fallback_warned: bool = False


_engine_state = _AnalyticsEngineState()


def get_analytics_engine(app: Flask) -> Engine:
    """Return the engine to use for creator-analytics DSL execution.

    A dedicated engine is built lazily from ``ANALYTICS_DATABASE_URI`` and
    cached for the process lifetime. When the URI is empty the primary
    Flask-SQLAlchemy engine is reused and a one-shot warning is emitted.
    """
    uri = (app.config.get("ANALYTICS_DATABASE_URI") or "").strip()

    if not uri:
        with _engine_state.lock:
            if not _engine_state.fallback_warned:
                app.logger.warning(
                    "creator-analytics is falling back to the primary database; "
                    "set ANALYTICS_DATABASE_URI to a read-only replica in production."
                )
                _engine_state.fallback_warned = True
        return db.engine

    with _engine_state.lock:
        if _engine_state.engine is None or _engine_state.uri != uri:
            pool_size = _coerce_int(app, "ANALYTICS_DATABASE_POOL_SIZE", 5)
            previous_engine = _engine_state.engine
            _engine_state.engine = create_engine(
                uri,
                pool_size=pool_size,
                pool_pre_ping=True,
                future=True,
            )
            _engine_state.uri = uri
            if previous_engine is not None:
                previous_engine.dispose()
        engine = _engine_state.engine
        if engine is None:  # pragma: no cover - guarded by the branch above
            raise RuntimeError("Analytics engine initialization failed")
        return engine


def run_query(app: Flask, stmt: Select) -> dict[str, Any]:
    """Execute ``stmt`` against the analytics engine and return columns/rows."""
    engine = get_analytics_engine(app)
    with engine.connect() as connection:
        result: Result = connection.execute(stmt)
        columns = list(result.keys())
        rows: list[list[Any]] = [list(row) for row in result.fetchall()]
    return {"columns": columns, "rows": rows}


def reset_for_tests() -> None:
    """Clear the cached engine — used by the test suite between cases."""
    with _engine_state.lock:
        if _engine_state.engine is not None:
            _engine_state.engine.dispose()
        _engine_state.engine = None
        _engine_state.uri = None
        _engine_state.fallback_warned = False


def _coerce_int(app: Flask, key: str, default: int) -> int:
    raw = app.config.get(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        app.logger.warning("Invalid %s=%r, falling back to %d", key, raw, default)
        return default
