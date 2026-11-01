"""A `?[...]` inside literal Markdown is an example of the notation, never a question.

Every consumer reads the shared marker scanner: the engine's script questions,
collected bindings and syntax detection, authored input hints, and the learner
runtime filter on streamed narration. The literal contexts follow CommonMark as
the web client renders them (micromark with remark-math).
"""

import pytest
from flaskr.service.learn.agent.interaction_syntax import InteractionSyntaxFilter
from markdownflow.engine.script import collected_names, detect_syntax
from markdownflow.engine.tools import _script_questions, script_text_inputs
from markdownflow.syntax.parser.document_context import (
    find_document_interaction_spans,
)

EXAMPLE = "?[{{ example }} A | ...Example]"
PLAIN = "?[A | B]"
QUESTION = "?[%{{ real }} C | ...Real]"

LITERALS = {
    "backtick-fence": "```\n" + EXAMPLE + "\n```",
    "tilde-fence": "~~~md\n" + EXAMPLE + "\n~~~",
    "indented-code": "Intro\n\n    " + EXAMPLE,
    "inline-code": "Write `" + EXAMPLE + "` here.",
    "double-backtick-code": "Write `` a ` " + EXAMPLE + " `` here.",
    "html-block": "<div>\n" + EXAMPLE + "\n</div>",
    "raw-html-block": "<script>\n" + EXAMPLE + "\n</script>",
    "html-comment": "Text <!-- " + EXAMPLE + " --> end.",
    "inline-html-attribute": 'Text <span title="' + EXAMPLE + '">x</span>',
    "link-destination": "[text](<" + EXAMPLE + ">)",
    "link-title": '[text](/url "' + EXAMPLE + '")',
    "reference-title": '[ref]: /url "' + EXAMPLE + '"',
    "inline-math": "Math $" + EXAMPLE + "$ here.",
    "display-math": "$$\n" + EXAMPLE + "\n$$",
    "autolink": "<https://example.com/?[A|B]>",
}
# Not literal under CommonMark, so the control stays a question.
LIVE = {
    "backtick-in-fence-info": "``` a`b\n" + EXAMPLE,
    "indented-continuation": "Intro\n    " + EXAMPLE,
    "unmatched-backtick": "Write ` " + EXAMPLE,
}
CONTAINERS = [("", ""), ("> ", "> "), ("- ", "  ")]


def _wrap(source: str, first: str, continued: str, newline: str) -> str:
    lines = source.split("\n")
    return newline.join([first + lines[0], *(continued + line for line in lines[1:])])


def _streams(source: str) -> list[list[str]]:
    return [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(1, len(source))
    ]


def _assert_filter(source: str, spans: list[str]) -> None:
    shown = source
    for span in spans:
        shown = shown.replace(span, "", 1)
    for stream in _streams(source):
        syntax = InteractionSyntaxFilter()
        output = "".join(syntax.feed(part) for part in stream) + syntax.flush()
        assert (output, syntax.spans) == (shown, spans), stream


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize(("first", "continued"), CONTAINERS)
@pytest.mark.parametrize("example", list(LITERALS.values()), ids=list(LITERALS))
def test_literal_example_is_not_a_question_anywhere(
    example: str, first: str, continued: str, newline: str
) -> None:
    source = _wrap(example + "\n\n" + QUESTION, first, continued, newline)
    spans = [
        source[start:end] for start, end in find_document_interaction_spans(source)
    ]
    assert spans == [QUESTION]
    assert [question.variable for question in _script_questions(source)] == ["real"]
    assert [question.placeholder for question in script_text_inputs(source)] == ["Real"]
    assert "example" not in collected_names(source)
    # Without the example, nothing else in the text is MarkdownFlow notation.
    plain = _wrap(example.replace(EXAMPLE, PLAIN), first, continued, newline)
    assert not detect_syntax(plain)
    _assert_filter(source, [QUESTION])


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("example", list(LIVE.values()), ids=list(LIVE))
def test_non_literal_lookalikes_stay_questions(example: str, newline: str) -> None:
    source = (example + "\n\n" + QUESTION).replace("\n", newline)
    assert [question.variable for question in _script_questions(source)] == [
        "example",
        "real",
    ]
    assert detect_syntax(example.replace("\n", newline))
    _assert_filter(source, [EXAMPLE, QUESTION])


def test_streamed_question_waits_for_an_unmatched_backtick_to_be_decided() -> None:
    syntax = InteractionSyntaxFilter()
    shown = syntax.feed("Write `" + EXAMPLE)
    # The code span may still close, so the example is held, not released.
    assert shown == "Write `"
    assert syntax.spans == []
    shown += syntax.feed("` here.\n\n" + QUESTION) + syntax.flush()
    assert shown == "Write `" + EXAMPLE + "` here.\n\n"
    assert syntax.spans == [QUESTION]


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_unclosed_fence_keeps_everything_after_it_as_code(newline: str) -> None:
    source = ("Intro\n\n```\n" + EXAMPLE + "\n\n" + QUESTION).replace("\n", newline)
    assert _script_questions(source) == []
    _assert_filter(source, [])
