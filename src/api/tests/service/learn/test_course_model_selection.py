"""Course models are authoritative for both engines, preview, and follow-up."""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from flaskr.dao import db
from flaskr.service.learn import context_v2
from flaskr.service.learn.agent import lesson_entry
from flaskr.service.learn.learn_dtos import PlaygroundPreviewRequest
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

if TYPE_CHECKING:
    from flask import Flask


@pytest.mark.parametrize("preview", [True, False])
@pytest.mark.parametrize("course_model", ["course-main", ""])
@pytest.mark.parametrize("ask_model", ["course-ask", ""])
def test_course_settings_drive_both_engines_and_follow_up(
    app: Flask,
    preview: bool,
    course_model: str,
    ask_model: str,
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
        )
        lesson = outline_type(
            shifu_bid=shifu_bid,
            outline_item_bid=lesson_bid,
            parent_bid=chapter_bid,
            content="Teach this lesson.",
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
            outline.ask_enabled_status = 5102
            outline.llm_system_prompt = "Legacy outline teaching rules"
            outline.ask_llm_system_prompt = "Legacy outline follow-up rules"
            outline.ask_llm_temperature = Decimal("1.9")

        expected_model = course_model or app.config["DEFAULT_LLM_MODEL"]
        expected_temperature = (
            float(course.llm_temperature)
            if course_model
            else float(app.config["DEFAULT_LLM_TEMPERATURE"])
        )
        ctx = context_v2.RunScriptContextV2.__new__(context_v2.RunScriptContextV2)
        ctx.app = app
        ctx._struct = tree
        ctx._shifu_model = shifu_type
        ctx._preview_mode = preview
        assert ctx.get_system_prompt(lesson_bid) == "Course teaching prompt"
        settings = ctx.get_llm_settings(lesson_bid)
        assert settings.model == expected_model
        assert float(settings.temperature) == expected_temperature
        assert lesson_entry._resolve(
            app,
            user_bid="teacher-1",
            shifu_bid=shifu_bid,
            outline_bid=lesson_bid,
            preview_mode=preview,
        ) == (lesson.content, expected_model, expected_temperature)

        info = get_follow_up_info_v2(app, shifu_bid, lesson_bid, "", is_preview=preview)
        assert info.ask_model == (ask_model or course_model)
        assert info.ask_prompt == "Course follow-up prompt"
        assert info.model_args == {"temperature": Decimal("0.4")}
        assert info.ask_mode == 5103
        course.ask_enabled_status = 5102
        db.session.commit()
        disabled = get_follow_up_info_v2(
            app, shifu_bid, lesson_bid, "", is_preview=preview
        )
        assert disabled.ask_mode == 5102
        assert disabled.ask_model == (ask_model or course_model)
        db.session.rollback()


@pytest.mark.parametrize("course_model", ["course-main", ""])
def test_block_preview_uses_course_model_and_ignores_legacy_request_settings(
    app: Flask, monkeypatch: pytest.MonkeyPatch, course_model: str
) -> None:
    monkeypatch.setattr(context_v2, "get_allowed_models", list)
    request = PlaygroundPreviewRequest(
        block_index=0,
        model="legacy-block-model",
        temperature=1.8,
        document_prompt="Legacy request prompt",
    )
    course = SimpleNamespace(llm=course_model, llm_temperature=0.7)
    ctx = context_v2.RunScriptPreviewContextV2(app)
    model, temperature = ctx._resolve_llm_settings(course)
    assert model == (course_model or app.config["DEFAULT_LLM_MODEL"])
    assert temperature == 0.7
    assert {
        "model",
        "temperature",
        "document_prompt",
        "interaction_prompt",
        "interaction_error_prompt",
    }.isdisjoint(request.model_dump())
