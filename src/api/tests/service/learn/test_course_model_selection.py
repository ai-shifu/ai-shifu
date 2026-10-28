"""Course models are authoritative for lessons, preview, and follow-up."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from flaskr.dao import db
from flaskr.service.learn.agent import lesson_entry
from flaskr.service.learn.ask.context import resolve_course_system_prompt
from flaskr.service.learn.utils_v2 import get_follow_up_info_v2
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    LogDraftStruct,
    LogPublishedStruct,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.service.shifu.struct_utils import find_node_with_parents

if TYPE_CHECKING:
    from flask import Flask


@pytest.mark.parametrize("preview", [True, False])
@pytest.mark.parametrize("course_model", ["course-main", "", "   ", " course-main "])
@pytest.mark.parametrize("ask_model", ["course-ask", ""])
@pytest.mark.parametrize("outline_ask_mode", [5101, 5102, 5103])
def test_course_settings_drive_lessons_and_follow_up(
    app: Flask,
    preview: bool,
    course_model: str,
    ask_model: str,
    outline_ask_mode: int,
) -> None:
    shifu_type = DraftShifu if preview else PublishedShifu
    outline_type = DraftOutlineItem if preview else PublishedOutlineItem
    struct_type = LogDraftStruct if preview else LogPublishedStruct
    shifu_bid, chapter_bid, lesson_bid = (uuid.uuid4().hex for _ in range(3))
    with app.app_context():
        course = shifu_type(
            shifu_bid=shifu_bid,
            llm=course_model,
            llm_temperature=Decimal("0.7"),
            ask_llm=ask_model,
            ask_enabled_status=5103,
            ask_llm_system_prompt="Course follow-up prompt",
            ask_llm_temperature=Decimal("0.4"),
            llm_system_prompt="Course teaching prompt",
        )
        chapter = outline_type(
            shifu_bid=shifu_bid,
            outline_item_bid=chapter_bid,
            llm_system_prompt="Chapter teaching prompt",
            ask_llm_system_prompt="Chapter follow-up prompt",
            ask_enabled_status=5103,
        )
        lesson = outline_type(
            shifu_bid=shifu_bid,
            outline_item_bid=lesson_bid,
            parent_bid=chapter_bid,
            content="Teach this lesson.",
            ask_llm_system_prompt="Lesson follow-up prompt",
            ask_enabled_status=outline_ask_mode,
            type=401,
        )
        db.session.add_all([course, chapter, lesson])
        db.session.flush()
        tree = HistoryItem(
            bid=shifu_bid,
            id=course.id,
            type="shifu",
            children=[
                HistoryItem(
                    bid=chapter_bid,
                    id=chapter.id,
                    type="outline",
                    children=[
                        HistoryItem(
                            bid=lesson_bid, id=lesson.id, type="outline", children=[]
                        )
                    ],
                )
            ],
        )
        db.session.add(
            struct_type(
                struct_bid=uuid.uuid4().hex, shifu_bid=shifu_bid, struct=tree.to_json()
            )
        )
        db.session.commit()
        # Deliberately attach legacy attributes: no resolver may consult them.
        for outline in (chapter, lesson):
            outline.llm = "legacy-outline-main"
            outline.ask_llm = "gemini-3.8-live"
            outline.llm_temperature = Decimal("1.8")
            outline.ask_llm_temperature = Decimal("1.9")

        expected_model = course_model
        expected_temperature = float(course.llm_temperature)
        assert (
            resolve_course_system_prompt(
                app,
                shifu_bid=shifu_bid,
                outline_item_bid=lesson_bid,
                preview_mode=preview,
                outline_path=find_node_with_parents(tree, lesson_bid),
                outline_model=outline_type,
                shifu_model=shifu_type,
            )
            == "Chapter teaching prompt"
        )
        script, _brief, agent_settings, _revision, _language = lesson_entry._resolve(
            app,
            user_bid="teacher-1",
            shifu_bid=shifu_bid,
            outline_bid=lesson_bid,
            preview_mode=preview,
        )
        assert script == lesson.content
        assert agent_settings.model == expected_model
        assert float(agent_settings.temperature) == expected_temperature

        info = get_follow_up_info_v2(app, shifu_bid, lesson_bid, "", is_preview=preview)
        assert info.ask_model == ask_model
        assert info.ask_prompt == (
            "Chapter follow-up prompt"
            if outline_ask_mode == 5101
            else "Lesson follow-up prompt"
        )
        assert info.model_args == {"temperature": Decimal("0.4")}
        assert info.ask_mode == (5103 if outline_ask_mode == 5101 else outline_ask_mode)
        chapter.ask_enabled_status = 5101
        lesson.ask_enabled_status = 5101
        course.ask_enabled_status = 5102
        db.session.commit()
        disabled = get_follow_up_info_v2(
            app, shifu_bid, lesson_bid, "", is_preview=preview
        )
        assert disabled.ask_mode == 5102
        assert disabled.ask_model == ask_model
        db.session.rollback()
