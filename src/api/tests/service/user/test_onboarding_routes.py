from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy.exc import IntegrityError

from flaskr.dao import db
from flaskr.service.user.onboarding import _serialize_datetime
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.service.user.models import UserOnboardingState
from flaskr.service.user.utils import generate_token


def _create_user(
    *,
    user_bid: str,
    language: str = "zh-CN",
    is_creator: bool = True,
    is_operator: bool = False,
    created_at: datetime | None = None,
    creator_activated_at: datetime | None = None,
) -> UserEntity:
    user = UserEntity(
        user_bid=user_bid,
        user_identify=f"{user_bid}@example.com",
        nickname="Onboarding User",
        language=language,
        state=1,
        is_creator=1 if is_creator else 0,
        is_operator=1 if is_operator else 0,
        created_at=created_at or datetime.now(),
        creator_activated_at=creator_activated_at,
        updated_at=created_at or datetime.now(),
    )
    db.session.add(user)
    return user


def test_serialize_datetime_emits_explicit_utc_suffix():
    assert _serialize_datetime(None) is None
    assert _serialize_datetime(datetime(2026, 6, 17, 12, 5, 0)) == (
        "2026-06-17T12:05:00Z"
    )
    assert (
        _serialize_datetime(
            datetime(2026, 6, 17, 20, 5, 0, tzinfo=timezone(timedelta(hours=8)))
        )
        == "2026-06-17T12:05:00Z"
    )


def test_onboarding_status_returns_eligible_creator_scene_state(
    app, test_client, monkeypatch
):
    user_bid = uuid.uuid4().hex[:32]
    now = datetime(2026, 6, 17, 12, 0, 0)

    with app.app_context():
        _create_user(user_bid=user_bid, created_at=now)
        db.session.add(
            UserOnboardingState(
                user_bid=user_bid,
                scene_key="admin_home_onboarding",
                version="v1",
                status="completed",
                trigger_source="admin_entry",
                completed_at=now + timedelta(minutes=3),
            )
        )
        db.session.commit()
        token = generate_token(app, user_bid)

    monkeypatch.setattr(
        "flaskr.service.user.onboarding.get_dynamic_config",
        lambda key, default="": {
            "ADMIN_ONBOARDING_ENABLED_FROM": "2026-06-10 00:00:00",
            "DEMO_SHIFU_BID": "demo-zh-course",
            "DEMO_EN_SHIFU_BID": "demo-en-course",
        }.get(key, default),
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.demo_courses.get_dynamic_config",
        lambda key, default="": {
            "DEMO_SHIFU_BID": "demo-zh-course",
            "DEMO_EN_SHIFU_BID": "demo-en-course",
        }.get(key, default),
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.demo_courses._load_shifu_demo_metadata",
        lambda app, shifu_bid: (
            [("AI Shifu Guide Course", "system")]
            if shifu_bid == "demo-zh-course"
            else [("AI-Shifu Creation Guide", "system")]
        ),
    )

    response = test_client.get(
        "/api/user/onboarding/status",
        headers={"Token": token},
    )

    assert response.status_code == 200
    payload = response.get_json(force=True)
    assert payload["code"] == 0
    assert payload["data"]["eligible"] is True
    assert payload["data"]["version"] == "v1"
    assert payload["data"]["scenes"]["admin_home_onboarding"]["completed"] is True
    assert payload["data"]["scenes"]["course_editor_onboarding"]["completed"] is False
    assert payload["data"]["guide_course"]["bid"] == "demo-zh-course"
    assert payload["data"]["guide_course"]["language"] == "zh-CN"


def test_onboarding_status_excludes_operator_and_old_creator(
    app, test_client, monkeypatch
):
    user_bid = uuid.uuid4().hex[:32]
    with app.app_context():
        _create_user(
            user_bid=user_bid,
            is_creator=True,
            is_operator=True,
            created_at=datetime(2026, 6, 1, 12, 0, 0),
        )
        db.session.commit()
        token = generate_token(app, user_bid)

    monkeypatch.setattr(
        "flaskr.service.user.onboarding.get_dynamic_config",
        lambda key, default="": {
            "ADMIN_ONBOARDING_ENABLED_FROM": "2026-06-10 00:00:00",
            "DEMO_SHIFU_BID": "demo-zh-course",
        }.get(key, default),
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.demo_courses.get_dynamic_config",
        lambda key, default="": {"DEMO_SHIFU_BID": "demo-zh-course"}.get(key, default),
    )

    response = test_client.get(
        "/api/user/onboarding/status",
        headers={"Token": token},
    )

    assert response.status_code == 200
    payload = response.get_json(force=True)
    assert payload["code"] == 0
    assert payload["data"]["eligible"] is False


def test_onboarding_status_includes_old_user_newly_activated_as_creator(
    app, test_client, monkeypatch
):
    user_bid = uuid.uuid4().hex[:32]
    created_at = datetime(2026, 6, 1, 12, 0, 0)
    creator_activated_at = datetime(2026, 6, 12, 9, 30, 0)

    with app.app_context():
        _create_user(
            user_bid=user_bid,
            is_creator=True,
            created_at=created_at,
            creator_activated_at=creator_activated_at,
        )
        db.session.commit()
        token = generate_token(app, user_bid)

    monkeypatch.setattr(
        "flaskr.service.user.onboarding.get_dynamic_config",
        lambda key, default="": {
            "ADMIN_ONBOARDING_ENABLED_FROM": "2026-06-10 00:00:00",
            "DEMO_SHIFU_BID": "demo-zh-course",
        }.get(key, default),
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.demo_courses.get_dynamic_config",
        lambda key, default="": {"DEMO_SHIFU_BID": "demo-zh-course"}.get(key, default),
    )

    response = test_client.get(
        "/api/user/onboarding/status",
        headers={"Token": token},
    )

    assert response.status_code == 200
    payload = response.get_json(force=True)
    assert payload["code"] == 0
    assert payload["data"]["eligible"] is True


def test_complete_onboarding_scene_is_idempotent(app, test_client, monkeypatch):
    user_bid = uuid.uuid4().hex[:32]
    with app.app_context():
        _create_user(user_bid=user_bid, created_at=datetime(2026, 6, 17, 12, 0, 0))
        db.session.commit()
        token = generate_token(app, user_bid)

    monkeypatch.setattr(
        "flaskr.service.user.onboarding.get_dynamic_config",
        lambda key, default="": default,
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.demo_courses.get_dynamic_config",
        lambda key, default="": default,
    )

    payload = {
        "scene_key": "admin_home_onboarding",
        "version": "v1",
        "trigger_source": "admin_entry",
    }
    first = test_client.post(
        "/api/user/onboarding/complete",
        json=payload,
        headers={"Token": token},
    )
    second = test_client.post(
        "/api/user/onboarding/complete",
        json=payload,
        headers={"Token": token},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.get_json(force=True)["data"]["completed"] is True
    assert second.get_json(force=True)["data"]["completed"] is True

    with app.app_context():
        rows = UserOnboardingState.query.filter(
            UserOnboardingState.user_bid == user_bid,
            UserOnboardingState.scene_key == "admin_home_onboarding",
            UserOnboardingState.version == "v1",
        ).all()
        assert len(rows) == 1


def test_complete_course_editor_onboarding_accepts_direct_editor_entry(
    app, test_client, monkeypatch
):
    user_bid = uuid.uuid4().hex[:32]
    with app.app_context():
        _create_user(user_bid=user_bid, created_at=datetime(2026, 6, 17, 12, 0, 0))
        db.session.commit()
        token = generate_token(app, user_bid)

    monkeypatch.setattr(
        "flaskr.service.user.onboarding.get_dynamic_config",
        lambda key, default="": default,
    )

    response = test_client.post(
        "/api/user/onboarding/complete",
        json={
            "scene_key": "course_editor_onboarding",
            "version": "v1",
            "trigger_source": "editor_entry",
        },
        headers={"Token": token},
    )

    assert response.status_code == 200
    payload = response.get_json(force=True)
    assert payload["code"] == 0
    assert payload["data"]["completed"] is True

    with app.app_context():
        row = UserOnboardingState.query.filter(
            UserOnboardingState.user_bid == user_bid,
            UserOnboardingState.scene_key == "course_editor_onboarding",
            UserOnboardingState.version == "v1",
        ).first()
        assert row is not None
        assert row.trigger_source == "editor_entry"


def test_complete_onboarding_scene_handles_integrity_error(
    app, test_client, monkeypatch
):
    user_bid = uuid.uuid4().hex[:32]
    completed_at = datetime(2026, 6, 17, 12, 5, 0)

    with app.app_context():
        _create_user(user_bid=user_bid, created_at=datetime(2026, 6, 17, 12, 0, 0))
        db.session.add(
            UserOnboardingState(
                user_bid=user_bid,
                scene_key="admin_home_onboarding",
                version="v1",
                status="completed",
                trigger_source="admin_entry",
                completed_at=completed_at,
            )
        )
        db.session.commit()
        token = generate_token(app, user_bid)

    monkeypatch.setattr(
        "flaskr.service.user.onboarding.get_dynamic_config",
        lambda key, default="": default,
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.demo_courses.get_dynamic_config",
        lambda key, default="": default,
    )

    original_commit = db.session.commit
    state = {"raised": False}

    def flaky_commit():
        if not state["raised"]:
            state["raised"] = True
            raise IntegrityError("duplicate", None, None)
        return original_commit()

    monkeypatch.setattr(db.session, "commit", flaky_commit)

    response = test_client.post(
        "/api/user/onboarding/complete",
        json={
            "scene_key": "admin_home_onboarding",
            "version": "v1",
            "trigger_source": "admin_entry",
        },
        headers={"Token": token},
    )

    assert response.status_code == 200
    payload = response.get_json(force=True)
    assert payload["code"] == 0
    assert payload["data"]["completed"] is True
    assert payload["data"]["completed_at"] == f"{completed_at.isoformat()}Z"


def test_complete_onboarding_scene_rejects_ineligible_user(
    app, test_client, monkeypatch
):
    user_bid = uuid.uuid4().hex[:32]
    with app.app_context():
        _create_user(
            user_bid=user_bid,
            is_creator=False,
            created_at=datetime(2026, 6, 17, 12, 0, 0),
        )
        db.session.commit()
        token = generate_token(app, user_bid)

    monkeypatch.setattr(
        "flaskr.service.user.onboarding.get_dynamic_config",
        lambda key, default="": default,
    )

    response = test_client.post(
        "/api/user/onboarding/complete",
        json={
            "scene_key": "admin_home_onboarding",
            "version": "v1",
            "trigger_source": "admin_entry",
        },
        headers={"Token": token},
    )

    assert response.status_code == 200
    payload = response.get_json(force=True)
    assert payload["code"] != 0


def test_complete_onboarding_scene_handles_non_object_payload(
    app, test_client, monkeypatch
):
    user_bid = uuid.uuid4().hex[:32]
    with app.app_context():
        _create_user(user_bid=user_bid, created_at=datetime(2026, 6, 17, 12, 0, 0))
        db.session.commit()
        token = generate_token(app, user_bid)

    monkeypatch.setattr(
        "flaskr.service.user.onboarding.get_dynamic_config",
        lambda key, default="": default,
    )

    response = test_client.post(
        "/api/user/onboarding/complete",
        json=[],
        headers={"Token": token},
    )

    assert response.status_code == 200
    payload = response.get_json(force=True)
    assert payload["code"] != 0
