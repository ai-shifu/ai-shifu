"""Keep blank outline prompts from masking inherited course instructions."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask
from flaskr.service.learn import follow_up_context


@pytest.mark.parametrize("preview_mode", [False, True])
@pytest.mark.parametrize(
    ("lesson_prompt", "chapter_prompt", "course_prompt", "expected"),
    [
        (None, None, "COURSE RULE", "COURSE RULE"),
        ("", "", "COURSE RULE", "COURSE RULE"),
        ("", " ", "COURSE RULE", "COURSE RULE"),
        ("", "\n", "COURSE RULE", "COURSE RULE"),
        (" \t\r\n", "\u3000\u00a0", "COURSE RULE", "COURSE RULE"),
        (" ", "CHAPTER RULE", "COURSE RULE", "CHAPTER RULE"),
        ("\n", "  CHAPTER RULE\n", "COURSE RULE", "  CHAPTER RULE\n"),
        ("  LESSON RULE\n", "CHAPTER RULE", "COURSE RULE", "  LESSON RULE\n"),
        ("LESSON RULE", "\n", "COURSE RULE", "LESSON RULE"),
        ("\n", " ", "", None),
        ("\n", " ", " \t\r\n\u3000\u00a0", None),
        ("", "", "  COURSE RULE\n", "  COURSE RULE\n"),
    ],
)
def test_blank_outline_prompts_inherit_nearest_substantive_prompt(
    monkeypatch: pytest.MonkeyPatch,
    preview_mode: bool,
    lesson_prompt: str | None,
    chapter_prompt: str | None,
    course_prompt: str,
    expected: str | None,
) -> None:
    """Draft and published lessons skip blank overrides and preserve real prompts."""
    outline_model = MagicMock()
    outline_model.query.filter.return_value.all.return_value = [
        SimpleNamespace(id="chapter-db", llm_system_prompt=chapter_prompt),
        SimpleNamespace(id="lesson-db", llm_system_prompt=lesson_prompt),
    ]
    course_model = MagicMock()
    course_model.query.filter.return_value.order_by.return_value.first.return_value = (
        SimpleNamespace(llm_system_prompt=course_prompt)
    )
    prefix = "Draft" if preview_mode else "Published"
    monkeypatch.setattr(follow_up_context, f"{prefix}OutlineItem", outline_model)
    monkeypatch.setattr(follow_up_context, f"{prefix}Shifu", course_model)

    result = follow_up_context.resolve_course_system_prompt(
        Flask("course-prompt-inheritance"),
        shifu_bid="course-1",
        outline_item_bid="lesson-1",
        preview_mode=preview_mode,
        outline_path=[
            SimpleNamespace(id="course-db", type="shifu"),
            SimpleNamespace(id="chapter-db", type="outline"),
            SimpleNamespace(id="lesson-db", type="outline"),
        ],
    )

    assert result == expected
