"""Verify source-version concurrency in an isolated local MySQL schema.

Opt in with RUN_LOCAL_MYSQL_SHARED_ANSWER_TESTS=1 and
MYSQL_SHARED_ANSWER_TEST_ADMIN_URI=mysql+pymysql://root@127.0.0.1:13316.
Only loopback admin URLs without an existing schema are accepted.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from flask import Flask
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.i18n import load_translations
from flaskr.service.profile.api import get_global_profile_keys
from flaskr.service.profile.models import Variable, VariableValue
from flaskr.service.profile.shared_answers import (
    load_shared_answers,
    stage_shared_answers,
)
from flaskr.service.shifu.models import DraftShifu, PublishedOutlineItem, PublishedShifu
from flaskr.service.user.models import AuthCredential, UserInfo
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def mysql_shared_app() -> Iterator[Flask]:
    if os.getenv("RUN_LOCAL_MYSQL_SHARED_ANSWER_TESTS") != "1":
        pytest.skip("Opt into the isolated local MySQL shared-answer tests")
    uri = os.getenv("MYSQL_SHARED_ANSWER_TEST_ADMIN_URI", "")
    url = make_url(uri)
    if (
        not url.drivername.startswith("mysql")
        or url.host not in {"127.0.0.1", "localhost", "::1"}
        or url.database
    ):
        pytest.fail("Use a loopback MySQL admin URL without a schema")
    schema = f"ai_shifu_shared_answer_test_{uuid4().hex}"
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
    created = initialized = False
    try:
        with admin.connect() as connection:
            connection.execute(
                text(f"CREATE DATABASE `{schema}` CHARACTER SET utf8mb4")
            )
        created = True
        db.init_app(app)
        initialized = True
        load_translations(app)
        with app.app_context():
            for model in (
                DraftShifu,
                PublishedShifu,
                PublishedOutlineItem,
                Variable,
                VariableValue,
                UserInfo,
                AuthCredential,
            ):
                model.__table__.create(db.engine)
            with unit_of_work():
                for course, other in (("a" * 32, "b" * 32), ("b" * 32, "a" * 32)):
                    alias = f"share:{other}:goal"
                    db.session.add_all(
                        [
                            DraftShifu(shifu_bid=course, created_user_bid="owner"),
                            PublishedShifu(shifu_bid=course, created_user_bid="owner"),
                            PublishedOutlineItem(
                                shifu_bid=course,
                                outline_item_bid=course,
                                content=f"Collect %{{{{{alias}}}}}.",
                            ),
                            Variable(shifu_bid=course, key="goal"),
                            Variable(shifu_bid=course, key=alias),
                            VariableValue(
                                user_bid="learner",
                                shifu_bid=course,
                                key="goal",
                                value="Original",
                            ),
                        ]
                    )
                db.session.add(UserInfo(user_bid="learner", user_identify="learner"))
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


@pytest.mark.parametrize(
    "change", ["value", "delete", "owner", "publication", "definition"]
)
def test_locking_revalidation_sees_changes_after_a_repeatable_read_snapshot(
    mysql_shared_app: Flask, change: str
) -> None:
    app = mysql_shared_app
    target, source = "a" * 32, "b" * 32
    alias = f"share:{source}:goal"
    with app.app_context():
        expected = load_shared_answers(
            "learner",
            target,
            [alias],
            reserved=get_global_profile_keys(),
            outline_bid=target,
        )
        assert alias in expected

        def concurrent_change() -> None:
            with app.app_context(), unit_of_work():
                if change in {"value", "delete"}:
                    db.session.add(
                        VariableValue(
                            user_bid="learner",
                            shifu_bid=source,
                            key="goal",
                            value="Concurrent",
                            deleted=int(change == "delete"),
                        )
                    )
                elif change == "owner":
                    DraftShifu.query.filter_by(shifu_bid=source).update(
                        {DraftShifu.created_user_bid: "another-owner"}
                    )
                elif change == "publication":
                    db.session.add(
                        PublishedOutlineItem(
                            shifu_bid=target,
                            outline_item_bid=target,
                            content="Collection removed.",
                        )
                    )
                else:
                    Variable.query.filter_by(shifu_bid=source, key="goal").update(
                        {Variable.deleted: 1}
                    )

        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(concurrent_change).result(timeout=15)
        # The existing consistent-read snapshot still sees the old source version.
        assert (
            VariableValue.query.filter_by(shifu_bid=source)
            .order_by(VariableValue.id.desc())
            .first()
            .value
            == "Original"
        )
        with unit_of_work():
            assert not stage_shared_answers(
                app, "learner", target, target, {alias: "Stale"}, expected
            )
        assert VariableValue.query.filter_by(value="Stale").count() == 0


@pytest.mark.parametrize("opposing", [False, True])
def test_concurrent_writers_serialize_and_do_not_overwrite_changed_versions(
    mysql_shared_app: Flask, opposing: bool
) -> None:
    app = mysql_shared_app
    barrier = Barrier(2)

    def write(index: int) -> bool:
        target = ("b" if opposing and index else "a") * 32
        source = ("a" if opposing and index else "b") * 32
        alias = f"share:{source}:goal"
        with app.app_context():
            expected = load_shared_answers(
                "learner",
                target,
                [alias],
                reserved=get_global_profile_keys(),
                outline_bid=target,
            )
            barrier.wait(timeout=10)
            with unit_of_work():
                return bool(
                    stage_shared_answers(
                        app,
                        "learner",
                        target,
                        target,
                        {alias: f"Answer {index}"},
                        expected,
                    )
                )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(write, index) for index in range(2)]
        accepted = [future.result(timeout=20) for future in futures]
    assert sum(accepted) == (2 if opposing else 1)
    with app.app_context():
        assert VariableValue.query.filter(
            VariableValue.value.startswith("Answer ")
        ).count() == sum(accepted)
