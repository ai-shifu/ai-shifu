#!/usr/bin/env python3
"""Validate lesson comparisons on synthetic data in disposable local databases.

Run from src/api with its Python environment. SQLite is always tested; pass
--mysql-env .env to also test a local MySQL server. The configured database is
never modified: MySQL fixtures live in a uniquely named, disposable database.
Reported payload sizes exclude database protocol overhead. Timings are warm,
single-process measurements, not production capacity or latency estimates.
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
from typing import TYPE_CHECKING, Any

from flask import Flask, jsonify
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import URL, make_url

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from flask import Response
    from flask.testing import FlaskClient
    from flask_sqlalchemy import SQLAlchemy
    from sqlalchemy.engine import Engine


USER_BID = "benchmark-user"
SHIFU_BID = "benchmark-course"


@contextmanager
def disposable_database(mysql_env: Path | None) -> Iterator[URL | str]:
    """Create only an isolated fixture database, and always remove that database."""
    if mysql_env is None:
        with tempfile.TemporaryDirectory(prefix="lesson-comparison-") as directory:
            yield f"sqlite:///{Path(directory) / 'fixtures.sqlite'}"
        return

    from dotenv import dotenv_values

    configured = make_url(dotenv_values(mysql_env)["SQLALCHEMY_DATABASE_URI"])
    if configured.get_backend_name() != "mysql" or configured.host not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        message = "The benchmark only accepts a local MySQL server."
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
    database_name = f"lesson_compare_bench_{uuid.uuid4().hex}"
    created = False
    try:
        with admin.connect() as connection:
            connection.exec_driver_sql(
                # The identifier contains only this fixed prefix and generated hexadecimal.
                f"CREATE DATABASE `{database_name}` CHARACTER SET utf8mb4"
            )
            created = True
        yield admin_url.set(database=database_name)
    finally:
        if created:
            with admin.connect() as connection:
                connection.exec_driver_sql(
                    # This name belongs exclusively to the database created above.
                    f"DROP DATABASE `{database_name}`"
                )
        admin.dispose()


def prepare_app(database_url: URL | str) -> Flask:
    """Bind minimal Flask infrastructure without starting integrations or migrations."""
    from flaskr.dao import db
    from flaskr.service.learn.agent.models import LearnAgentSession
    from flaskr.service.shifu.models import DraftOutlineItem, PublishedOutlineItem
    from sqlalchemy.dialects.mysql import BIGINT
    from sqlalchemy.ext.compiler import compiles

    @compiles(BIGINT, "sqlite")
    def compile_bigint(_type: object, _compiler: object, **_kwargs: object) -> str:
        return "INTEGER"

    app = Flask("lesson-comparison-benchmark")
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"hide_parameters": True}
    db.init_app(app)
    with app.app_context(), db.engine.begin() as connection:
        # Explicitly create only the three declared fixture tables in the disposable DB.
        for model in (LearnAgentSession, DraftOutlineItem, PublishedOutlineItem):
            model.__table__.create(connection, checkfirst=False)
    return app


def session_document(body: object, target_bytes: int = 0) -> str:
    """Build a valid JSON snapshot with a synthetic message of the desired size."""
    document = {"script": {"script": body}, "messages": [{"content": ""}]}
    base_size = len(json.dumps(document, ensure_ascii=False).encode())
    document["messages"][0]["content"] = "x" * max(0, target_bytes - base_size)
    return json.dumps(document, ensure_ascii=False)


def install_fixtures(
    cases: list[dict[str, Any]],
    *,
    preview_mode: bool,
    distractors: int = 0,
    retired_sessions: int = 0,
) -> dict[str, int]:
    """Replace synthetic rows using explicit transactions on the disposable DB."""
    from flaskr.dao import db
    from flaskr.service.learn.agent.models import LearnAgentSession, active_key_for
    from flaskr.service.shifu.models import DraftOutlineItem, PublishedOutlineItem

    model = DraftOutlineItem if preview_mode else PublishedOutlineItem
    outlines, sessions = [], []
    for index, case in enumerate(cases, start=1):
        bid = f"outline-{index:03d}"
        outlines.append(
            {
                "id": index,
                "outline_item_bid": bid,
                "shifu_bid": SHIFU_BID,
                "content": case["current"],
                "deleted": 0,
            }
        )
        sessions.append(
            {
                "id": index,
                "agent_session_bid": f"session-{index:03d}",
                "user_bid": USER_BID,
                "shifu_bid": SHIFU_BID,
                "outline_item_bid": bid,
                "active_key": active_key_for(USER_BID, bid, preview_mode=preview_mode),
                "session_data": case["document"],
                "schema_version": case.get("schema_version", 1),
                "finished": 1,
                "deleted": case.get("deleted", 0),
            }
        )
    outline_ids = {item["outline_item_bid"]: item["id"] for item in outlines}
    for index in range(distractors):
        bid = f"other-outline-{index:04d}"
        outlines.append(
            {
                **outlines[0],
                "id": 10000 + index,
                "outline_item_bid": bid,
                "content": "other",
            }
        )
        sessions.append(
            {
                **sessions[0],
                "id": 10000 + index,
                "agent_session_bid": f"other-session-{index:04d}",
                "user_bid": "another-benchmark-user",
                "outline_item_bid": bid,
                "active_key": active_key_for(
                    "another-benchmark-user", bid, preview_mode=preview_mode
                ),
                "session_data": session_document("other"),
            }
        )
    retired_document = session_document("retired", 100 * 1024)
    invalid_document = "{broken" + "x" * (100 * 1024 - len("{broken"))
    target_bids = list(outline_ids)
    for index in range(retired_sessions):
        sessions.append(
            {
                **sessions[0],
                "id": 20000 + index,
                "agent_session_bid": f"retired-session-{index:04d}",
                "outline_item_bid": target_bids[index % len(target_bids)],
                "active_key": None,
                "deleted": 1,
                "session_data": retired_document if index % 2 else invalid_document,
            }
        )
    db.session.remove()
    with db.engine.begin() as connection:
        for table in (LearnAgentSession.__table__, model.__table__):
            connection.execute(table.delete())
        connection.execute(model.__table__.insert(), outlines)
        connection.execute(LearnAgentSession.__table__.insert(), sessions)
    return outline_ids


def validate_semantics() -> dict[str, int]:
    """Check normalization, exact comparison, and invalid snapshots on both surfaces."""
    from flaskr.service.learn.lesson_content_updates import load_lesson_content_states

    cases = [
        {
            "name": name,
            "current": current,
            "document": session_document(old),
            "changed": changed,
            "started": True,
        }
        for name, old, current, changed in (
            ("identical", "same", "same", False),
            ("same_length", "old", "new", True),
            ("case", "Title", "title", True),
            ("accent", "café", "cafe", True),
            ("trailing_space", "body", "body ", True),
            ("crlf", "line\r\nnext", "line\nnext", False),
            ("bare_cr", "line\rnext", "line\nnext", False),
            ("cleared_body", "body", "", True),
            ("literal_null", "null", "null", False),
            ("nul_character", "a\x00b", "a\x00c", True),
        )
    ]
    cases.extend(
        {"name": name, "current": "body", "document": document, "changed": False}
        for name, document in (
            ("malformed", "{broken"),
            ("empty_document", ""),
            ("root_array", "[]"),
            ("missing_body", '{"messages":[{}]}'),
            ("numeric_body", session_document(123)),
            ("null_body", session_document(None)),
            ("empty_messages", '{"script":{"script":"old"},"messages":[]}'),
            ("object_messages", '{"script":{"script":"old"},"messages":{"x":1}}'),
            ("null_messages", '{"script":{"script":"old"},"messages":null}'),
            ("true_messages", '{"script":{"script":"old"},"messages":true}'),
            ("false_messages", '{"script":{"script":"old"},"messages":false}'),
            ("number_messages", '{"script":{"script":"old"},"messages":1}'),
            ("string_messages", '{"script":{"script":"old"},"messages":"text"}'),
        )
    )
    cases.extend(
        [
            {
                "name": "unknown_schema",
                "current": "new",
                "document": session_document("old"),
                "schema_version": 99,
                "changed": False,
            },
            {
                "name": "deleted",
                "current": "new",
                "document": session_document("old"),
                "deleted": 1,
                "changed": False,
            },
        ]
    )
    for preview_mode in (False, True):
        outlines = install_fixtures(cases, preview_mode=preview_mode)
        states = load_lesson_content_states(
            user_bid=USER_BID,
            shifu_bid=SHIFU_BID,
            preview_mode=preview_mode,
            outline_ids=outlines,
        )
        for bid, case in zip(outlines, cases, strict=True):
            state = states.get(bid)
            actual = bool(state and state.has_content_update)
            if (
                actual != case["changed"]
                or bool(state and state.started) != case.get("started", False)
                or bool(state and state.finished) != case.get("started", False)
            ):
                message = f"Semantic mismatch: {case['name']}, preview={preview_mode}"
                raise AssertionError(message)
        other_surface = load_lesson_content_states(
            user_bid=USER_BID,
            shifu_bid=SHIFU_BID,
            preview_mode=not preview_mode,
            outline_ids=outlines,
        )
        if other_surface:
            message = "A baseline was visible in the other learning surface."
            raise AssertionError(message)
    return {"cases_per_surface": len(cases), "surfaces": 2}


def baseline_reader(outlines: dict[str, int]) -> dict[str, bool]:
    """Model the rejected approach: transfer and parse every complete session."""
    from flaskr.dao import db
    from flaskr.service.learn.agent.models import LearnAgentSession, active_key_for
    from flaskr.service.shifu.models import PublishedOutlineItem

    rows = db.session.execute(
        select(
            LearnAgentSession.outline_item_bid,
            LearnAgentSession.session_data,
            PublishedOutlineItem.content,
        )
        .join(
            PublishedOutlineItem,
            PublishedOutlineItem.outline_item_bid == LearnAgentSession.outline_item_bid,
        )
        .where(
            LearnAgentSession.active_key.in_(
                [active_key_for(USER_BID, bid) for bid in outlines]
            ),
            PublishedOutlineItem.id.in_(outlines.values()),
            LearnAgentSession.deleted == 0,
        )
    ).all()
    return {
        bid: json.loads(document)["script"]["script"]
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        != current.replace("\r\n", "\n").replace("\r", "\n")
        for bid, document, current in rows
    }


def payload_bytes(rows: list[object]) -> int:
    """Count UTF-8 value bytes, deliberately excluding wire framing and metadata."""
    return sum(
        len(value if isinstance(value, bytes) else str(value).encode())
        for row in rows
        for value in row
        if value is not None
    )


def measure(
    operation: Callable[[], object], *, db: SQLAlchemy, iterations: int
) -> dict:
    """Measure latency separately from allocation tracing, then inspect captured SQL."""
    for _ in range(2):
        operation()
    samples = []
    statements = []

    def capture(
        _connection: object,
        _cursor: object,
        statement: str,
        parameters: object,
        _context: object,
        _executemany: bool,
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
    tracemalloc.start()
    operation()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    first_statement, parameters = statements[0]
    with db.engine.connect() as connection:
        rows = connection.exec_driver_sql(first_statement, parameters).fetchall()
        explain_prefix = (
            "EXPLAIN QUERY PLAN " if db.engine.dialect.name == "sqlite" else "EXPLAIN "
        )
        explanation = connection.exec_driver_sql(
            explain_prefix + first_statement, parameters
        )
        plan = [dict(row) for row in explanation.mappings()]
    return {
        "query_count_per_call": len(statements) / iterations,
        "rows_returned": len(rows),
        "returned_value_bytes": payload_bytes(rows),
        "python_peak_bytes": peak,
        "p50_ms": round(statistics.median(samples), 3),
        "p95_ms": round(
            statistics.quantiles(samples, n=100, method="inclusive")[94], 3
        ),
        "explain": plan,
    }


def measure_synthetic_endpoint(client: FlaskClient, *, iterations: int) -> dict:
    """Time an in-process HTTP route, including JSON serialization but no real network."""
    samples = []
    response_bytes = 0
    for index in range(iterations + 2):
        started = time.perf_counter()
        response = client.get("/benchmark/lesson-content-updates")
        elapsed = (time.perf_counter() - started) * 1000
        if response.status_code != 200:
            message = "The synthetic comparison endpoint failed."
            raise AssertionError(message)
        response_bytes = len(response.data)
        if index >= 2:
            samples.append(elapsed)
    return {
        "p50_ms": round(statistics.median(samples), 3),
        "p95_ms": round(
            statistics.quantiles(samples, n=100, method="inclusive")[94], 3
        ),
        "response_body_bytes": response_bytes,
    }


def benchmark_database(database_url: URL | str, *, iterations: int) -> dict:
    """Run correctness checks and a small matrix of realistic large session documents."""
    from flaskr.dao import db
    from flaskr.service.learn.lesson_content_updates import load_lesson_content_states

    app = prepare_app(database_url)
    requested_outlines: dict[str, int] = {}

    @app.get("/benchmark/lesson-content-updates")
    def comparison_endpoint() -> Response:
        states = load_lesson_content_states(
            user_bid=USER_BID,
            shifu_bid=SHIFU_BID,
            preview_mode=False,
            outline_ids=requested_outlines,
        )
        return jsonify(
            {
                bid: {
                    "started": state.started,
                    "finished": state.finished,
                    "has_content_update": state.has_content_update,
                }
                for bid, state in states.items()
            }
        )

    client = app.test_client()
    try:
        with app.app_context():
            engine: Engine = db.engine
            version_sql = (
                "SELECT sqlite_version()"
                if engine.dialect.name == "sqlite"
                else "SELECT VERSION()"
            )
            with engine.connect() as connection:
                version = connection.exec_driver_sql(version_sql).scalar_one()
            report = {
                "dialect": engine.dialect.name,
                "version": version,
                "semantics": validate_semantics(),
                "scenarios": [],
            }
            for count, body_bytes, session_bytes in (
                (10, 7 * 1024, 100 * 1024),
                (100, 7 * 1024, 100 * 1024),
                (10, 30 * 1024, 1024 * 1024),
                (100, 30 * 1024, 1024 * 1024),
            ):
                print(
                    f"Benchmark {engine.dialect.name}: {count} sessions, "
                    f"{body_bytes} body bytes, {session_bytes} document bytes",
                    file=sys.stderr,
                    flush=True,
                )
                body = "a" * body_bytes
                cases = [
                    {
                        "current": body
                        if index % 3 == 0
                        else ("b" + body[1:] if index % 3 == 1 else body + "b"),
                        "document": session_document(body, session_bytes),
                    }
                    for index in range(count)
                ]
                outlines = install_fixtures(
                    cases, preview_mode=False, distractors=1000, retired_sessions=1000
                )
                requested_outlines.clear()
                requested_outlines.update(outlines)

                projected = partial(
                    load_lesson_content_states,
                    user_bid=USER_BID,
                    shifu_bid=SHIFU_BID,
                    preview_mode=False,
                    outline_ids=outlines,
                )

                projected_states = projected()
                baseline_states = baseline_reader(outlines)
                if any(
                    projected_states[bid].has_content_update != changed
                    for bid, changed in baseline_states.items()
                ):
                    message = "Projected and full-session comparison results differ."
                    raise AssertionError(message)
                report["scenarios"].append(
                    {
                        "sessions": count,
                        "body_bytes": body_bytes,
                        "session_document_bytes": session_bytes,
                        "distractor_sessions": 1000,
                        "retired_sessions": 1000,
                        "retired_session_document_bytes": 100 * 1024,
                        "projected": measure(projected, db=db, iterations=iterations),
                        "full_session_baseline": measure(
                            partial(baseline_reader, outlines),
                            db=db,
                            iterations=iterations,
                        ),
                        "synthetic_http_endpoint": measure_synthetic_endpoint(
                            client, iterations=iterations
                        ),
                    }
                )
            return report
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()


def main() -> None:
    """Print only synthetic measurements; never print credentials or original DB names."""
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
        with disposable_database(environment) as database_url:
            reports.append(benchmark_database(database_url, iterations=args.iterations))
    print(
        json.dumps({"warm_iterations": args.iterations, "databases": reports}, indent=2)
    )


if __name__ == "__main__":
    main()
