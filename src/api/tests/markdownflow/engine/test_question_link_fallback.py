"""Disqualified question candidates retain native link-resource boundaries."""

import pytest
from flaskr.service.learn.agent.interaction_syntax import InteractionSyntaxFilter
from markdownflow.engine import collected_questions
from markdownflow.engine.marker_context import analyze_marker_context
from markdownflow.engine.tools import _script_questions

QUESTION = "?[%{{ real }} A|B]"
LINKS = [
    "?[Label](dest/{{unfinished)",
    "?[Label](<dest/{{unfinished>)",
    '?[Label](dest "{{unfinished")',
    "?[Label](dest '{{unfinished')",
    "?[Label](dest ({{unfinished))",
    "?[Label](d(n)/{{unfinished)",
]


def _assert_streams(source: str, shown: str, spans: list[str]) -> None:
    for stream in [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]:
        syntax = InteractionSyntaxFilter()
        actual = "".join(syntax.feed(chunk) for chunk in stream) + syntax.flush()
        assert (actual, syntax.spans) == (shown, spans), stream


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("link", LINKS)
def test_disqualified_question_replays_its_native_link_label(
    link: str, newline: str
) -> None:
    prefix = link + newline * 2
    source = prefix + QUESTION
    assert collected_questions(source) == frozenset({"real"})
    assert [question.question for question in _script_questions(source)] == ["real"]
    _assert_streams(source, prefix, [QUESTION])


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize(
    "link", ["?[Label](dest/{{unfinished", "?[outer [inner](u)](dest/{{unfinished)"]
)
def test_standalone_braces_in_incomplete_resources_do_not_hide_later_questions(
    link: str, newline: str
) -> None:
    source = link + newline * 2 + QUESTION
    assert collected_questions(source) == frozenset({"real"})
    assert [question.question for question in _script_questions(source)] == ["real"]
    _assert_streams(source, link + newline * 2, [QUESTION])


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_replayed_labels_and_resources_keep_complete_names_exact(newline: str) -> None:
    prefix = "?[{{ a\\]b }}](dest/{{ value ? }})" + newline * 2
    source = prefix + QUESTION
    assert {marker.name for marker in analyze_marker_context(source).markers} == {
        "real"
    }
    assert [question.question for question in _script_questions(source)] == ["real"]
    _assert_streams(source, prefix, [QUESTION])


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_only_an_adjacent_parenthesis_disqualifies_the_existing_control(
    newline: str,
) -> None:
    tail = " (dest/{{unfinished)" + newline * 2 + QUESTION
    source = "?[Label]" + tail
    assert [question.question for question in _script_questions(source)] == [
        None,
        "real",
    ]
    assert collected_questions(source) == frozenset({"real"})
    _assert_streams(source, tail[: -len(QUESTION)], ["?[Label]", QUESTION])


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_marker_body_closing_brackets_do_not_trigger_link_fallback(
    newline: str,
) -> None:
    first = "?[%{{ a](b }} A|B]"
    source = first + newline * 2 + QUESTION
    assert collected_questions(source) == frozenset({"a](b", "real"})
    assert [question.question for question in _script_questions(source)] == [
        "a](b",
        "real",
    ]
    _assert_streams(source, newline * 2, [first, QUESTION])


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_unfinished_brace_groups_inside_an_actual_control_remain_atomic(
    newline: str,
) -> None:
    source = "?[{{unfinished](dest)" + newline * 2 + QUESTION
    assert collected_questions(source) == frozenset()
    assert [question.question for question in _script_questions(source)] == [None]
    _assert_streams(source, "", [source])
