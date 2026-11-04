"""Read bound course instructions without consulting retired outline prompts."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask
from flaskr.service.learn.ask import context as follow_up_context


class _OutlineWithoutPrompt:
    """Fail if a resolver attempts to read the removed outline setting."""

    def __init__(self, row_id: str) -> None:
        self.id = row_id

    @property
    def llm_system_prompt(self) -> str:
        message = "Outline teaching prompts have been retired"
        raise AssertionError(message)


@pytest.mark.parametrize("preview_mode", [False, True])
@pytest.mark.parametrize(
    ("course_prompt", "expected"),
    [
        ("COURSE RULE", "COURSE RULE"),
        ("", None),
        (None, None),
        (" \t\r\n\u3000\u00a0", None),
        ("  COURSE RULE\n", "  COURSE RULE\n"),
    ],
)
def test_follow_up_reads_only_the_bound_course_prompt(
    monkeypatch: pytest.MonkeyPatch,
    preview_mode: bool,
    course_prompt: str | None,
    expected: str | None,
) -> None:
    """Preview and published runs work with no readable outline prompt field."""
    outline_model = MagicMock()
    outline_model.query.filter.return_value.all.return_value = [
        _OutlineWithoutPrompt("chapter-db"),
        _OutlineWithoutPrompt("lesson-db"),
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
