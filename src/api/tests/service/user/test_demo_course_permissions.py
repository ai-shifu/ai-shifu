import json
import uuid
from datetime import datetime
from decimal import Decimal

from flaskr.dao import db
from flaskr.service.shifu.models import AiCourseAuth, PublishedShifu
from flaskr.service.user.utils import ensure_demo_course_permissions


def _seed_published_shifu(shifu_bid: str) -> None:
    now = datetime.utcnow()
    db.session.add(
        PublishedShifu(
            shifu_bid=shifu_bid,
            title=f"Demo {shifu_bid[:6]}",
            description="",
            avatar_res_bid="",
            keywords="",
            llm="",
            llm_temperature=Decimal("0"),
            llm_system_prompt="",
            price=Decimal("0"),
            deleted=0,
            created_at=now,
            created_user_bid="system",
            updated_at=now,
            updated_user_bid="system",
        )
    )


def test_ensure_demo_course_permissions_creates_view_auth(app, monkeypatch):
    demo_bid = uuid.uuid4().hex[:32]
    user_id = uuid.uuid4().hex[:32]

    monkeypatch.setattr(
        "flaskr.service.user.utils.get_dynamic_config",
        lambda key: demo_bid if key == "DEMO_SHIFU_BID" else None,
        raising=False,
    )

    with app.app_context():
        try:
            _seed_published_shifu(demo_bid)
            db.session.flush()
            ensure_demo_course_permissions(app, user_id)
            db.session.commit()

            auth = AiCourseAuth.query.filter(
                AiCourseAuth.user_id == user_id,
                AiCourseAuth.course_id == demo_bid,
            ).first()
            assert auth is not None
            assert auth.auth_type == json.dumps(["view"])
            assert auth.status == 1
        finally:
            AiCourseAuth.query.filter(
                AiCourseAuth.user_id == user_id,
                AiCourseAuth.course_id == demo_bid,
            ).delete()
            PublishedShifu.query.filter(PublishedShifu.shifu_bid == demo_bid).delete()
            db.session.commit()


def test_ensure_demo_course_permissions_keeps_existing_higher_permission(
    app, monkeypatch
):
    demo_bid = uuid.uuid4().hex[:32]
    user_id = uuid.uuid4().hex[:32]
    edit_auth = json.dumps(["edit"])

    monkeypatch.setattr(
        "flaskr.service.user.utils.get_dynamic_config",
        lambda key: demo_bid if key == "DEMO_SHIFU_BID" else None,
        raising=False,
    )

    with app.app_context():
        try:
            _seed_published_shifu(demo_bid)
            db.session.add(
                AiCourseAuth(
                    course_auth_id=uuid.uuid4().hex[:32],
                    course_id=demo_bid,
                    user_id=user_id,
                    auth_type=edit_auth,
                    status=0,
                )
            )
            db.session.flush()

            ensure_demo_course_permissions(app, user_id)
            db.session.commit()

            auth = AiCourseAuth.query.filter(
                AiCourseAuth.user_id == user_id,
                AiCourseAuth.course_id == demo_bid,
            ).first()
            assert auth is not None
            assert auth.auth_type == edit_auth
            assert auth.status == 1
        finally:
            AiCourseAuth.query.filter(
                AiCourseAuth.user_id == user_id,
                AiCourseAuth.course_id == demo_bid,
            ).delete()
            PublishedShifu.query.filter(PublishedShifu.shifu_bid == demo_bid).delete()
            db.session.commit()


def test_ensure_demo_course_permissions_fills_empty_auth_type(app, monkeypatch):
    demo_bid = uuid.uuid4().hex[:32]
    user_id = uuid.uuid4().hex[:32]

    monkeypatch.setattr(
        "flaskr.service.user.utils.get_dynamic_config",
        lambda key: demo_bid if key == "DEMO_SHIFU_BID" else None,
        raising=False,
    )

    with app.app_context():
        try:
            _seed_published_shifu(demo_bid)
            db.session.add(
                AiCourseAuth(
                    course_auth_id=uuid.uuid4().hex[:32],
                    course_id=demo_bid,
                    user_id=user_id,
                    auth_type="[]",
                    status=0,
                )
            )
            db.session.flush()

            ensure_demo_course_permissions(app, user_id)
            db.session.commit()

            auth = AiCourseAuth.query.filter(
                AiCourseAuth.user_id == user_id,
                AiCourseAuth.course_id == demo_bid,
            ).first()
            assert auth is not None
            assert auth.auth_type == json.dumps(["view"])
            assert auth.status == 1
        finally:
            AiCourseAuth.query.filter(
                AiCourseAuth.user_id == user_id,
                AiCourseAuth.course_id == demo_bid,
            ).delete()
            PublishedShifu.query.filter(PublishedShifu.shifu_bid == demo_bid).delete()
            db.session.commit()


def test_ensure_demo_course_permissions_skips_missing_demo_courses(app, monkeypatch):
    demo_bid = uuid.uuid4().hex[:32]
    user_id = uuid.uuid4().hex[:32]

    monkeypatch.setattr(
        "flaskr.service.user.utils.get_dynamic_config",
        lambda key: demo_bid if key == "DEMO_SHIFU_BID" else None,
        raising=False,
    )

    with app.app_context():
        try:
            ensure_demo_course_permissions(app, user_id)
            db.session.commit()
            auth = AiCourseAuth.query.filter(
                AiCourseAuth.user_id == user_id,
                AiCourseAuth.course_id == demo_bid,
            ).first()
            assert auth is None
        finally:
            AiCourseAuth.query.filter(
                AiCourseAuth.user_id == user_id,
                AiCourseAuth.course_id == demo_bid,
            ).delete()
            db.session.commit()


def test_ensure_demo_course_permissions_uses_explicit_demo_ids(app):
    demo_bid = uuid.uuid4().hex[:32]
    user_id = uuid.uuid4().hex[:32]

    with app.app_context():
        try:
            _seed_published_shifu(demo_bid)
            db.session.flush()

            ensure_demo_course_permissions(app, user_id, demo_ids={demo_bid})
            db.session.commit()

            auth = AiCourseAuth.query.filter(
                AiCourseAuth.user_id == user_id,
                AiCourseAuth.course_id == demo_bid,
            ).first()
            assert auth is not None
            assert auth.auth_type == json.dumps(["view"])
            assert auth.status == 1
        finally:
            AiCourseAuth.query.filter(
                AiCourseAuth.user_id == user_id,
                AiCourseAuth.course_id == demo_bid,
            ).delete()
            PublishedShifu.query.filter(PublishedShifu.shifu_bid == demo_bid).delete()
            db.session.commit()


def test_ensure_demo_course_permissions_skips_empty_explicit_demo_ids(app, monkeypatch):
    demo_bid = uuid.uuid4().hex[:32]
    user_id = uuid.uuid4().hex[:32]

    monkeypatch.setattr(
        "flaskr.service.user.utils.get_dynamic_config",
        lambda key: demo_bid if key == "DEMO_SHIFU_BID" else None,
        raising=False,
    )

    with app.app_context():
        try:
            _seed_published_shifu(demo_bid)
            db.session.flush()

            ensure_demo_course_permissions(app, user_id, demo_ids=set())
            db.session.commit()

            auth = AiCourseAuth.query.filter(
                AiCourseAuth.user_id == user_id,
                AiCourseAuth.course_id == demo_bid,
            ).first()
            assert auth is None
        finally:
            AiCourseAuth.query.filter(
                AiCourseAuth.user_id == user_id,
                AiCourseAuth.course_id == demo_bid,
            ).delete()
            PublishedShifu.query.filter(PublishedShifu.shifu_bid == demo_bid).delete()
            db.session.commit()
