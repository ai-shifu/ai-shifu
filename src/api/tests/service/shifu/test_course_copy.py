from __future__ import annotations

import json
import uuid
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from flaskr.common import config as config_module
from flaskr.dao import db
from flaskr.i18n import _
from flaskr.service.common.models import AppException, ERROR_CODE, raise_error
from flaskr.service.profile.models import Variable
from flaskr.service.shifu.admin import copy_operator_course
from flaskr.service.shifu.models import AiCourseAuth, DraftOutlineItem, DraftShifu
from flaskr.service.shifu.shifu_history_manager import get_shifu_history
from flaskr.service.user.consts import USER_STATE_REGISTERED
from flaskr.service.user.models import AuthCredential, UserInfo as UserEntity
from flaskr.service.user.repository import create_user_entity, upsert_credential


SOURCE_TITLE = "复制源课程"
SOURCE_OPERATOR_BID = "operator-copy-1"


def _unique_email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:10]}@example.com"


@pytest.fixture(autouse=True)
def _stub_copy_course_risk_control(monkeypatch):
    monkeypatch.setattr(
        "flaskr.service.shifu.admin.check_text_with_risk_control",
        lambda *args, **kwargs: None,
    )


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


def _seed_course_with_outlines(
    app, *, shifu_bid: str, creator_user_bid: str
) -> dict[str, str]:
    draft = DraftShifu(
        shifu_bid=shifu_bid,
        title=SOURCE_TITLE,
        description="source description",
        avatar_res_bid="avatar-1",
        keywords="copy,test",
        llm="gpt-4.1",
        llm_temperature=Decimal("0.35"),
        llm_system_prompt="course prompt",
        ask_enabled_status=5103,
        ask_llm="gpt-4.1-mini",
        ask_llm_temperature=Decimal("0.15"),
        ask_llm_system_prompt="ask prompt",
        ask_provider_config=json.dumps(
            {
                "provider": "llm",
                "mode": "provider_then_llm",
                "config": {"foo": "bar"},
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        price=Decimal("199.00"),
        tts_enabled=1,
        tts_provider="volcengine",
        tts_model="seed-tts-1.0",
        tts_voice_id="voice-1",
        tts_speed=Decimal("1.25"),
        tts_pitch=2,
        tts_emotion="calm",
        use_learner_language=1,
        created_user_bid=creator_user_bid,
        updated_user_bid="source-editor",
        created_at=datetime(2026, 5, 10, 10, 0, 0),
        updated_at=datetime(2026, 5, 10, 12, 0, 0),
    )
    db.session.add(draft)
    db.session.flush()

    chapter_bid = uuid.uuid4().hex[:32]
    lesson_a_bid = uuid.uuid4().hex[:32]
    lesson_b_bid = uuid.uuid4().hex[:32]
    db.session.add_all(
        [
            DraftOutlineItem(
                outline_item_bid=chapter_bid,
                shifu_bid=shifu_bid,
                title="第一章",
                type=402,
                hidden=0,
                parent_bid="",
                position="01",
                prerequisite_item_bids="",
                llm="gpt-4.1",
                llm_temperature=Decimal("0.25"),
                llm_system_prompt="chapter prompt",
                ask_enabled_status=5103,
                ask_llm="gpt-4.1-mini",
                ask_llm_temperature=Decimal("0.10"),
                ask_llm_system_prompt="chapter ask",
                content="",
                created_user_bid=creator_user_bid,
                updated_user_bid="source-editor",
            ),
            DraftOutlineItem(
                outline_item_bid=lesson_a_bid,
                shifu_bid=shifu_bid,
                title="第一节",
                type=402,
                hidden=0,
                parent_bid=chapter_bid,
                position="0101",
                prerequisite_item_bids="",
                llm="gpt-4.1",
                llm_temperature=Decimal("0.20"),
                llm_system_prompt="lesson prompt 1",
                ask_enabled_status=5103,
                ask_llm="gpt-4.1-mini",
                ask_llm_temperature=Decimal("0.10"),
                ask_llm_system_prompt="lesson ask 1",
                content="## Title\n\nLesson A content",
                created_user_bid=creator_user_bid,
                updated_user_bid="source-editor",
            ),
            DraftOutlineItem(
                outline_item_bid=lesson_b_bid,
                shifu_bid=shifu_bid,
                title="第二节",
                type=402,
                hidden=0,
                parent_bid=chapter_bid,
                position="0102",
                prerequisite_item_bids=lesson_a_bid,
                llm="gpt-4.1",
                llm_temperature=Decimal("0.30"),
                llm_system_prompt="lesson prompt 2",
                ask_enabled_status=5103,
                ask_llm="gpt-4.1-mini",
                ask_llm_temperature=Decimal("0.10"),
                ask_llm_system_prompt="lesson ask 2",
                content="## Title\n\nLesson B content",
                created_user_bid=creator_user_bid,
                updated_user_bid="source-editor",
            ),
        ]
    )
    db.session.flush()
    return {
        "chapter_bid": chapter_bid,
        "lesson_a_bid": lesson_a_bid,
        "lesson_b_bid": lesson_b_bid,
    }


def _mock_operator(monkeypatch, user_id: str = SOURCE_OPERATOR_BID):
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
    except (AttributeError, KeyError, TypeError):
        pass
    try:
        if config_module.__INSTANCE__ is not None:
            config_module.__INSTANCE__.enhanced._cache.clear()
    except (AttributeError, KeyError, TypeError):
        pass


def _seed_course_variable(
    *,
    shifu_bid: str,
    key: str,
    creator_user_bid: str,
    is_hidden: int = 0,
) -> None:
    db.session.add(
        Variable(
            variable_bid=uuid.uuid4().hex[:32],
            shifu_bid=shifu_bid,
            key=key,
            is_hidden=is_hidden,
            deleted=0,
            created_user_bid=creator_user_bid,
            updated_user_bid=creator_user_bid,
        )
    )
    db.session.flush()
    _clear_config_caches()


def test_copy_course_allows_same_creator_and_clones_latest_draft(app):
    shifu_bid = uuid.uuid4().hex[:32]
    creator_bid = uuid.uuid4().hex[:32]
    viewer_bid = uuid.uuid4().hex[:32]
    creator_email = _unique_email("owner")
    viewer_email = _unique_email("viewer")

    with app.app_context():
        _seed_user(app, user_bid=creator_bid, email=creator_email)
        creator_entity = UserEntity.query.filter_by(user_bid=creator_bid).one()
        creator_entity.is_creator = 1
        _seed_user(app, user_bid=viewer_bid, email=viewer_email)
        source_bids = _seed_course_with_outlines(
            app,
            shifu_bid=shifu_bid,
            creator_user_bid=creator_bid,
        )
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

        result = copy_operator_course(
            app,
            shifu_bid=shifu_bid,
            contact_type="email",
            identifier=creator_email,
            operator_user_bid=SOURCE_OPERATOR_BID,
        )

        new_shifu_bid = result["new_shifu_bid"]
        copied_draft = DraftShifu.query.filter_by(
            shifu_bid=new_shifu_bid,
            deleted=0,
        ).one()
        copied_outlines = (
            DraftOutlineItem.query.filter_by(shifu_bid=new_shifu_bid, deleted=0)
            .order_by(DraftOutlineItem.position.asc())
            .all()
        )
        copied_by_title = {item.title: item for item in copied_outlines}
        copied_history = get_shifu_history(app, new_shifu_bid)
        copied_auths = AiCourseAuth.query.filter_by(course_id=new_shifu_bid).all()

        assert result["source_shifu_bid"] == shifu_bid
        assert result["target_creator_user_bid"] == creator_bid
        assert result["created_new_user"] is False
        assert copied_draft.shifu_bid != shifu_bid
        assert (
            copied_draft.title
            == f"{SOURCE_TITLE}{_('server.shifu.copyCourseTitleSuffix')}"
        )
        assert copied_draft.created_user_bid == creator_bid
        assert copied_draft.updated_user_bid == SOURCE_OPERATOR_BID
        assert copied_draft.llm == "gpt-4.1"
        assert copied_draft.ask_provider_config == json.dumps(
            {
                "provider": "llm",
                "mode": "provider_then_llm",
                "config": {"foo": "bar"},
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        assert copied_draft.tts_provider == "volcengine"
        assert copied_draft.tts_model == "seed-tts-1.0"
        assert copied_draft.tts_voice_id == "voice-1"
        assert copied_draft.tts_emotion == "calm"
        assert copied_draft.use_learner_language == 1

        assert len(copied_outlines) == 3
        assert copied_by_title["第一章"].outline_item_bid != source_bids["chapter_bid"]
        assert copied_by_title["第一节"].outline_item_bid != source_bids["lesson_a_bid"]
        assert copied_by_title["第二节"].outline_item_bid != source_bids["lesson_b_bid"]
        assert (
            copied_by_title["第一节"].parent_bid
            == copied_by_title["第一章"].outline_item_bid
        )
        assert (
            copied_by_title["第二节"].parent_bid
            == copied_by_title["第一章"].outline_item_bid
        )
        assert (
            copied_by_title["第二节"].prerequisite_item_bids
            == copied_by_title["第一节"].outline_item_bid
        )
        assert copied_by_title["第一节"].content == "## Title\n\nLesson A content"
        assert copied_by_title["第二节"].updated_user_bid == SOURCE_OPERATOR_BID

        assert copied_history.bid == new_shifu_bid
        assert copied_history.id == copied_draft.id
        assert len(copied_history.children) == 1
        assert (
            copied_history.children[0].bid == copied_by_title["第一章"].outline_item_bid
        )
        assert len(copied_history.children[0].children) == 2
        assert copied_auths == []


def test_copy_course_creates_missing_target_user_and_grants_creator_role(
    app, monkeypatch
):
    shifu_bid = uuid.uuid4().hex[:32]
    creator_bid = uuid.uuid4().hex[:32]
    target_email = f"{uuid.uuid4().hex[:10]}@example.com"
    post_auth_calls: list[dict] = []
    owner_email = _unique_email("copy-owner")

    with app.app_context():
        _seed_user(app, user_bid=creator_bid, email=owner_email)
        _seed_course_with_outlines(
            app, shifu_bid=shifu_bid, creator_user_bid=creator_bid
        )
        db.session.commit()

        monkeypatch.setattr(
            "flaskr.service.shifu.admin.run_creator_granted_post_auth",
            lambda *args, **kwargs: post_auth_calls.append(kwargs),
        )

        result = copy_operator_course(
            app,
            shifu_bid=shifu_bid,
            contact_type="email",
            identifier=target_email,
            operator_user_bid=SOURCE_OPERATOR_BID,
        )

        target_user_bid = result["target_creator_user_bid"]
        target_entity = UserEntity.query.filter_by(user_bid=target_user_bid).one()
        target_credential = AuthCredential.query.filter_by(
            user_bid=target_user_bid,
            provider_name="email",
            identifier=target_email,
            deleted=0,
        ).one()
        copied_draft = DraftShifu.query.filter_by(
            shifu_bid=result["new_shifu_bid"],
            deleted=0,
        ).one()

        assert result["created_new_user"] is True
        assert target_entity.is_creator == 1
        assert target_entity.creator_activated_at is not None
        assert target_credential is not None
        assert copied_draft.created_user_bid == target_user_bid
        assert copied_draft.updated_user_bid == SOURCE_OPERATOR_BID
        assert post_auth_calls == [
            {
                "user_id": target_user_bid,
                "source": "operator_copy_course",
                "login_context": "admin",
                "created_new_user": True,
                "language": "en-US",
            }
        ]


def test_copy_course_reuses_existing_google_creator_account(app):
    shifu_bid = uuid.uuid4().hex[:32]
    creator_bid = uuid.uuid4().hex[:32]
    target_user_bid = uuid.uuid4().hex[:32]
    target_email = _unique_email("google-only-creator")
    owner_email = _unique_email("copy-owner")

    with app.app_context():
        _seed_user(app, user_bid=creator_bid, email=owner_email)
        _seed_course_with_outlines(
            app,
            shifu_bid=shifu_bid,
            creator_user_bid=creator_bid,
        )
        _seed_user(app, user_bid=target_user_bid)
        upsert_credential(
            app,
            user_bid=target_user_bid,
            provider_name="google",
            subject_id=target_email,
            subject_format="email",
            identifier=target_email,
            metadata={},
            verified=True,
        )
        db.session.commit()

        result = copy_operator_course(
            app,
            shifu_bid=shifu_bid,
            contact_type="email",
            identifier=target_email,
            operator_user_bid=SOURCE_OPERATOR_BID,
        )

        copied_draft = DraftShifu.query.filter_by(
            shifu_bid=result["new_shifu_bid"],
            deleted=0,
        ).one()
        target_entity = UserEntity.query.filter_by(user_bid=target_user_bid).one()
        email_credential = AuthCredential.query.filter_by(
            user_bid=target_user_bid,
            provider_name="email",
            identifier=target_email,
            deleted=0,
        ).one()

        assert result["created_new_user"] is False
        assert result["target_creator_user_bid"] == target_user_bid
        assert target_entity.creator_activated_at is not None
        assert copied_draft.created_user_bid == target_user_bid
        assert email_credential is not None


def test_copy_course_skips_deleted_outlines_and_copies_course_variables(app):
    shifu_bid = uuid.uuid4().hex[:32]
    creator_bid = uuid.uuid4().hex[:32]
    creator_email = _unique_email("variables-owner")

    with app.app_context():
        _seed_user(app, user_bid=creator_bid, email=creator_email)
        creator_entity = UserEntity.query.filter_by(user_bid=creator_bid).one()
        creator_entity.is_creator = 1
        source_bids = _seed_course_with_outlines(
            app,
            shifu_bid=shifu_bid,
            creator_user_bid=creator_bid,
        )
        _seed_course_variable(
            shifu_bid=shifu_bid,
            key="course_goal",
            creator_user_bid=creator_bid,
            is_hidden=1,
        )
        db.session.add(
            DraftOutlineItem(
                outline_item_bid=source_bids["lesson_b_bid"],
                shifu_bid=shifu_bid,
                title="第二节",
                type=402,
                hidden=0,
                parent_bid=source_bids["chapter_bid"],
                position="0102",
                prerequisite_item_bids=source_bids["lesson_a_bid"],
                llm="gpt-4.1",
                llm_temperature=Decimal("0.30"),
                llm_system_prompt="lesson prompt 2",
                ask_enabled_status=5103,
                ask_llm="gpt-4.1-mini",
                ask_llm_temperature=Decimal("0.10"),
                ask_llm_system_prompt="lesson ask 2",
                content="## Title\n\nLesson B content",
                deleted=1,
                created_user_bid=creator_bid,
                updated_user_bid="source-editor",
            )
        )
        db.session.commit()

        result = copy_operator_course(
            app,
            shifu_bid=shifu_bid,
            contact_type="email",
            identifier=creator_email,
            operator_user_bid=SOURCE_OPERATOR_BID,
        )

        copied_outlines = (
            DraftOutlineItem.query.filter_by(
                shifu_bid=result["new_shifu_bid"],
                deleted=0,
            )
            .order_by(DraftOutlineItem.position.asc())
            .all()
        )
        copied_variables = (
            Variable.query.filter_by(
                shifu_bid=result["new_shifu_bid"],
                deleted=0,
            )
            .order_by(Variable.key.asc())
            .all()
        )

        assert [item.title for item in copied_outlines] == ["第一章", "第一节"]
        assert len(copied_variables) == 1
        assert copied_variables[0].key == "course_goal"
        assert copied_variables[0].is_hidden == 1
        assert copied_variables[0].variable_bid


def test_copy_course_rejects_builtin_demo_course(app):
    shifu_bid = uuid.uuid4().hex[:32]
    target_email = _unique_email("demo-copy")

    with app.app_context():
        _seed_user(app, user_bid="target-demo-copy", email=target_email)
        target_entity = UserEntity.query.filter_by(user_bid="target-demo-copy").one()
        target_entity.is_creator = 1
        demo_draft = DraftShifu(
            shifu_bid=shifu_bid,
            title="AI-Shifu Creation Guide",
            description="builtin demo",
            avatar_res_bid="",
            keywords="",
            llm="gpt-test",
            llm_temperature=Decimal("0"),
            llm_system_prompt="",
            price=Decimal("0"),
            created_user_bid="system",
            updated_user_bid="system",
        )
        db.session.add(demo_draft)
        db.session.commit()

        with pytest.raises(AppException) as exc_info:
            copy_operator_course(
                app,
                shifu_bid=shifu_bid,
                contact_type="email",
                identifier=target_email,
                operator_user_bid=SOURCE_OPERATOR_BID,
            )

        assert "copied" in exc_info.value.message.lower()
        assert DraftShifu.query.filter_by(shifu_bid=shifu_bid, deleted=0).count() == 1


def test_copy_course_requires_operator_user_bid(app):
    shifu_bid = uuid.uuid4().hex[:32]
    creator_bid = uuid.uuid4().hex[:32]
    creator_email = _unique_email("owner")

    with app.app_context():
        _seed_user(app, user_bid=creator_bid, email=creator_email)
        creator_entity = UserEntity.query.filter_by(user_bid=creator_bid).one()
        creator_entity.is_creator = 1
        _seed_course_with_outlines(
            app,
            shifu_bid=shifu_bid,
            creator_user_bid=creator_bid,
        )
        db.session.commit()

        with pytest.raises(AppException) as exc_info:
            copy_operator_course(
                app,
                shifu_bid=shifu_bid,
                contact_type="email",
                identifier=creator_email,
                operator_user_bid="",
            )

        assert exc_info.value.message
        assert "operator_user_bid" in exc_info.value.message


def test_copy_course_route_for_operator(app, test_client, monkeypatch):
    shifu_bid = uuid.uuid4().hex[:32]
    creator_bid = uuid.uuid4().hex[:32]
    owner_email = _unique_email("route-owner")
    target_email = _unique_email("route-copy")
    requested_course_name = "Operator Requested Copy Name"
    risk_checks: list[tuple[str, str, str]] = []

    with app.app_context():
        _seed_user(app, user_bid=creator_bid, email=owner_email)
        _seed_user(app, user_bid="route-target", email=target_email)
        target_entity = UserEntity.query.filter_by(user_bid="route-target").one()
        target_entity.is_creator = 1
        _seed_course_with_outlines(
            app, shifu_bid=shifu_bid, creator_user_bid=creator_bid
        )
        db.session.commit()

    _mock_operator(monkeypatch)
    monkeypatch.setenv("LOGIN_METHODS_ENABLED", "phone")
    config_module.get_config("LOGIN_METHODS_ENABLED", "phone")
    monkeypatch.setenv("LOGIN_METHODS_ENABLED", "phone,email")
    _clear_config_caches()
    monkeypatch.setattr(
        "flaskr.service.shifu.admin.check_text_with_risk_control",
        lambda _app, resource_bid, user_id, content: risk_checks.append(
            (resource_bid, user_id, content)
        ),
    )

    response = test_client.post(
        f"/api/shifu/admin/operations/courses/{shifu_bid}/copy",
        json={
            "contact_type": "email",
            "identifier": target_email,
            "new_course_name": requested_course_name,
        },
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["source_shifu_bid"] == shifu_bid
    assert payload["data"]["target_creator_user_bid"] == "route-target"
    assert payload["data"]["new_shifu_bid"] != shifu_bid
    assert payload["data"]["new_course_name"] == requested_course_name

    with app.app_context():
        copied_draft = DraftShifu.query.filter_by(
            shifu_bid=payload["data"]["new_shifu_bid"],
            deleted=0,
        ).one()
        copied_outlines = (
            DraftOutlineItem.query.filter_by(
                shifu_bid=payload["data"]["new_shifu_bid"],
                deleted=0,
            )
            .order_by(DraftOutlineItem.position.asc(), DraftOutlineItem.id.asc())
            .all()
        )

    expected_risk_checks = [
        (
            payload["data"]["new_shifu_bid"],
            SOURCE_OPERATOR_BID,
            copied_draft.get_str_to_check(),
        )
    ]
    for outline in copied_outlines:
        expected_risk_checks.append(
            (
                outline.outline_item_bid,
                SOURCE_OPERATOR_BID,
                outline.get_str_to_check(),
            )
        )
        if outline.content:
            expected_risk_checks.append(
                (
                    outline.outline_item_bid,
                    SOURCE_OPERATOR_BID,
                    outline.content,
                )
            )

    assert risk_checks == expected_risk_checks


def test_copy_course_route_rejects_non_object_payload(app, test_client, monkeypatch):
    shifu_bid = uuid.uuid4().hex[:32]
    creator_bid = uuid.uuid4().hex[:32]
    owner_email = _unique_email("route-owner")

    with app.app_context():
        _seed_user(app, user_bid=creator_bid, email=owner_email)
        _seed_course_with_outlines(
            app, shifu_bid=shifu_bid, creator_user_bid=creator_bid
        )
        db.session.commit()

    _mock_operator(monkeypatch)

    response = test_client.post(
        f"/api/shifu/admin/operations/courses/{shifu_bid}/copy",
        json=["invalid-payload"],
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == ERROR_CODE["server.common.paramsError"]


def test_copy_course_risk_rejection_does_not_create_target_user(app, monkeypatch):
    shifu_bid = uuid.uuid4().hex[:32]
    creator_bid = uuid.uuid4().hex[:32]
    target_email = f"{uuid.uuid4().hex[:10]}@example.com"
    owner_email = _unique_email("copy-owner")

    with app.app_context():
        _seed_user(app, user_bid=creator_bid, email=owner_email)
        _seed_course_with_outlines(
            app,
            shifu_bid=shifu_bid,
            creator_user_bid=creator_bid,
        )
        db.session.commit()

    def _reject_risk(*args, **kwargs):
        raise_error("server.check.checkRiskControlReject")

    monkeypatch.setattr(
        "flaskr.service.shifu.admin.check_text_with_risk_control",
        _reject_risk,
    )

    with pytest.raises(AppException) as exc_info:
        copy_operator_course(
            app,
            shifu_bid=shifu_bid,
            contact_type="email",
            identifier=target_email,
            operator_user_bid=SOURCE_OPERATOR_BID,
        )

    with app.app_context():
        assert exc_info.value.message == _("server.check.checkRiskControlReject")

    with app.app_context():
        assert (
            UserEntity.query.filter_by(
                user_identify=target_email,
                deleted=0,
            ).count()
            == 0
        )
        assert (
            AuthCredential.query.filter_by(
                identifier=target_email,
                deleted=0,
            ).count()
            == 0
        )
