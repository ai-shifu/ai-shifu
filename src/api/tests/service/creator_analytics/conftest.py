from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Optional

import pytest

from flaskr.dao import db
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnLessonFeedback,
    LearnProgressRecord,
)
from flaskr.service.metering.models import BillUsageRecord
from flaskr.service.order.models import Order
from flaskr.service.profile.models import VariableValue
from flaskr.service.shifu.models import (
    AiCourseAuth,
    DraftShifu,
    PublishedShifu,
    ShifuUserArchive,
)
from flaskr.service.user.models import UserInfo


def _clear_tables() -> None:
    for model in (
        BillUsageRecord,
        VariableValue,
        LearnLessonFeedback,
        LearnGeneratedBlock,
        LearnProgressRecord,
        Order,
        ShifuUserArchive,
        AiCourseAuth,
        DraftShifu,
        PublishedShifu,
        UserInfo,
    ):
        db.session.query(model).delete()
    db.session.commit()
    db.session.remove()


@pytest.fixture(autouse=True)
def _isolate_creator_analytics_tables(app):
    if app is None:
        yield
        return
    with app.app_context():
        _clear_tables()
    yield
    with app.app_context():
        _clear_tables()


@pytest.fixture
def mock_request_user(monkeypatch):
    """Return a helper that installs a fake authenticated user."""

    def _install(user_id: str = "teacher-1", is_creator: bool = True) -> None:
        dummy_user = SimpleNamespace(
            user_id=user_id,
            language="en-US",
            is_creator=is_creator,
        )
        monkeypatch.setattr(
            "flaskr.route.user.validate_user",
            lambda _app, _token: dummy_user,
            raising=False,
        )

    return _install


def seed_owned_course(
    *,
    shifu_bid: str,
    user_id: str = "teacher-1",
    title: str = "Untitled",
) -> None:
    now = datetime.utcnow()
    db.session.add(
        DraftShifu(
            shifu_bid=shifu_bid,
            title=title,
            keywords="",
            description="",
            avatar_res_bid="",
            llm="",
            llm_temperature=0,
            llm_system_prompt="",
            ask_enabled_status=0,
            ask_llm="",
            ask_llm_temperature=0,
            ask_llm_system_prompt="",
            ask_provider_config="{}",
            price=0,
            deleted=0,
            created_at=now,
            created_user_bid=user_id,
            updated_at=now,
            updated_user_bid=user_id,
        )
    )
    db.session.commit()


def seed_progress(
    *,
    shifu_bid: str,
    user_bid: str,
    status: int,
    outline_item_bid: str = "outline-1",
    progress_record_bid: Optional[str] = None,
) -> str:
    now = datetime.utcnow()
    record_bid = progress_record_bid or f"pr-{shifu_bid}-{user_bid}-{status}"
    db.session.add(
        LearnProgressRecord(
            progress_record_bid=record_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_item_bid,
            user_bid=user_bid,
            status=status,
            block_position="0",
            deleted=0,
            created_at=now,
            updated_at=now,
        )
    )
    db.session.commit()
    return record_bid


def seed_archive(
    *,
    shifu_bid: str,
    user_bid: str,
    archived: int = 0,
) -> None:
    now = datetime.utcnow()
    db.session.add(
        ShifuUserArchive(
            shifu_bid=shifu_bid,
            user_bid=user_bid,
            archived=archived,
            archived_at=now if archived else None,
            created_at=now,
        )
    )
    db.session.commit()


def seed_generated_block(
    *,
    shifu_bid: str,
    user_bid: str,
    type: int,
    role: int,
    content: str,
    progress_record_bid: str = "pr-default",
    generated_block_bid: Optional[str] = None,
) -> str:
    bid = generated_block_bid or f"gb-{shifu_bid}-{user_bid}-{type}-{content[:8]}"
    now = datetime.utcnow()
    db.session.add(
        LearnGeneratedBlock(
            generated_block_bid=bid,
            shifu_bid=shifu_bid,
            user_bid=user_bid,
            progress_record_bid=progress_record_bid,
            type=type,
            role=role,
            generated_content=content,
            deleted=0,
            created_at=now,
        )
    )
    db.session.commit()
    return bid


def seed_user_info(
    *,
    user_bid: str,
    nickname: str,
    user_identify: str = "",
) -> None:
    db.session.add(
        UserInfo(
            user_bid=user_bid,
            user_identify=user_identify,
            nickname=nickname,
            avatar="",
            language="",
            deleted=0,
        )
    )
    db.session.commit()


def seed_bill_usage(
    *,
    shifu_bid: str,
    user_bid: str,
    usage_type: int = 1101,
    usage_scene: int = 1203,
    input_tokens: int = 0,
    output_tokens: int = 0,
    usage_bid: Optional[str] = None,
) -> str:
    """Seed one BillUsageRecord row.

    Defaults model a production learner call (usage_type=LLM, usage_scene=PROD).
    """

    bid = usage_bid or f"usage-{shifu_bid}-{user_bid}-{usage_type}-{usage_scene}"
    now = datetime.utcnow()
    db.session.add(
        BillUsageRecord(
            usage_bid=bid,
            shifu_bid=shifu_bid,
            user_bid=user_bid,
            usage_type=usage_type,
            usage_scene=usage_scene,
            input=input_tokens,
            output=output_tokens,
            deleted=0,
            created_at=now,
        )
    )
    db.session.commit()
    return bid
