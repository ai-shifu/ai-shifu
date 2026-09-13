"""Unit-of-work behavior for the B2 shifu call sites.

Covers the outline batch create (one transaction for the whole batch), the
shared-permission service functions moved out of the route, and the creator
transfer whose cache invalidation and post-auth chain now run post-commit.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest
from flaskr import dao
from flaskr.service.shifu import shifu_outline_funcs, shifu_permission_funcs
from flaskr.service.shifu.admin_operations import courses_transfer_copy
from flaskr.service.shifu.models import AiCourseAuth, DraftOutlineItem, DraftShifu
from flaskr.service.user.consts import USER_STATE_REGISTERED
from flaskr.service.user.repository import create_user_entity, upsert_credential


def _committed_rows(app: object, table: object, *conditions: object) -> list[object]:
    with app.app_context(), dao.db.engine.connect() as connection:
        return connection.execute(table.select().where(*conditions)).fetchall()


def _seed_draft(shifu_bid: str, creator_user_bid: str) -> None:
    dao.db.session.add(
        DraftShifu(
            shifu_bid=shifu_bid,
            title=f"UOW {shifu_bid[:6]}",
            description="desc",
            avatar_res_bid="",
            keywords="",
            llm="gpt-test",
            llm_temperature=Decimal(0),
            llm_system_prompt="",
            price=Decimal(0),
            created_user_bid=creator_user_bid,
            updated_user_bid=creator_user_bid,
        )
    )
    dao.db.session.commit()


def _seed_user(app: object, user_bid: str, email: str) -> None:
    create_user_entity(
        user_bid=user_bid,
        identify=email,
        nickname=f"user-{user_bid[:6]}",
        language="en-US",
        state=USER_STATE_REGISTERED,
    )
    dao.db.session.flush()
    upsert_credential(
        app,
        user_bid=user_bid,
        provider_name="email",
        subject_id=email,
        subject_format="email",
        identifier=email,
        metadata={},
        verified=True,
    )
    dao.db.session.commit()


def test_outline_batch_create_persists_nothing_when_a_later_node_fails(
    app: object, monkeypatch: object
) -> None:
    shifu_bid = uuid.uuid4().hex[:32]
    monkeypatch.setattr(
        shifu_outline_funcs, "check_text_with_risk_control", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        shifu_outline_funcs, "save_new_outline_history", lambda *_a, **_k: None
    )
    real_insert = shifu_outline_funcs.__insert_outline_locked
    calls = {"n": 0}

    def failing_second_insert(*args: object, **kwargs: object) -> object:
        calls["n"] += 1
        if calls["n"] == 2:
            message = "second node boom"
            raise RuntimeError(message)
        return real_insert(*args, **kwargs)

    monkeypatch.setattr(
        shifu_outline_funcs, "__insert_outline_locked", failing_second_insert
    )

    with app.app_context():
        _seed_draft(shifu_bid, "uow-outline-owner")
        with pytest.raises(RuntimeError, match="second node boom"):
            shifu_outline_funcs.create_outlines_batch(
                app,
                "uow-outline-owner",
                shifu_bid,
                [{"name": "Chapter 1"}, {"name": "Chapter 2"}],
            )

    rows = _committed_rows(
        app, DraftOutlineItem.__table__, DraftOutlineItem.shifu_bid == shifu_bid
    )
    assert rows == []


def test_outline_batch_create_commits_all_nodes_together(
    app: object, monkeypatch: object
) -> None:
    shifu_bid = uuid.uuid4().hex[:32]
    monkeypatch.setattr(
        shifu_outline_funcs, "check_text_with_risk_control", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        shifu_outline_funcs, "save_new_outline_history", lambda *_a, **_k: None
    )

    with app.app_context():
        _seed_draft(shifu_bid, "uow-outline-owner")
        created = shifu_outline_funcs.create_outlines_batch(
            app,
            "uow-outline-owner",
            shifu_bid,
            [{"name": "Chapter 1", "children": [{"name": "Lesson 1"}]}],
        )

    assert len(created) == 1
    rows = _committed_rows(
        app, DraftOutlineItem.__table__, DraftOutlineItem.shifu_bid == shifu_bid
    )
    assert len(rows) == 2


def test_grant_permission_late_failure_persists_nothing_and_skips_post_auth(
    app: object, monkeypatch: object
) -> None:
    shifu_bid = uuid.uuid4().hex[:32]
    owner_id = uuid.uuid4().hex[:32]
    target_email = f"{uuid.uuid4().hex[:10]}@example.com"
    post_auth: list[str] = []
    monkeypatch.setattr(
        shifu_permission_funcs,
        "run_creator_granted_post_auth",
        lambda *_a, **kwargs: post_auth.append(kwargs["user_id"]),
    )

    def failing_upsert(*_args: object, **_kwargs: object) -> None:
        message = "credential boom"
        raise RuntimeError(message)

    monkeypatch.setattr(shifu_permission_funcs, "upsert_credential", failing_upsert)

    with app.app_context():
        _seed_draft(shifu_bid, owner_id)
        with pytest.raises(RuntimeError, match="credential boom"):
            shifu_permission_funcs.grant_shifu_permissions(
                app,
                shifu_bid=shifu_bid,
                owner_id=owner_id,
                contact_type="email",
                contacts=[target_email],
                permission="edit",
            )

    auths = _committed_rows(
        app, AiCourseAuth.__table__, AiCourseAuth.course_id == shifu_bid
    )
    assert auths == []
    assert post_auth == []


def test_grant_permission_runs_post_auth_only_after_commit(
    app: object, monkeypatch: object
) -> None:
    shifu_bid = uuid.uuid4().hex[:32]
    owner_id = uuid.uuid4().hex[:32]
    target_user = uuid.uuid4().hex[:32]
    target_email = f"{uuid.uuid4().hex[:10]}@example.com"
    seen: list[list[str]] = []

    def fake_post_auth(_app: object, *, user_id: str, **_kwargs: object) -> None:
        rows = _committed_rows(
            app,
            AiCourseAuth.__table__,
            AiCourseAuth.course_id == shifu_bid,
            AiCourseAuth.user_id == user_id,
            AiCourseAuth.status == 1,
        )
        seen.append([json.loads(row.auth_type) for row in rows])

    monkeypatch.setattr(
        shifu_permission_funcs, "run_creator_granted_post_auth", fake_post_auth
    )

    with app.app_context():
        _seed_draft(shifu_bid, owner_id)
        _seed_user(app, target_user, target_email)
        count = shifu_permission_funcs.grant_shifu_permissions(
            app,
            shifu_bid=shifu_bid,
            owner_id=owner_id,
            contact_type="email",
            contacts=[target_email],
            permission="publish",
        )

    assert count == 1
    # The post-auth hook observed the committed grant.
    assert seen == [[["edit", "publish"]]]


def test_remove_permission_soft_deletes_and_commits(app: object) -> None:
    shifu_bid = uuid.uuid4().hex[:32]
    user_id = uuid.uuid4().hex[:32]
    with app.app_context():
        dao.db.session.add(
            AiCourseAuth(
                course_auth_id=f"auth-{user_id}",
                course_id=shifu_bid,
                user_id=user_id,
                auth_type=json.dumps(["view"]),
                status=1,
            )
        )
        dao.db.session.commit()
        assert shifu_permission_funcs.remove_shifu_permission(
            app, shifu_bid=shifu_bid, user_id=user_id
        )

    rows = _committed_rows(
        app,
        AiCourseAuth.__table__,
        AiCourseAuth.course_id == shifu_bid,
        AiCourseAuth.user_id == user_id,
    )
    assert [row.status for row in rows] == [0]


def test_transfer_creator_runs_post_auth_only_after_commit(
    app: object, monkeypatch: object
) -> None:
    shifu_bid = uuid.uuid4().hex[:32]
    old_creator = uuid.uuid4().hex[:32]
    target_user = uuid.uuid4().hex[:32]
    target_email = f"{uuid.uuid4().hex[:10]}@example.com"
    seen: list[str] = []

    def fake_post_auth(_app: object, *, user_id: str, **_kwargs: object) -> None:
        rows = _committed_rows(
            app,
            DraftShifu.__table__,
            DraftShifu.shifu_bid == shifu_bid,
            DraftShifu.deleted == 0,
        )
        seen.append(rows[-1].created_user_bid if rows else "")
        assert user_id == target_user

    monkeypatch.setattr(
        "flaskr.service.shifu.admin.run_creator_granted_post_auth", fake_post_auth
    )
    monkeypatch.setattr(
        courses_transfer_copy, "run_creator_granted_post_auth", fake_post_auth
    )

    with app.app_context():
        _seed_user(app, old_creator, f"{uuid.uuid4().hex[:10]}@example.com")
        _seed_user(app, target_user, target_email)
        _seed_draft(shifu_bid, old_creator)
        result = courses_transfer_copy.transfer_operator_course_creator(
            app,
            shifu_bid=shifu_bid,
            contact_type="email",
            identifier=target_email,
        )

    assert result["target_creator_user_bid"] == target_user
    # The hook saw the committed creator change, not a pending one.
    assert seen == [target_user]


def _deadlock_error() -> object:
    from sqlalchemy.exc import OperationalError

    exc = OperationalError("UPDATE outline", {}, Exception(1213, "Deadlock found"))
    exc.orig.args = (1213, "Deadlock found")
    return exc


def _stub_mdflow_save_collaborators(monkeypatch: object) -> None:
    prefix = "flaskr.service.shifu.shifu_mdflow_funcs."
    monkeypatch.setattr(prefix + "check_text_with_risk_control", lambda *_a, **_k: None)
    monkeypatch.setattr(
        prefix + "get_profile_item_definition_list", lambda *_a, **_k: []
    )
    monkeypatch.setattr(
        prefix + "add_profile_item_quick_internal", lambda *_a, **_k: None
    )
    monkeypatch.setattr(prefix + "save_outline_history", lambda *_a, **_k: 999999)
    monkeypatch.setattr(
        prefix + "cleanup_outline_history_versions", lambda *_a, **_k: None
    )
    monkeypatch.setattr("flaskr.dao.time.sleep", lambda *_a, **_k: None)


def test_save_mdflow_retries_a_deadlock_only_when_it_owns_the_transaction(
    app: object, monkeypatch: object
) -> None:
    """Top-level: the deadlock is retried. Nested: it propagates to the owner.

    A nested retry would roll back the caller's staged writes and re-run only
    the save, so the outer transaction would commit without them.
    """
    from flaskr.dao.uow import unit_of_work
    from flaskr.service.shifu.shifu_mdflow_funcs import save_shifu_mdflow
    from sqlalchemy.exc import OperationalError

    from tests.test_mdflow_adapter import _add_outline_version

    shifu_bid = "uow-mdflow-deadlock-shifu"
    outline_bid = "uow-mdflow-deadlock-outline"
    _add_outline_version(app, shifu_bid, outline_bid, "Original", "uow-user", 0)
    _stub_mdflow_save_collaborators(monkeypatch)

    lock_calls: list[str] = []

    def flaky_lock(bid: str) -> None:
        lock_calls.append(bid)
        if len(lock_calls) == 1:
            raise _deadlock_error()

    monkeypatch.setattr(
        "flaskr.service.shifu.shifu_mdflow_funcs.lock_shifu_for_outline_write",
        flaky_lock,
    )

    result = save_shifu_mdflow(app, "uow-user", shifu_bid, outline_bid, "Owner save")
    assert result["conflict"] is False
    assert lock_calls == [shifu_bid, shifu_bid]  # deadlock, then a retry

    lock_calls.clear()

    def nested_save() -> None:
        with app.app_context(), unit_of_work():
            save_shifu_mdflow(app, "uow-user", shifu_bid, outline_bid, "Nested save")

    with pytest.raises(OperationalError):
        nested_save()
    assert lock_calls == [shifu_bid]  # no retry inside a caller's transaction


def test_publish_rolls_back_and_never_starts_the_summary_when_the_last_step_fails(
    app: object, monkeypatch: object
) -> None:
    """Publishing is one unit of work; the summary starts only after it commits."""
    from flaskr.service.shifu import shifu_publish_funcs as module
    from flaskr.service.shifu.models import PublishedOutlineItem, PublishedShifu

    shifu_bid = "uow-publish-rollback"
    summaries: list[object] = []
    monkeypatch.setattr(
        module, "_run_summary_with_error_handling", lambda *args: summaries.append(args)
    )

    def failing_build_url(*_args: object, **_kwargs: object) -> str:
        message = "url boom"
        raise RuntimeError(message)

    monkeypatch.setattr(module, "_build_frontend_url", failing_build_url)

    with app.app_context():
        dao.db.session.add_all(
            [
                DraftShifu(shifu_bid=shifu_bid, title="Draft", description="Desc"),
                DraftOutlineItem(
                    outline_item_bid=f"{shifu_bid}-lesson",
                    shifu_bid=shifu_bid,
                    title="Lesson",
                    position="1",
                    type=401,
                    hidden=0,
                    content="# Lesson",
                ),
            ]
        )
        dao.db.session.commit()

    with pytest.raises(RuntimeError, match="url boom"):
        module.publish_shifu_draft(
            app,
            user_id="uow-user",
            shifu_id=shifu_bid,
            base_url="https://example.com",
            sync_summary=True,
        )

    with app.app_context():
        dao.db.session.expire_all()
        assert PublishedShifu.query.filter_by(shifu_bid=shifu_bid).count() == 0
        assert PublishedOutlineItem.query.filter_by(shifu_bid=shifu_bid).count() == 0
    assert summaries == []


def test_mdflow_save_persists_no_version_when_a_later_step_fails(
    app: object, monkeypatch: object
) -> None:
    """The locked save is one unit of work: a late failure leaves no new version."""
    from flaskr.service.shifu.shifu_mdflow_funcs import save_shifu_mdflow

    from tests.test_mdflow_adapter import _add_outline_version

    shifu_bid = "uow-mdflow-rollback-shifu"
    outline_bid = "uow-mdflow-rollback-outline"
    _add_outline_version(app, shifu_bid, outline_bid, "Original", "uow-user", 0)
    _stub_mdflow_save_collaborators(monkeypatch)
    monkeypatch.setattr(
        "flaskr.service.shifu.shifu_mdflow_funcs.lock_shifu_for_outline_write",
        lambda _bid: None,
    )

    def failing_cleanup(*_args: object, **_kwargs: object) -> None:
        message = "cleanup boom"
        raise RuntimeError(message)

    monkeypatch.setattr(
        "flaskr.service.shifu.shifu_mdflow_funcs.cleanup_outline_history_versions",
        failing_cleanup,
    )

    with pytest.raises(RuntimeError, match="cleanup boom"):
        save_shifu_mdflow(app, "uow-user", shifu_bid, outline_bid, "Updated content")

    with app.app_context():
        dao.db.session.expire_all()
        contents = [
            row.content
            for row in DraftOutlineItem.query.filter_by(
                shifu_bid=shifu_bid, outline_item_bid=outline_bid
            ).all()
        ]
    assert contents == ["Original"]
