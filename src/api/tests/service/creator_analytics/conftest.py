from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Optional

import pytest

from flaskr.dao import db
from flaskr.service.billing.models import BillingDailyUsageMetric
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnLessonFeedback,
    LearnProgressRecord,
)
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
        BillingDailyUsageMetric,
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
    deleted: int = 0,
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
            deleted=deleted,
            created_at=now,
            created_user_bid=user_id,
            updated_at=now,
            updated_user_bid=user_id,
        )
    )
    db.session.commit()


def seed_published_shifu(
    *,
    shifu_bid: str,
    user_id: str = "teacher-1",
    title: str = "Untitled",
    deleted: int = 0,
) -> None:
    """Seed one PublishedShifu row. Pair with seed_owned_course when the test
    needs both the draft and the published version of a course (e.g. to cover
    the "draft title diverges from published title after rename" scenario)."""

    now = datetime.utcnow()
    db.session.add(
        PublishedShifu(
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
            deleted=deleted,
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
    outline_item_bid: str = "",
    position: int = 0,
    status: int = 1,
) -> str:
    bid = generated_block_bid or f"gb-{shifu_bid}-{user_bid}-{type}-{content[:8]}"
    now = datetime.utcnow()
    db.session.add(
        LearnGeneratedBlock(
            generated_block_bid=bid,
            shifu_bid=shifu_bid,
            user_bid=user_bid,
            progress_record_bid=progress_record_bid,
            outline_item_bid=outline_item_bid,
            position=position,
            type=type,
            role=role,
            status=status,
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


def seed_bill_daily_metric(
    *,
    shifu_bid: str,
    stat_date: str,
    creator_bid: str = "creator-1",
    usage_scene: int = 1203,
    usage_type: int = 1101,
    provider: str = "openai",
    model: str = "gpt-4o",
    billing_metric: int = 1,
    consumed_credits: float = 10.0,
    record_count: int = 5,
    daily_usage_metric_bid: Optional[str] = None,
) -> None:
    """Seed one BillingDailyUsageMetric row for E2E credit-query tests."""

    bid = (
        daily_usage_metric_bid
        or f"dm-{shifu_bid}-{stat_date}-{usage_type}-{provider}-{model}"
    )
    now = datetime.utcnow()
    db.session.add(
        BillingDailyUsageMetric(
            daily_usage_metric_bid=bid,
            stat_date=stat_date,
            creator_bid=creator_bid,
            shifu_bid=shifu_bid,
            usage_scene=usage_scene,
            usage_type=usage_type,
            provider=provider,
            model=model,
            billing_metric=billing_metric,
            raw_amount=0,
            record_count=record_count,
            consumed_credits=consumed_credits,
            window_started_at=now,
            window_ended_at=now,
            deleted=0,
        )
    )
    db.session.commit()
