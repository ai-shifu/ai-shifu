"""Disqualified question candidates retain native link-resource boundaries."""

import pytest
from flaskr.service.learn.agent.engine import collected_names, substitute_variables
from flaskr.service.learn.agent.engine.marker_context import analyze_marker_context
from flaskr.service.learn.agent.engine.tools import _script_questions
from flaskr.service.learn.agent.interaction_syntax import InteractionSyntaxFilter

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
    assert collected_names(source) == frozenset({"real"})
    assert [question.variable for question in _script_questions(source)] == ["real"]
    assert (
        substitute_variables(prefix + "{{ real }}", {"real": "VALUE"})
        == prefix + "VALUE"
    )
    _assert_streams(source, prefix, [QUESTION])


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize(
    "link", ["?[Label](dest/{{unfinished", "?[outer [inner](u)](dest/{{unfinished)"]
)
def test_incomplete_or_inactive_resources_keep_raw_marker_ownership(
    link: str, newline: str
) -> None:
    source = link + newline * 2 + QUESTION
    assert collected_names(source) == frozenset()
    assert all(question.variable != "real" for question in _script_questions(source))
    assert substitute_variables(source, {"real": "VALUE"}) == source
    _assert_streams(source, source, [])


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_replayed_labels_and_resources_keep_complete_names_exact(newline: str) -> None:
    prefix = "?[{{ a]b }}](dest/{{ value ? }})" + newline * 2
    source = prefix + QUESTION
    assert {marker.name for marker in analyze_marker_context(source).markers} == {
        "a]b",
        "value ?",
        "real",
    }
    assert [question.variable for question in _script_questions(source)] == ["real"]
    assert (
        substitute_variables(source, {"a]b": "LABEL", "value ?": "DEST"})
        == "?[LABEL](dest/DEST)" + newline * 2 + QUESTION
    )
    _assert_streams(source, prefix, [QUESTION])


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_only_an_adjacent_parenthesis_disqualifies_the_existing_control(
    newline: str,
) -> None:
    tail = " (dest/{{unfinished)" + newline * 2 + QUESTION
    source = "?[Label]" + tail
    assert [question.choices for question in _script_questions(source)] == [["Label"]]
    assert collected_names(source) == frozenset()
    _assert_streams(source, tail, ["?[Label]"])


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_marker_body_closing_brackets_do_not_trigger_link_fallback(
    newline: str,
) -> None:
    first = "?[%{{ a](b }} A|B]"
    source = first + newline * 2 + QUESTION
    assert collected_names(source) == frozenset({"a](b", "real"})
    assert [question.variable for question in _script_questions(source)] == [
        "a](b",
        "real",
    ]
    _assert_streams(source, newline * 2, [first, QUESTION])


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_a_marker_opened_inside_the_candidate_stays_atomic(newline: str) -> None:
    source = "?[{{unfinished](dest)" + newline * 2 + QUESTION
    assert collected_names(source) == frozenset()
    assert all(question.variable != "real" for question in _script_questions(source))
    _assert_streams(source, "", [source])
