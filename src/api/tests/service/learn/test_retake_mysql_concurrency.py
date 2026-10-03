"""Real MySQL concurrency on a randomly named, loopback-only test schema.

Run with RUN_LOCAL_MYSQL_RETAKE_TESTS=1 and MYSQL_RETAKE_TEST_ADMIN_URI
set to a loopback MySQL admin URI without a database name. The fixture applies
all three actual retake migrations and removes only its own random schema.
No application database or paid model/TTS service is used.
"""

from __future__ import annotations

import importlib.util
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import Flask
from flaskr.dao import db
from flaskr.service.learn.retake_ledger import (
    claim_attempt,
    configure_policy,
    finish_attempt,
    get_allowance,
    reserve_attempt,
)
from flaskr.service.learn.retake_models import CourseRetakePolicy, LessonRetakeAttempt
from flaskr.service.learn.retake_policy import RetakeRuleError
from flaskr.service.learn.retake_run_guard import acquire_lesson_run, release_lesson_run
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

if TYPE_CHECKING:
    from collections.abc import Iterator

BASE = {"namespace": "mysql-test", "shifu_bid": "course"}
IDENTITY = {**BASE, "user_bid": "learner", "outline_bid": "lesson"}
MIGRATIONS = [
    "0a3b9866d338_add_deployment_scoped_lesson_retake_.py",
    "48efe7c245af_record_retake_recovery_and_producer_.py",
    "f5c8745b7e91_guard_active_lesson_producers_during_.py",
]


@pytest.fixture
def mysql_retake_app() -> Iterator[Flask]:
    if os.getenv("RUN_LOCAL_MYSQL_RETAKE_TESTS") != "1":
        pytest.skip("Set RUN_LOCAL_MYSQL_RETAKE_TESTS=1 for local MySQL coverage")
    uri = os.getenv("MYSQL_RETAKE_TEST_ADMIN_URI")
    if not uri:
        pytest.fail("MYSQL_RETAKE_TEST_ADMIN_URI must name a local MySQL server")
    url = make_url(uri)
    if (
        not url.drivername.startswith("mysql")
        or url.host not in {"127.0.0.1", "localhost", "::1"}
        or url.database
    ):
        pytest.fail("Use a loopback MySQL admin URI without a database name")

    schema = f"ai_shifu_retake_test_{uuid.uuid4().hex}"
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=url.set(database=schema),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={
            "isolation_level": "REPEATABLE READ",
            "connect_args": {
                "connect_timeout": 5,
                "init_command": "SET SESSION innodb_lock_wait_timeout=5",
            },
        },
    )
    created = False
    initialized = False
    try:
        with admin.connect() as connection:
            connection.execute(
                text(f"CREATE DATABASE `{schema}` CHARACTER SET utf8mb4")
            )
        created = True
        db.init_app(app)
        initialized = True
        with app.app_context():
            with (
                db.engine.begin() as connection,
                Operations.context(MigrationContext.configure(connection)),
            ):
                for name in MIGRATIONS:
                    path = (
                        Path(__file__).resolve().parents[3]
                        / "migrations/versions"
                        / name
                    )
                    spec = importlib.util.spec_from_file_location(name, path)
                    migration = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(migration)
                    migration.upgrade()
            configure_policy(app, **BASE, limit=1)
        yield app
    finally:
        try:
            if initialized:
                with app.app_context():
                    db.session.remove()
                    db.engine.dispose()
        finally:
            try:
                if created:
                    with admin.connect() as connection:
                        connection.execute(text(f"DROP DATABASE `{schema}`"))
            finally:
                admin.dispose()


@pytest.mark.parametrize("same_request", [False, True])
def test_concurrent_last_slot_and_idempotent_retry(
    mysql_retake_app: Flask, same_request: bool
) -> None:
    app = mysql_retake_app
    barrier = threading.Barrier(2)
    resets = []

    def attempt(index: int) -> tuple[str, str]:
        with app.app_context():
            assert LessonRetakeAttempt.query.count() == 0
            barrier.wait(timeout=10)

            def reset() -> dict:
                resets.append(index)
                return {"version": 1}

            try:
                bid, _ = reserve_attempt(
                    app,
                    **IDENTITY,
                    request_id="same" if same_request else str(index),
                    stage_reset=reset,
                )
            except RetakeRuleError as exc:
                return "blocked", str(exc)
            else:
                return "accepted", bid

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, (0, 1)))
    assert len(resets) == 1
    if same_request:
        assert results[0] == results[1]
    else:
        assert sorted(result[0] for result in results) == ["accepted", "blocked"]
        assert ("blocked", "retake_in_progress") in results
    with app.app_context():
        assert LessonRetakeAttempt.query.count() == 1
        assert get_allowance(app, **IDENTITY).reserved == 1


def test_stale_snapshot_cannot_admit_after_last_slot_is_spent(
    mysql_retake_app: Flask,
) -> None:
    app = mysql_retake_app
    ready = threading.Event()
    committed = threading.Event()

    def stale_request() -> str:
        with app.app_context():
            assert LessonRetakeAttempt.query.count() == 0
            ready.set()
            assert committed.wait(timeout=10)
            try:
                reserve_attempt(app, **IDENTITY, request_id="stale")
            except RetakeRuleError as exc:
                return str(exc)
            return "incorrectly admitted"

    with ThreadPoolExecutor(max_workers=1) as pool:
        stale = pool.submit(stale_request)
        assert ready.wait(timeout=10)
        bid, _ = reserve_attempt(app, **IDENTITY, request_id="winner")
        claim_attempt(app, **BASE, attempt_id=bid, producer_id="producer")
        finish_attempt(
            app,
            **BASE,
            attempt_id=bid,
            producer_id="producer",
            has_durable_content=True,
            producer_stopped=True,
        )
        committed.set()
        assert stale.result(timeout=10) == "retake_limit_reached"


def test_two_first_study_producers_cannot_own_the_same_lesson(
    mysql_retake_app: Flask,
) -> None:
    app = mysql_retake_app
    barrier = threading.Barrier(2)

    def acquire() -> object:
        with app.app_context():
            barrier.wait(timeout=10)
            try:
                return acquire_lesson_run(app, **IDENTITY)
            except RetakeRuleError as exc:
                return str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: acquire(), (0, 1)))
    assert results.count("retake_in_progress") == 1
    winner = next(result for result in results if not isinstance(result, str))
    with pytest.raises(RetakeRuleError, match="retake_in_progress"):
        reserve_attempt(app, **IDENTITY, request_id="reset")
    release_lesson_run(app, winner)
    reserve_attempt(app, **IDENTITY, request_id="reset")


def test_policy_reduction_overrides_an_existing_orm_snapshot(
    mysql_retake_app: Flask,
) -> None:
    app = mysql_retake_app
    ready = threading.Event()
    changed = threading.Event()

    def stale_request() -> str:
        with app.app_context():
            assert CourseRetakePolicy.query.one().lesson_limit == 1
            ready.set()
            assert changed.wait(timeout=10)
            try:
                reserve_attempt(app, **IDENTITY, request_id="stale-policy")
            except RetakeRuleError as exc:
                return str(exc)
            return "incorrectly admitted"

    with ThreadPoolExecutor(max_workers=1) as pool:
        stale = pool.submit(stale_request)
        assert ready.wait(timeout=10)
        configure_policy(app, **BASE, limit=0)
        changed.set()
        assert stale.result(timeout=10) == "retake_limit_reached"
