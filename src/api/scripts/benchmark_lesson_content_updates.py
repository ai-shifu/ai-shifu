#!/usr/bin/env python3
"""Benchmark revision comparisons in disposable SQLite and local MySQL databases.

Run from src/api; pass --mysql-env .env to also test local MySQL. The configured
DB is never altered. Results cover the comparison helper, not production HTTP
latency. Returned-value sizes exclude database protocol overhead.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
import tracemalloc
import uuid
from argparse import ArgumentParser
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from flask import Flask
from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL, make_url

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

USER_BID = "benchmark-user"
SHIFU_BID = "benchmark-course"


@contextmanager
def disposable_database(mysql_env: Path | None) -> Iterator[URL | str]:
    """Create and remove only this invocation's isolated fixture database."""
    if mysql_env is None:
        with tempfile.TemporaryDirectory(prefix="lesson-revision-") as directory:
            yield f"sqlite:///{Path(directory) / 'fixtures.sqlite'}"
        return
    from dotenv import dotenv_values

    configured = make_url(dotenv_values(mysql_env)["SQLALCHEMY_DATABASE_URI"])
    if configured.get_backend_name() != "mysql" or configured.host not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        message = "Only a local MySQL server is allowed."
        raise ValueError(message)
    admin_url = URL.create(
        "mysql+pymysql",
        username=configured.username,
        password=configured.password,
        host=configured.host,
        port=configured.port,
        query=configured.query,
    )
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", hide_parameters=True)
    name = f"lesson_revision_bench_{uuid.uuid4().hex}"
    created = False
    try:
        with admin.connect() as connection:
            # The identifier contains only a fixed prefix and generated hexadecimal.
            connection.exec_driver_sql(f"CREATE DATABASE {name} CHARACTER SET utf8mb4")
            created = True
        yield admin_url.set(database=name)
    finally:
        if created:
            with admin.connect() as connection:
                connection.exec_driver_sql(f"DROP DATABASE {name}")
        admin.dispose()


def prepare_app(database_url: URL | str) -> Flask:
    """Initialize only the declared session table, without app startup or migrations."""
    from flaskr.dao import db
    from flaskr.service.learn.agent.models import LearnAgentSession
    from sqlalchemy.dialects.mysql import BIGINT
    from sqlalchemy.ext.compiler import compiles

    @compiles(BIGINT, "sqlite")
    def compile_bigint(_type: object, _compiler: object, **_kwargs: object) -> str:
        return "INTEGER"

    app = Flask("lesson-revision-benchmark")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=database_url,
        SQLALCHEMY_ENGINE_OPTIONS={"hide_parameters": True},
    )
    db.init_app(app)
    with app.app_context(), db.engine.begin() as connection:
        LearnAgentSession.__table__.create(connection, checkfirst=False)
    return app


def install_fixtures(count: int, history_bytes: int) -> dict[str, int]:
    """Store target sessions plus 1,000 other-user and 1,000 retired-session rows."""
    from flaskr.dao import db
    from flaskr.service.learn.agent.models import LearnAgentSession, active_key_for

    bids = [f"outline-{index:03d}" for index in range(count)]
    history = json.dumps({"history": "x" * max(0, history_bytes - 15)})
    rows = [
        {
            "id": index + 1,
            "agent_session_bid": f"session-{index}",
            "user_bid": USER_BID,
            "shifu_bid": SHIFU_BID,
            "outline_item_bid": bid,
            "active_key": active_key_for(USER_BID, bid),
            "content_revision": (10, 10, None, 0)[index % 4],
            "session_data": history,
            "schema_version": 1,
            "turn": 1,
            "finished": 1,
            "deleted": 0,
        }
        for index, bid in enumerate(bids)
    ]
    for index in range(1000):
        rows.extend(
            [
                {
                    **rows[0],
                    "id": 10000 + index,
                    "agent_session_bid": f"other-{index}",
                    "user_bid": "other-user",
                    "outline_item_bid": f"other-{index}",
                    "active_key": active_key_for("other-user", f"other-{index}"),
                    "session_data": "{}",
                },
                {
                    **rows[0],
                    "id": 20000 + index,
                    "agent_session_bid": f"retired-{index}",
                    "outline_item_bid": bids[index % count],
                    "active_key": None,
                    "deleted": 1,
                    "session_data": "{retired",
                },
            ]
        )
    db.session.remove()
    with db.engine.begin() as connection:
        connection.execute(LearnAgentSession.__table__.delete())
        connection.execute(LearnAgentSession.__table__.insert(), rows)
        if db.engine.dialect.name == "sqlite":
            connection.exec_driver_sql("ANALYZE learn_agent_sessions")
    return {bid: 10 + index % 2 for index, bid in enumerate(bids)}


def measure(operation: Callable[[], object], *, iterations: int) -> dict:
    """Verify one small SELECT and measure latency, allocation, result size and plan."""
    from flaskr.dao import db

    for _ in range(2):
        operation()
    statements, samples = [], []

    def capture(
        _conn: object,
        _cursor: object,
        statement: str,
        parameters: object,
        _context: object,
        _many: bool,
    ) -> None:
        statements.append((statement, parameters))

    event.listen(db.engine, "before_cursor_execute", capture)
    try:
        for _ in range(iterations):
            started = time.perf_counter()
            operation()
            samples.append((time.perf_counter() - started) * 1000)
    finally:
        event.remove(db.engine, "before_cursor_execute", capture)
    if len(statements) != iterations or any(
        token in statement.lower()
        for statement, _ in statements
        for token in (
            "session_data",
            "json_",
            "shifu_draft_outline",
            "shifu_published_outline",
        )
    ):
        message = "Expected one metadata SELECT without JSON or lesson-body access."
        raise AssertionError(message)
    tracemalloc.start()
    operation()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    statement, parameters = statements[0]
    with db.engine.connect() as connection:
        result = connection.exec_driver_sql(statement, parameters)
        columns, rows = list(result.keys()), result.fetchall()
        prefix = (
            "EXPLAIN QUERY PLAN " if db.engine.dialect.name == "sqlite" else "EXPLAIN "
        )
        plan = list(
            connection.exec_driver_sql(prefix + statement, parameters).mappings()
        )
    return {
        "queries_per_call": 1,
        "columns": columns,
        "rows_returned": len(rows),
        "returned_value_bytes": sum(
            len(str(value).encode())
            for row in rows
            for value in row
            if value is not None
        ),
        "python_peak_bytes": peak,
        "p50_ms": round(statistics.median(samples), 3),
        "p95_ms": round(
            statistics.quantiles(samples, n=100, method="inclusive")[94], 3
        ),
        "active_key_index_used": "uq_learn_agent_sessions_active" in str(plan),
        "explain": [dict(row) for row in plan],
    }


def benchmark(database_url: URL | str, *, iterations: int) -> dict:
    """Compare equal batch sizes with small and large unused history documents."""
    from flaskr.dao import db
    from flaskr.service.learn.lesson_content_updates import load_lesson_content_states

    app = prepare_app(database_url)
    try:
        with app.app_context():
            dialect = db.engine.dialect.name
            with db.engine.connect() as connection:
                version = connection.exec_driver_sql(
                    "SELECT sqlite_version()"
                    if dialect == "sqlite"
                    else "SELECT VERSION()"
                ).scalar_one()
            report = {"dialect": dialect, "version": version, "scenarios": []}
            for count, size in (
                (10, 100 * 1024),
                (100, 100 * 1024),
                (10, 1024 * 1024),
                (100, 1024 * 1024),
            ):
                print(
                    f"Benchmark {dialect}: {count} sessions, {size} history bytes",
                    file=sys.stderr,
                    flush=True,
                )
                revisions = install_fixtures(count, size)
                operation = partial(
                    load_lesson_content_states,
                    user_bid=USER_BID,
                    shifu_bid=SHIFU_BID,
                    preview_mode=False,
                    outline_revisions=revisions,
                )
                states = operation()
                if set(states) != set(revisions) or any(
                    states[bid].has_content_update != (index % 4 == 1)
                    for index, bid in enumerate(revisions)
                ):
                    message = "Unexpected revision flags or session scope."
                    raise AssertionError(message)
                result = measure(operation, iterations=iterations)
                report["scenarios"].append(
                    {
                        "sessions": count,
                        "history_bytes": size,
                        "other_user_sessions": 1000,
                        "retired_sessions": 1000,
                        **result,
                    }
                )
            return report
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()


def main() -> None:
    """Print only synthetic fixture measurements, never connection credentials."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--mysql-env", type=Path)
    parser.add_argument("--iterations", type=int, default=7)
    args = parser.parse_args()
    if args.iterations < 2:
        parser.error("--iterations must be at least 2")
    os.environ["SKIP_LOAD_DOTENV"] = "1"
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    reports = []
    for environment in [None, args.mysql_env] if args.mysql_env else [None]:
        with disposable_database(environment) as url:
            reports.append(benchmark(url, iterations=args.iterations))
    print(
        json.dumps({"warm_iterations": args.iterations, "databases": reports}, indent=2)
    )


if __name__ == "__main__":
    main()
