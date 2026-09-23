"""Course-wide credit feature extraction follows the teaching engines."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from flaskr.service.learn.api import (
    build_course_prompt,
    render_course_prompt_identity_variables,
)
from flaskr.service.shifu.admin_operations.course_completion_credit_features import (
    CourseCreditFeatures,
    build_course_completion_credit_features,
    detect_authored_language,
)
from markdown_flow import MarkdownFlow


def _item(
    bid: str,
    content: str = "",
    *,
    parent_bid: str = "",
    prompt: str = "",
) -> SimpleNamespace:
    return SimpleNamespace(
        outline_item_bid=bid,
        parent_bid=parent_bid,
        llm_system_prompt=prompt,
        content=content,
    )


def _features(
    items: list[SimpleNamespace],
    leaves: list[str],
    *,
    engine: str = "1.0",
    course_prompt: str = "course prompt",
) -> CourseCreditFeatures:
    return build_course_completion_credit_features(
        course=SimpleNamespace(llm_system_prompt=course_prompt),
        outline_items=items,
        visible_leaf_outline_bids=leaves,
        engine=engine,
        language="zh",
    )


def test_v1_uses_parser_blocks_and_preserves_unicode_and_code() -> None:
    content = (
        "说明🎯\n---\n```python\nprint('你好')\n```\n"
        "---\n!===\n静态🎯\n!===\n---\n?[%{{answer}} A | B]"
    )
    result = _features([_item("lesson", content)], ["lesson"])

    assert result.lesson_count == 1
    assert result.dynamic_chars_k == pytest.approx(
        (len("说明🎯") + len("```python\nprint('你好')\n```")) / 1000
    )
    assert result.static_chars_k == len("静态🎯") / 1000
    assert result.generated_block_count == 2
    assert result.interaction_count == 1
    assert result.system_chars_k > len("course prompt") / 1000
    assert tuple(result.as_mapping()) == (
        "lesson_count",
        "dynamic_chars_k",
        "static_chars_k",
        "system_chars_k",
        "generated_block_count",
        "interaction_count",
        "char_square_k2",
        "chars_system_k2",
        "chars_blocks_k",
    )


def test_prompt_inheritance_prefers_nearest_ancestor_then_lesson() -> None:
    base = [_item("chapter", prompt="parent instruction")]
    inherited = _features(
        [*base, _item("one", "Teach this", parent_bid="chapter")], ["one"]
    )
    overridden = _features(
        [*base, _item("one", "Teach this", parent_bid="chapter", prompt="x")],
        ["one"],
    )
    course = _features([_item("one", "Teach this")], ["one"])

    assert inherited.system_chars_k - overridden.system_chars_k == pytest.approx(
        (len("parent instruction") - 1) / 1000
    )
    assert course.system_chars_k - overridden.system_chars_k == pytest.approx(
        (len("course prompt") - 1) / 1000
    )


def test_v1_system_chars_match_runtime_composed_prompt_baseline() -> None:
    prompt = "  Teach patiently with {{sys_user_background}}.\n"
    result = _features([_item("lesson", "Teach this", prompt=prompt)], ["lesson"])
    composed = build_course_prompt(prompt, variables={})
    composed = render_course_prompt_identity_variables(composed, {})
    messages = MarkdownFlow(
        "Teach this", document_prompt=composed
    ).get_content_messages(0, variables={})

    assert result.system_chars_k == len(messages[0]["content"]) / 1000
    assert result.system_chars_k > len(prompt) / 1000 + 1


def test_whole_course_interactions_capture_long_vs_many_lessons() -> None:
    one_long = _features([_item("long", "a" * 2000)], ["long"])
    many_short = _features([_item("a", "a" * 1000), _item("b", "b" * 1000)], ["a", "b"])

    assert one_long.dynamic_chars_k == many_short.dynamic_chars_k == 2
    assert one_long.char_square_k2 == 4
    assert many_short.char_square_k2 == 2
    assert one_long.lesson_count == 1
    assert many_short.lesson_count == 2
    assert many_short.system_chars_k == pytest.approx(2 * one_long.system_chars_k)
    assert one_long.chars_system_k2 == pytest.approx(many_short.chars_system_k2)


def test_v2_counts_full_script_and_not_unused_course_prompt() -> None:
    content = "Explain this.\n---\nAsk ?[%{{x}} A | B]\n```\n?[example]\n```"
    item = _item("lesson", content)
    first = _features([item], ["lesson"], engine="2.0", course_prompt="short")
    second = _features([item], ["lesson"], engine="2.0", course_prompt="a" * 10000)

    assert first == second
    assert first.dynamic_chars_k == len(content) / 1000
    assert first.static_chars_k == 0
    assert first.generated_block_count == 1
    assert first.interaction_count == 1
    assert first.system_chars_k > 1


@pytest.mark.parametrize(
    ("items", "leaves"),
    [
        ([], []),
        ([], ["missing"]),
        ([_item("lesson", "")], ["lesson"]),
        ([_item("lesson", "text", parent_bid="missing")], ["lesson"]),
        ([_item("a", "text", parent_bid="a")], ["a"]),
    ],
)
def test_incomplete_outline_is_rejected(
    items: list[SimpleNamespace], leaves: list[str]
) -> None:
    with pytest.raises(
        ValueError, match=r"course has|visible lessons|visible lesson|ancestor|cycle"
    ):
        _features(items, leaves)


def test_unsupported_engine_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported teaching engine"):
        _features([_item("a", "content")], ["a"], engine="3.0")


@pytest.mark.parametrize(
    ("content", "language"),
    [
        ("学习这些基础概念并完成练习，然后用自己的话说明其中的区别。" * 3, "zh"),
        ("اقرأ هذا الدرس بعناية ثم اشرح الفكرة وأجب عن السؤال التالي. " * 3, "ar"),
        ("อ่านข้อความนี้แล้วอธิบายแนวคิดด้วยคำของคุณเองก่อนตอบคำถาม " * 3, "th"),
        ("This is the lesson and you have the examples for your practice. " * 4, "en"),
        (
            "Cette leçon est pour vous et nous allons voir les exemples dans cette partie. "
            * 4,
            "fr",
        ),
        ("Tiny lesson", "und"),
    ],
)
def test_authored_language_requires_strong_script_evidence(
    content: str, language: str
) -> None:
    assert detect_authored_language([_item("a", content)], ["a"]) == language


def test_authored_language_ignores_fenced_code_and_ambiguous_scripts() -> None:
    code = "```\n" + ("This is the lesson and you have the examples. " * 4) + "\n```"
    assert detect_authored_language([_item("a", code)], ["a"]) == "und"
    mixed = (
        "学习这些基础概念并完成练习，然后用自己的话说明其中的区别。" * 4
        + "This is the lesson and you have the examples for your practice. " * 4
    )
    assert detect_authored_language([_item("a", mixed)], ["a"]) == "und"
