from __future__ import annotations

import json
import uuid
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from flaskr.common import config as config_module
from flaskr.common.shifu_context import _get_shifu_creator_bid_cached
from flaskr.dao import db
from flaskr.service.shifu.admin import transfer_operator_course_creator
from flaskr.service.shifu.funcs import shifu_permission_verification
from flaskr.service.shifu.models import AiCourseAuth, DraftShifu, PublishedShifu
from flaskr.service.shifu.permissions import get_user_shifu_permissions
from flaskr.service.shifu.utils import get_shifu_creator_bid
from flaskr.service.user.consts import USER_STATE_REGISTERED, USER_STATE_UNREGISTERED
from flaskr.service.user.models import AuthCredential, UserInfo as UserEntity
from flaskr.service.user.repository import create_user_entity, upsert_credential


def _seed_user(
    app,
    *,
    user_bid: str,
    email: str = "",
    phone: str = "",
    state: int = USER_STATE_REGISTERED,
) -> None:
    identify = email or phone or user_bid
    entity = create_user_entity(
        user_bid=user_bid,
        identify=identify,
        nickname=f"user-{user_bid[:6]}",
        language="en-US",
        state=state,
    )
    entity.created_at = datetime.utcnow()
    entity.updated_at = datetime.utcnow()
    db.session.flush()
    if email:
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
    if phone:
        upsert_credential(
            app,
            user_bid=user_bid,
            provider_name="phone",
            subject_id=phone,
            subject_format="phone",
            identifier=phone,
            metadata={},
            verified=True,
        )
    db.session.flush()


def _seed_course(shifu_bid: str, creator_user_bid: str) -> None:
    draft = DraftShifu(
        shifu_bid=shifu_bid,
        title=f"Course {shifu_bid[:6]}",
        description="desc",
        avatar_res_bid="",
        keywords="",
        llm="gpt-test",
        llm_temperature=Decimal("0"),
        llm_system_prompt="",
        price=Decimal("0"),
        created_user_bid=creator_user_bid,
        updated_user_bid=creator_user_bid,
    )
    db.session.add(draft)
    db.session.flush()


def _seed_published_course(shifu_bid: str, creator_user_bid: str) -> None:
    published = PublishedShifu(
        shifu_bid=shifu_bid,
        title=f"Published {shifu_bid[:6]}",
        description="desc",
        avatar_res_bid="",
        keywords="",
        llm="gpt-test",
        llm_temperature=Decimal("0"),
        llm_system_prompt="",
        price=Decimal("0"),
        created_user_bid=creator_user_bid,
        updated_user_bid=creator_user_bid,
    )
    db.session.add(published)
    db.session.flush()


def _mock_operator(monkeypatch, user_id: str = "operator-1"):
    dummy_user = SimpleNamespace(
        user_id=user_id,
        is_operator=True,
        is_creator=False,
        language="en-US",
    )
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: dummy_user,
        raising=False,
    )
    return dummy_user


def _clear_config_caches() -> None:
    try:
        config_module.__ENHANCED_CONFIG__._cache.clear()
    except Exception:
        pass
    try:
        if config_module.__INSTANCE__ is not None:
            config_module.__INSTANCE__.enhanced._cache.clear()
    except Exception:
        pass


def test_transfer_creator_creates_missing_user_and_preserves_shared_auth(
    app, monkeypatch
):
    shifu_bid = uuid.uuid4().hex[:32]
    old_creator_bid = uuid.uuid4().hex[:32]
    viewer_bid = uuid.uuid4().hex[:32]
    target_email = f"{uuid.uuid4().hex[:10]}@example.com"
    demo_bid = uuid.uuid4().hex[:32]

    with app.app_context():
        _seed_user(app, user_bid=old_creator_bid, email="old@example.com")
        _seed_user(app, user_bid=viewer_bid, email="viewer@example.com")
        _seed_course(shifu_bid, old_creator_bid)
        db.session.add(
            AiCourseAuth(
                course_auth_id=uuid.uuid4().hex[:32],
                user_id=viewer_bid,
                course_id=shifu_bid,
                auth_type=json.dumps(["view"]),
                status=1,
            )
        )
        db.session.commit()

        monkeypatch.setattr(
            "flaskr.service.shifu.admin.load_existing_demo_shifu_ids",
            lambda: {demo_bid},
        )

        result = transfer_operator_course_creator(
            app,
            shifu_bid=shifu_bid,
            contact_type="email",
            identifier=target_email,
        )

        target_user_bid = result["target_creator_user_bid"]
        auth = AiCourseAuth.query.filter_by(
            user_id=target_user_bid,
            course_id=demo_bid,
        ).first()
        shared_auth = AiCourseAuth.query.filter_by(
            user_id=viewer_bid,
            course_id=shifu_bid,
            status=1,
        ).first()
        target_entity = UserEntity.query.filter_by(user_bid=target_user_bid).first()
        target_credential = AuthCredential.query.filter_by(
            user_bid=target_user_bid,
            provider_name="email",
            identifier=target_email,
            deleted=0,
        ).first()

        assert result["created_new_user"] is True
        assert result["granted_demo_permissions"] is True
        assert target_entity is not None
        assert target_entity.state == USER_STATE_REGISTERED
        assert target_entity.is_creator == 1
        assert target_credential is not None
        assert auth is not None
        assert auth.status == 1
        assert get_shifu_creator_bid(app, shifu_bid) == target_user_bid
        assert (
            shifu_permission_verification(app, old_creator_bid, shifu_bid, "edit")
            is False
        )
        assert shared_auth is not None


def test_transfer_creator_promotes_unregistered_existing_user(app, monkeypatch):
    shifu_bid = uuid.uuid4().hex[:32]
    old_creator_bid = uuid.uuid4().hex[:32]
    target_user_bid = uuid.uuid4().hex[:32]
    target_phone = "13800001234"
    demo_bid = uuid.uuid4().hex[:32]

    with app.app_context():
        _seed_user(app, user_bid=old_creator_bid, email="old2@example.com")
        _seed_user(
            app,
            user_bid=target_user_bid,
            phone=target_phone,
            state=USER_STATE_UNREGISTERED,
        )
        _seed_course(shifu_bid, old_creator_bid)
        db.session.commit()

        monkeypatch.setattr(
            "flaskr.service.shifu.admin.load_existing_demo_shifu_ids",
            lambda: {demo_bid},
        )

        result = transfer_operator_course_creator(
            app,
            shifu_bid=shifu_bid,
            contact_type="phone",
            identifier=target_phone,
        )

        target_entity = UserEntity.query.filter_by(user_bid=target_user_bid).first()
        demo_auth = AiCourseAuth.query.filter_by(
            user_id=target_user_bid,
            course_id=demo_bid,
        ).first()

        assert result["created_new_user"] is False
        assert result["granted_demo_permissions"] is True
        assert target_entity is not None
        assert target_entity.state == USER_STATE_REGISTERED
        assert target_entity.is_creator == 1
        assert demo_auth is not None
        assert get_shifu_creator_bid(app, shifu_bid) == target_user_bid


def test_transfer_creator_route_for_operator(app, test_client, monkeypatch):
    shifu_bid = uuid.uuid4().hex[:32]
    old_creator_bid = uuid.uuid4().hex[:32]
    target_user_bid = uuid.uuid4().hex[:32]
    target_email = f"{uuid.uuid4().hex[:10]}@example.com"

    with app.app_context():
        _seed_user(app, user_bid=old_creator_bid, email="route-old@example.com")
        _seed_user(app, user_bid=target_user_bid, email=target_email)
        _seed_course(shifu_bid, old_creator_bid)
        db.session.commit()

    _mock_operator(monkeypatch)
    monkeypatch.setenv("LOGIN_METHODS_ENABLED", "phone,email")
    _clear_config_caches()

    response = test_client.post(
        f"/api/shifu/admin/operations/courses/{shifu_bid}/transfer-creator",
        json={
            "contact_type": "email",
            "identifier": target_email,
        },
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["target_creator_user_bid"] == target_user_bid


def test_transfer_creator_promotes_existing_viewer_to_owner_permissions(
    app, monkeypatch
):
    shifu_bid = uuid.uuid4().hex[:32]
    old_creator_bid = uuid.uuid4().hex[:32]
    target_user_bid = uuid.uuid4().hex[:32]
    target_phone = "13800009999"

    with app.app_context():
        _seed_user(app, user_bid=old_creator_bid, email="published-old@example.com")
        _seed_user(app, user_bid=target_user_bid, phone=target_phone)
        _seed_published_course(shifu_bid, old_creator_bid)
        db.session.add(
            AiCourseAuth(
                course_auth_id=uuid.uuid4().hex[:32],
                user_id=target_user_bid,
                course_id=shifu_bid,
                auth_type=json.dumps(["view"]),
                status=1,
            )
        )
        db.session.commit()

        result = transfer_operator_course_creator(
            app,
            shifu_bid=shifu_bid,
            contact_type="phone",
            identifier=target_phone,
        )

        permission_map = get_user_shifu_permissions(app, target_user_bid)

        assert result["target_creator_user_bid"] == target_user_bid
        assert get_shifu_creator_bid(app, shifu_bid) == target_user_bid
        assert (
            shifu_permission_verification(app, target_user_bid, shifu_bid, "edit")
            is True
        )
        assert permission_map[shifu_bid] == {"view", "edit", "publish"}


def test_transfer_creator_invalidates_cached_shifu_creator(app):
    shifu_bid = uuid.uuid4().hex[:32]
    old_creator_bid = uuid.uuid4().hex[:32]
    target_user_bid = uuid.uuid4().hex[:32]
    target_email = f"{uuid.uuid4().hex[:10]}@example.com"

    with app.app_context():
        _seed_user(app, user_bid=old_creator_bid, email="cached-old@example.com")
        _seed_user(app, user_bid=target_user_bid, email=target_email)
        _seed_course(shifu_bid, old_creator_bid)
        db.session.commit()

        assert _get_shifu_creator_bid_cached(app, shifu_bid) == old_creator_bid

        result = transfer_operator_course_creator(
            app,
            shifu_bid=shifu_bid,
            contact_type="email",
            identifier=target_email,
        )

        assert result["target_creator_user_bid"] == target_user_bid
        assert _get_shifu_creator_bid_cached(app, shifu_bid) == target_user_bid


def test_transfer_creator_preserves_existing_target_nickname(app):
    shifu_bid = uuid.uuid4().hex[:32]
    old_creator_bid = uuid.uuid4().hex[:32]
    target_user_bid = uuid.uuid4().hex[:32]
    target_email = f"{uuid.uuid4().hex[:10]}@example.com"
    original_nickname = "已有昵称"

    with app.app_context():
        _seed_user(app, user_bid=old_creator_bid, email="origin@example.com")
        _seed_user(app, user_bid=target_user_bid, email=target_email)
        target_entity = UserEntity.query.filter_by(user_bid=target_user_bid).first()
        assert target_entity is not None
        target_entity.nickname = original_nickname
        _seed_course(shifu_bid, old_creator_bid)
        db.session.commit()

        result = transfer_operator_course_creator(
            app,
            shifu_bid=shifu_bid,
            contact_type="email",
            identifier=target_email,
        )

        refreshed = UserEntity.query.filter_by(user_bid=target_user_bid).first()
        assert result["target_creator_user_bid"] == target_user_bid
        assert refreshed is not None
        assert refreshed.nickname == original_nickname
