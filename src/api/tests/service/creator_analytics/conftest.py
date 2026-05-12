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
