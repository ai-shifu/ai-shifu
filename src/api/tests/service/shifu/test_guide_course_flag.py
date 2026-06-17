from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import uuid

from flaskr.dao import db
from flaskr.service.shifu.models import AiCourseAuth, DraftShifu
from flaskr.service.shifu.shifu_draft_funcs import get_shifu_draft_list
from flaskr.service.user.models import UserInfo as UserEntity


def test_get_shifu_draft_list_marks_builtin_guide_course(app, monkeypatch):
    user_bid = uuid.uuid4().hex[:32]
    guide_bid = uuid.uuid4().hex[:32]
    regular_bid = uuid.uuid4().hex[:32]
    now = datetime.utcnow()

    monkeypatch.setattr(
        "flaskr.service.shifu.demo_courses.get_dynamic_config",
        lambda key, default="": {
            "DEMO_SHIFU_BID": guide_bid,
            "DEMO_EN_SHIFU_BID": "",
        }.get(key, default),
    )

    with app.app_context():
        db.session.add(
            UserEntity(
                user_bid=user_bid,
                user_identify=f"{user_bid}@example.com",
                nickname="Guide Test User",
                language="zh-CN",
                state=1,
                is_creator=1,
                is_operator=0,
                created_at=now,
                updated_at=now,
            )
        )
        db.session.add_all(
            [
                DraftShifu(
                    shifu_bid=guide_bid,
                    title="AI 师傅教学引导",
                    description="guide",
                    avatar_res_bid="",
                    keywords="",
                    llm="gpt-test",
                    llm_temperature=Decimal("0"),
                    llm_system_prompt="",
                    price=Decimal("0"),
                    deleted=0,
                    created_at=now,
                    created_user_bid="system",
                    updated_at=now,
                    updated_user_bid="system",
                ),
                DraftShifu(
                    shifu_bid=regular_bid,
                    title="Regular Course",
                    description="regular",
                    avatar_res_bid="",
                    keywords="",
                    llm="gpt-test",
                    llm_temperature=Decimal("0"),
                    llm_system_prompt="",
                    price=Decimal("0"),
                    deleted=0,
                    created_at=now,
                    created_user_bid=user_bid,
                    updated_at=now,
                    updated_user_bid=user_bid,
                ),
            ]
        )
        db.session.add_all(
            [
                AiCourseAuth(
                    course_auth_id=uuid.uuid4().hex[:32],
                    course_id=guide_bid,
                    user_id=user_bid,
                    auth_type='["view"]',
                    status=1,
                ),
                AiCourseAuth(
                    course_auth_id=uuid.uuid4().hex[:32],
                    course_id=regular_bid,
                    user_id=user_bid,
                    auth_type='["edit"]',
                    status=1,
                ),
            ]
        )
        db.session.commit()

        result = get_shifu_draft_list(
            app,
            user_bid,
            page_index=1,
            page_size=20,
            is_favorite=False,
            creator_only=False,
        )

    items_by_bid = {item.bid: item for item in result.data}
    assert items_by_bid[guide_bid].is_guide_course is True
    assert items_by_bid[regular_bid].is_guide_course is False
