"""Seed a published course for tests that read the learner-facing publication."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.shifu import shifu_publish_funcs
from flaskr.service.shifu.models import DraftOutlineItem, DraftShifu, LogDraftStruct
from flaskr.service.shifu.shifu_history_manager import HistoryItem

OLD_DOCUMENT = "Old first block\n\n---\n\nOld second block\n\n---\n\n?[Continue]"


@pytest.fixture
def runtime_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    """Publish without generating course summaries through a model."""
    monkeypatch.setattr(
        shifu_publish_funcs, "_run_summary_with_error_handling", lambda *_args: None
    )


def _seed_course(
    app: object,
    *,
    model: str = "1",
    temperature: Decimal = Decimal(0),
    outline_prompt: str = "Old lesson prompt",
) -> SimpleNamespace:
    course_bid, outline_bid, user_bid = (uuid4().hex for _index in range(3))
    with app.app_context(), unit_of_work():
        draft = DraftShifu(
            shifu_bid=course_bid,
            title="Revision test course",
            llm=model,
            llm_temperature=temperature,
            llm_system_prompt="Old course prompt",
        )
        outline = DraftOutlineItem(
            shifu_bid=course_bid,
            outline_item_bid=outline_bid,
            title="Revision test lesson",
            position="01",
            type=401,
            content=OLD_DOCUMENT,
            llm_system_prompt=outline_prompt,
        )
        db.session.add_all([draft, outline])
        db.session.flush()
        draft_struct = HistoryItem(
            bid=course_bid,
            id=draft.id,
            type="shifu",
            children=[
                HistoryItem(
                    bid=outline_bid,
                    id=outline.id,
                    type="outline",
                    children=[],
                    child_count=3,
                )
            ],
        )
        db.session.add(
            LogDraftStruct(
                struct_bid=uuid4().hex,
                shifu_bid=course_bid,
                struct=draft_struct.to_json(),
            )
        )
    shifu_publish_funcs.publish_shifu_draft(
        app, user_bid, course_bid, "", sync_summary=True
    )
    return SimpleNamespace(
        course_bid=course_bid, outline_bid=outline_bid, user_bid=user_bid
    )
