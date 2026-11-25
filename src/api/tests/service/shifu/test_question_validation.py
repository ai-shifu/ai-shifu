"""Protect the boundary between authored questions and system references."""

import json
from pathlib import Path

import pytest
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.shifu.question_validation import (
    assert_course_question_names_allowed,
    assert_course_question_names_within_limit,
)
from markdownflow import MarkdownFlowDocument


@pytest.mark.parametrize(
    "content",
    [
        "?[{{sys_}} Yes | No]",
        "?[%{{sys_custom}} ...Answer]",
        "?[{{ sys_user_nickname }} ...Answer]",
        "?[ %{{\u3000sys_自定义\u3000}} A || B]",
        "> ?[{{sys_custom}} Yes | No]",
        "1. ?[{{sys_custom}} Yes | No]",
        "?[{{ordinary}} Yes | No]\n\n?[{{sys_custom}} ...Answer]",
    ],
)
def test_reserved_question_names_are_rejected(content: str) -> None:
    with pytest.raises(AppError) as exc_info:
        assert_course_question_names_allowed(MarkdownFlowDocument(content))

    assert exc_info.value.code == ERROR_CODE["server.profile.keyReserved"]


@pytest.mark.parametrize(
    "content",
    [
        "Hello {{sys_user_nickname}} and %{{sys_custom}}.",
        "?[{{ordinary}} {{sys_user_nickname}} | Other]",
        "?[{{SYS_custom}} Yes | No]",
        "?[{{my_sys_custom}} Yes | No]",
        "?[Yes | No]",
        "```md\n?[{{sys_custom}} Yes | No]\n```",
        "`?[{{sys_custom}} Yes | No]`",
        "<!-- ?[{{sys_custom}} Yes | No] -->",
        r"\?[{{sys_custom}} Yes | No]",
        "?[{{sys_custom}} Yes | No](https://example.com)",
        "![{{sys_custom}}](image.png)",
        "?[{{sys_custom}}",
    ],
)
def test_system_references_and_literal_examples_remain_allowed(content: str) -> None:
    assert_course_question_names_allowed(MarkdownFlowDocument(content))


@pytest.mark.parametrize("filename", ["cn_demo.json", "en_demo.json"])
def test_bundled_demo_questions_obey_the_course_namespace(filename: str) -> None:
    path = Path(__file__).parents[3] / "demo_shifus" / filename
    demo = json.loads(path.read_text(encoding="utf-8"))

    for outline in demo["outline_items"]:
        assert_course_question_names_allowed(
            MarkdownFlowDocument(outline.get("content", ""))
        )


@pytest.mark.parametrize(
    "content",
    [
        "?[{{" + "q" * 201 + "}} ...Answer]",
        "?[%{{" + "问" * 201 + "}} Yes | No]",
        "Hello {{" + "q" * 201 + "}}.",
        "?[{{short}} Yes | No]\n\nHello %{{" + "😀" * 201 + "}}.",
    ],
)
def test_questions_over_the_length_limit_are_rejected(content: str) -> None:
    with pytest.raises(AppError) as exc_info:
        assert_course_question_names_within_limit(MarkdownFlowDocument(content))

    assert exc_info.value.code == ERROR_CODE["server.profile.keyTooLong"]


def test_length_error_names_the_limit_and_a_short_preview(app: object) -> None:
    question = "Which topic " + "q" * 189
    with app.app_context(), pytest.raises(AppError) as exc_info:
        assert_course_question_names_within_limit(
            MarkdownFlowDocument(f"?[{{{{{question}}}}} ...Answer]")
        )

    message = exc_info.value.message
    assert "201/200" in message
    assert question[:20] in message
    assert question[:21] not in message


@pytest.mark.parametrize(
    "content",
    [
        "?[{{" + "q" * 200 + "}} ...Answer]",
        "?[{{" + "问" * 200 + "}} Yes | No]",
        "?[{{ " + "😀" * 200 + " }} ...Answer]",
        "```md\n{{" + "q" * 201 + "}}\n```",
        "<!-- {{" + "q" * 201 + "}} -->",
    ],
)
def test_questions_within_the_limit_or_in_literal_examples_are_allowed(
    content: str,
) -> None:
    assert_course_question_names_within_limit(MarkdownFlowDocument(content))


@pytest.mark.parametrize("filename", ["cn_demo.json", "en_demo.json"])
def test_bundled_demo_questions_obey_the_length_limit(filename: str) -> None:
    path = Path(__file__).parents[3] / "demo_shifus" / filename
    demo = json.loads(path.read_text(encoding="utf-8"))

    for outline in demo["outline_items"]:
        assert_course_question_names_within_limit(
            MarkdownFlowDocument(outline.get("content", ""))
        )
