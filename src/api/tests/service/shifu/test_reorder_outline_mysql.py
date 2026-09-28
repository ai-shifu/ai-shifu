"""Exercise real MySQL repeatable-read snapshots in an isolated local schema.

Run from src/api (never point this test at an existing application schema)::

    RUN_LOCAL_MYSQL_REORDER_TESTS=1 \
    MYSQL_REORDER_TEST_ADMIN_URI=mysql+pymysql://root@127.0.0.1:3306 \
    python -m pytest tests/service/shifu/test_reorder_outline_mysql.py -q

The explicit opt-in accepts only loopback servers. Each test creates a random
schema containing three model tables and drops only that schema in its finalizer.
"""

from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING

import pytest
from flask import Flask
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.shifu import shifu_outline_funcs as outlines
from flaskr.service.shifu.models import DraftOutlineItem, DraftShifu, LogDraftStruct
from flaskr.service.shifu.outline_write_lock import lock_shifu_for_outline_write
from flaskr.service.shifu.shifu_history_manager import HistoryItem, get_shifu_history
from flaskr.service.shifu.shifu_outline_funcs import reorder_outline_siblings
from sqlalchemy import create_engine, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

if TYPE_CHECKING:
    from collections.abc import Iterator

COURSE_BID = "mysql-reorder-course"


@pytest.fixture
def mysql_reorder_app() -> Iterator[Flask]:
    if os.getenv("RUN_LOCAL_MYSQL_REORDER_TESTS") != "1":
        pytest.skip("Set RUN_LOCAL_MYSQL_REORDER_TESTS=1 for local MySQL coverage")
    uri = os.getenv("MYSQL_REORDER_TEST_ADMIN_URI")
    if not uri:
        pytest.fail("MYSQL_REORDER_TEST_ADMIN_URI must name a local MySQL server")
    url = make_url(uri)
    if (
        not url.drivername.startswith("mysql")
        or url.host not in {"127.0.0.1", "localhost", "::1"}
        or url.database
    ):
        pytest.fail("Use a loopback MySQL admin URI without a database name")

    schema = f"ai_shifu_reorder_test_{uuid.uuid4().hex}"
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
            for model in (DraftShifu, DraftOutlineItem, LogDraftStruct):
                model.__table__.create(db.engine)
            _seed_course()
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


def _seed_course() -> None:
    course = DraftShifu(shifu_bid=COURSE_BID, title="Initial title", deleted=0)
    db.session.add(course)
    db.session.flush()
    nodes = {}
    roots = []
    for bid, parent, position in (
        ("chapter-a", "", "01"),
        ("a1", "chapter-a", "0101"),
        ("a2", "chapter-a", "0102"),
        ("chapter-b", "", "02"),
        ("b1", "chapter-b", "0201"),
        ("b2", "chapter-b", "0202"),
    ):
        row = DraftOutlineItem(
            shifu_bid=COURSE_BID,
            outline_item_bid=bid,
            parent_bid=parent,
            position=position,
            title=bid,
            content=f"Initial content for {bid}",
            llm_system_prompt="Initial teaching prompt",
            deleted=0,
        )
        db.session.add(row)
        db.session.flush()
        node = HistoryItem(bid=bid, id=row.id, type="outline")
        nodes[bid] = node
        (nodes[parent].children if parent else roots).append(node)
    nodes["b1"].children = [HistoryItem(bid="legacy-block", id=17, type="block")]
    history = HistoryItem(bid=COURSE_BID, id=course.id, type="shifu", children=roots)
    db.session.add(_history_row(history))
    db.session.commit()


def _history_row(history: HistoryItem) -> LogDraftStruct:
    return LogDraftStruct(
        struct_bid=uuid.uuid4().hex,
        shifu_bid=COURSE_BID,
        struct=history.to_json(),
    )


def _history_nodes(root: HistoryItem) -> dict[str, HistoryItem]:
    result = {}
    pending = list(root.children)
    while pending:
        node = pending.pop()
        result[node.bid] = node
        pending.extend(node.children)
    return result


def _latest_items() -> dict[str, DraftOutlineItem]:
    result = {}
    for row in (
        DraftOutlineItem.query.filter_by(shifu_bid=COURSE_BID)
        .order_by(DraftOutlineItem.id.desc())
        .all()
    ):
        result.setdefault(row.outline_item_bid, row)
    return result


def _latest_history_row() -> LogDraftStruct:
    return (
        LogDraftStruct.query.filter_by(shifu_bid=COURSE_BID)
        .order_by(LogDraftStruct.id.desc())
        .first()
    )


def _connection_id() -> int:
    return db.session.execute(text("SELECT CONNECTION_ID()")).scalar_one()


def test_old_snapshot_merges_other_group_and_latest_content_history(
    mysql_reorder_app: Flask,
) -> None:
    app = mysql_reorder_app
    with app.app_context():
        assert db.session.execute(
            text("SELECT @@transaction_isolation")
        ).scalar_one() == ("REPEATABLE-READ")
        connection_a = _connection_id()
        cached = _latest_items()
        old_history = _latest_history_row()
        old_history_id = old_history.id

        # Separate app contexts provide independent real connections/transactions.
        with app.app_context():
            assert _connection_id() != connection_a
            reorder_outline_siblings(app, "writer-b", COURSE_BID, ["b2", "b1"])
            other_versions = {bid: _latest_items()[bid].id for bid in ("b1", "b2")}
            content = _latest_items()["a2"].clone()
            content.content = "Latest content from writer B"
            content.llm_system_prompt = "Latest teaching prompt"
            content.title = "Latest lesson title"
            course = DraftShifu.query.filter_by(shifu_bid=COURSE_BID).first().clone()
            course.title = "Latest course title"
            db.session.add_all([content, course])
            db.session.flush()
            latest_content_id, latest_course_id = content.id, course.id
            history = get_shifu_history(app, COURSE_BID)
            history.id = course.id
            nodes = _history_nodes(history)
            nodes["a2"].id = content.id
            nodes["legacy-block"].id = 99
            db.session.add(_history_row(history))
            db.session.commit()

        # Prove A still has a real old RR snapshot, not merely a stale Python value.
        assert _connection_id() == connection_a
        assert _latest_history_row().id == old_history_id
        assert (
            db.session.query(DraftOutlineItem.id)
            .filter_by(id=latest_content_id)
            .first()
            is None
        )
        assert cached["a2"].content == "Initial content for a2"

        reorder_outline_siblings(app, "writer-a", COURSE_BID, ["a2", "a1"])
        current = _latest_items()
        assert current["a2"].position == "0101"
        assert current["a1"].position == "0102"
        assert current["a2"].content == "Latest content from writer B"
        assert current["a2"].title == "Latest lesson title"
        assert current["a2"].llm_system_prompt == "Latest teaching prompt"
        assert {bid: current[bid].id for bid in other_versions} == other_versions
        assert current["b2"].position == "0201"
        assert current["b1"].position == "0202"
        saved = get_shifu_history(app, COURSE_BID)
        nodes = _history_nodes(saved)
        assert saved.id == latest_course_id
        assert db.session.get(DraftShifu, saved.id).title == "Latest course title"
        assert nodes["legacy-block"].id == 99
        assert [node.bid for node in nodes["chapter-b"].children] == ["b2", "b1"]
        assert [node.bid for node in nodes["chapter-a"].children] == ["a2", "a1"]
        assert all(nodes[bid].id == row.id for bid, row in current.items())


def test_locking_reads_refresh_same_id_identity_map_entries(
    mysql_reorder_app: Flask,
) -> None:
    app = mysql_reorder_app
    with app.app_context():
        connection_a = _connection_id()
        cached = _latest_items()["a2"]
        cached_history = _latest_history_row()
        changed_history = HistoryItem.from_json(cached_history.struct)
        changed_history.id = 1234
        _history_nodes(changed_history)["legacy-block"].id = 99

        with app.app_context():
            assert _connection_id() != connection_a
            db.session.execute(
                update(DraftOutlineItem.__table__)
                .where(DraftOutlineItem.id == cached.id)
                .values(content="Updated same row", llm_system_prompt="Updated prompt")
            )
            db.session.execute(
                update(LogDraftStruct.__table__)
                .where(LogDraftStruct.id == cached_history.id)
                .values(struct=changed_history.to_json())
            )
            db.session.commit()

        assert cached.content == "Initial content for a2"
        assert HistoryItem.from_json(cached_history.struct).id != 1234
        assert (
            db.session.query(DraftOutlineItem.content).filter_by(id=cached.id).scalar()
            == "Initial content for a2"
        )
        reorder_outline_siblings(app, "writer-a", COURSE_BID, ["a2", "a1"])
        current = _latest_items()["a2"]
        assert current.content == "Updated same row"
        assert current.llm_system_prompt == "Updated prompt"
        history = get_shifu_history(app, COURSE_BID)
        assert history.id == 1234
        assert _history_nodes(history)["legacy-block"].id == 99


def test_history_rows_remain_writable_while_current_rows_are_locked(
    mysql_reorder_app: Flask,
) -> None:
    app = mysql_reorder_app
    with app.app_context():
        initial = _latest_items()["a2"]
        versions = [initial.clone() for _ in range(200)]
        db.session.add_all(versions)
        db.session.flush()
        historical_id, current_id = versions[99].id, versions[-1].id
        db.session.commit()

        with unit_of_work():
            lock_shifu_for_outline_write(COURSE_BID)
            current = outlines._load_current_outline_items_for_reorder(COURSE_BID)
            assert (
                next(row.id for row in current if row.outline_item_bid == "a2")
                == current_id
            )
            # A second connection can edit interior history, but not current rows.
            with app.app_context():
                db.session.execute(text("SET SESSION innodb_lock_wait_timeout=1"))
                db.session.execute(
                    update(DraftOutlineItem.__table__)
                    .where(DraftOutlineItem.id == historical_id)
                    .values(content="Historical revision remains writable")
                )
                db.session.commit()
                with pytest.raises(OperationalError) as locked:
                    db.session.execute(
                        text(
                            "SELECT id FROM shifu_draft_outline_items "
                            "WHERE id=:row_id FOR UPDATE NOWAIT"
                        ),
                        {"row_id": current_id},
                    )
                assert locked.value.orig.args[0] == 3572
