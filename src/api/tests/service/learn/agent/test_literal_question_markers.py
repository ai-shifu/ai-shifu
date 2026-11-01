"""A `?[...]` inside literal Markdown is an example of the notation, never a question.

Every consumer reads the shared marker scanner: the engine's script questions,
collected bindings and syntax detection, authored input hints, and the learner
runtime filter on streamed narration. The literal contexts follow CommonMark as
the web client renders them (micromark with remark-math).
"""

import time

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


@pytest.mark.parametrize("opening", ["Use the ` key ", "`", "Cost $5 and "])
def test_held_question_keeps_streaming_work_linear(
    opening: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A question held behind an undecided run must not rescan per delta."""
    from flaskr.service.learn.agent import interaction_syntax
    from markdownflow.engine import stream_marker_context

    inspected = 0
    original = interaction_syntax.analyze_marker_context

    def counted(source: str, **kwargs: object) -> object:
        nonlocal inspected
        inspected += len(source)
        return original(source, **kwargs)

    monkeypatch.setattr(interaction_syntax, "analyze_marker_context", counted)
    monkeypatch.setattr(stream_marker_context, "analyze_marker_context", counted)
    question = "?[OK|Cancel]"
    tail = "and then the lesson goes on " * 720  # About 20,000 characters.
    syntax = InteractionSyntaxFilter()
    shown = syntax.feed(opening + question + " ")
    started = time.perf_counter()
    narrated_before_end = False
    for character in tail:
        released = syntax.feed(character)
        shown += released
        narrated_before_end = narrated_before_end or bool(released)
    shown += syntax.flush()
    assert time.perf_counter() - started < 1.0
    assert narrated_before_end
    assert syntax.spans == [question]
    assert shown == opening + " " + tail
    assert inspected <= 40 * len(tail)


def test_narration_after_a_decided_paragraph_flows_before_flush() -> None:
    """Once the paragraph ends, the held question is decided and narration resumes."""
    syntax = InteractionSyntaxFilter()
    shown = syntax.feed("Press ` then " + QUESTION)
    assert shown == "Press ` then "
    # A blank line ends the paragraph: the backtick can no longer close.
    shown += syntax.feed(" ok.\n\nNext paragraph")
    assert syntax.spans == [QUESTION]
    assert shown == "Press ` then  ok.\n\nNext paragraph"
    assert syntax.flush() == ""


def test_narration_after_a_closed_code_span_flows_before_flush() -> None:
    syntax = InteractionSyntaxFilter()
    shown = syntax.feed("Type `" + EXAMPLE)
    shown += syntax.feed(" exactly` and continue")
    assert syntax.spans == []
    assert shown == "Type `" + EXAMPLE + " exactly` and continue"
