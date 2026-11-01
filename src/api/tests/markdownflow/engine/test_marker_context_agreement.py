"""Keep every view of the single marker scanner on one CommonMark answer.

The editor/publish document helpers and the engine's projection both read
``syntax.parser.marker_context``. Each case came from a differential run of the
two former scanners over the test corpus, real lessons and generated literal
contexts. The expected values follow CommonMark 0.31.2 as rendered by the web
client's parser (micromark).
"""

from dataclasses import dataclass

import pytest
from flaskr.service.learn.agent.interaction_syntax import InteractionSyntaxFilter
from markdownflow.engine.tools import _script_questions
from markdownflow.syntax.parser.document_context import (
    find_document_interaction_spans,
    find_document_protected_spans,
    find_document_variable_markers,
)
from markdownflow.syntax.parser.marker_context import (
    analyze_marker_context,
    marker_syntax_source,
)
from markdownflow.syntax.variable_names import (
    find_interaction_spans,
    normalize_variable_name,
    read_variable_marker,
)

QUESTION = "?[%{{ real }} A|B]"


@dataclass(frozen=True)
class Projection:
    """One scanner's answer: markers, literal flags, unclosed openers, controls."""

    markers: tuple[tuple[int, int, str, bool], ...]
    unclosed: tuple[int, ...]
    controls: tuple[tuple[int, int], ...]


def _syntax(text: str) -> Projection:
    units = list(find_document_protected_spans(text))
    live = set(units)
    return Projection(
        tuple(
            (
                marker.start,
                marker.end,
                marker.raw_name,
                (marker.start, marker.end) not in live,
            )
            for marker in find_document_variable_markers(text)
        ),
        tuple(
            start
            for start, _ in units
            if text.startswith("{{", start)
            and read_variable_marker(text, start) is None
        ),
        tuple(find_document_interaction_spans(text)),
    )


def _engine(text: str) -> Projection:
    context = analyze_marker_context(text)

    def literal(at: int) -> bool:
        return any(start <= at < end for start, end in context.literals)

    # Mirror engine.script._interaction_bindings: controls outside literals.
    syntax = list(marker_syntax_source(text, context))
    for opening, closing in context.literals:
        at = text.find("?[", opening, closing)
        while at >= 0:
            syntax[at] = "\x00"
            at = text.find("?[", at + 2, closing)
    return Projection(
        tuple(
            sorted(
                (marker.start, marker.end, marker.raw_name, literal(marker.start))
                for marker in context.markers
                if marker.complete
            )
        ),
        tuple(marker.start for marker in context.markers if not marker.complete),
        tuple(
            (start, end)
            for start, end in find_interaction_spans(
                text, syntax_source="".join(syntax)
            )
            if not literal(start)
        ),
    )


# (id, document, live names, literal names, controls, unclosed opener count)
CASES = [
    # Cause 1: one CommonMark 0.31.2 raw-HTML grammar.
    (
        "declaration-lowercase",
        "Text <!doctype {{ x> end\n\n" + QUESTION,
        {"real"},
        set(),
        [QUESTION],
        0,
    ),
    (
        "declaration-no-space",
        "<!DOCTYPE{{ x>\n\n" + QUESTION,
        {"real"},
        set(),
        [QUESTION],
        0,
    ),
    ("declaration-mixed-case", "x <!Ax{{ >", set(), set(), [], 0),
    ("declaration-block", "<!doctype\n{{ a }}\n>\n\n{{ b }}", {"b"}, {"a"}, [], 0),
    ("empty-comment", "<!-->{{ x\n\n" + QUESTION, {"real"}, set(), [QUESTION], 0),
    ("empty-comment-dash", "Text <!--->{{ a }}", {"a"}, set(), [], 0),
    (
        "ideographic-space-is-text",
        # Not a tag, so the example's first "}}" pair is the question's.
        'Text <span\u3000title="{{ x\n\n' + QUESTION,
        set(),
        set(),
        [],
        0,
    ),
    (
        "form-feed-is-text",
        'Text <span\x0ctitle="{{ a }}">s</span>',
        {"a"},
        set(),
        [],
        0,
    ),
    ("nbsp-is-text", 'Text <a\xa0href="{{ a }}">', {"a"}, set(), [], 0),
    (
        "control-in-unquoted-value",
        "Text <a href=a\x01{{ x>\n\n" + QUESTION,
        {"real"},
        set(),
        [QUESTION],
        0,
    ),
    ("one-line-ending-in-tag", 'Text <b\na="{{ a }}"> end', set(), {"a"}, [], 0),
    ("two-line-endings-end-tag", '<b\n\na="{{ a }}">', {"a"}, set(), [], 0),
    # Cause 2: an even backslash run does not escape the opener.
    ("double-backslash", "Text \\\\" + QUESTION, {"real"}, set(), [QUESTION], 0),
    ("single-backslash", "Text \\" + QUESTION, {"real"}, set(), [], 0),
    ("triple-backslash", "Text \\\\\\?[A|B]", set(), set(), [], 0),
    # Cause 3: an unclosed control never reaches past its paragraph.
    ("nested-unclosed", "?[ a ?[ b\n\n" + QUESTION, {"real"}, set(), [QUESTION], 0),
    (
        "emphasis-unclosed",
        "*?[ open* and _?[ open_\n\n" + QUESTION,
        {"real"},
        set(),
        [QUESTION],
        0,
    ),
    # Cause 4: a definition's label and title are separate inline texts.
    ("reference-label-title", '[{{ a]: /url "t }}"\n\n{{ b }}', {"b"}, set(), [], 0),
    ("reference-title", '[x]: /url "{{ a }}"\n\n{{ b }}', {"b"}, {"a"}, [], 0),
    # Inline HTML ends with its paragraph, as in micromark. Every token form
    # that may span lines is checked across a blank line and within one.
    *(
        case
        for form, (opening, closing) in {
            "declaration": ("<!doctype", ">"),
            "comment": ("<!--", "-->"),
            "instruction": ("<?x", "?>"),
            "cdata": ("<![CDATA[", "]]>"),
            "double-quoted": ('<a b="', '">'),
            "single-quoted": ("<a b='", "'>"),
        }.items()
        for case in (
            (
                f"{form}-stops-at-blank-line",
                f"Text {opening}{{{{ a }}}}\n\ny{closing} {{{{ b }}}}",
                {"a", "b"},
                set(),
                [],
                0,
            ),
            (
                f"{form}-stops-at-spaced-blank-line",
                f"Text {opening}{{{{ a }}}}\n \t\ny{closing} {{{{ b }}}}",
                {"a", "b"},
                set(),
                [],
                0,
            ),
            (
                f"{form}-continues-in-its-paragraph",
                f"Text {opening}{{{{ a }}}}\ny{closing} {{{{ b }}}}",
                {"b"},
                {"a"},
                [],
                0,
            ),
        )
    ),
    (
        "declaration-stops-at-heading",
        "Text <!doctype {{ a }}\n# H > {{ b }}",
        {"a", "b"},
        set(),
        [],
        0,
    ),
    (
        "comment-stops-at-thematic-break",
        "Text <!-- {{ a }}\n***\n--> {{ b }}",
        {"a", "b"},
        set(),
        [],
        0,
    ),
    (
        # Not HTML, so the example's first "}}" pair is the question's.
        "declaration-cannot-own-the-next-paragraph",
        "Text <!doctype{{ x\n\n" + QUESTION + ">",
        set(),
        set(),
        [],
        0,
    ),
    # HTML blocks of types 2-5 interrupt the paragraph holding an unfinished tag.
    *(
        (
            f"unfinished-tag-stops-at-{form}-block",
            f'Text <a title="{{{{ a }}}}\n{block}\nend"> {{{{ b }}}}',
            {"a", "b"},
            set(),
            [],
            0,
        )
        for form, block in {
            "comment": "<!-- block -->",
            "instruction": "<?x y ?>",
            "declaration": "<!X decl>",
            "cdata": "<![CDATA[ x ]]>",
        }.items()
    ),
    (
        "block-tag-attribute-stops-at-blank-line",
        '<div a="{{ a }}\n\n{{ b }}">',
        {"b"},
        {"a"},
        [],
        0,
    ),
]
CONTAINERS = [("", ""), ("> ", "> "), ("- ", "  ")]


def _wrap(source: str, first: str, continued: str, newline: str) -> str:
    lines = source.split("\n")
    return newline.join([first + lines[0], *(continued + line for line in lines[1:])])


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize(("first", "continued"), CONTAINERS)
@pytest.mark.parametrize(
    ("source", "live", "literal", "controls", "unclosed"),
    [case[1:] for case in CASES],
    ids=[case[0] for case in CASES],
)
def test_document_and_engine_views_return_the_commonmark_answer(
    source: str,
    live: set[str],
    literal: set[str],
    controls: list[str],
    unclosed: int,
    first: str,
    continued: str,
    newline: str,
) -> None:
    text = _wrap(source, first, continued, newline)
    syntax = _syntax(text)
    assert _engine(text) == syntax
    names = [(normalize_variable_name(raw), lit) for _, _, raw, lit in syntax.markers]
    assert {name for name, lit in names if name is not None and not lit} == live
    assert {name for name, lit in names if name is not None and lit} == literal
    assert [text[start:end] for start, end in syntax.controls] == controls
    assert len(syntax.unclosed) == unclosed
    # None of these controls sits in a literal, so the learner question list agrees.
    assert [
        (question.variable, [choice.strip() for choice in question.choices])
        for question in _script_questions(text)
    ] == [("real", ["A", "B"])] * len(controls)


@pytest.mark.parametrize("boundary", ["- b", "> b", "# H\n", "***\n", "```\nc\n```\n"])
def test_link_label_does_not_reach_across_a_block_boundary(boundary: str) -> None:
    # micromark renders "[a" and "](/u)" as text in separate blocks.
    text = "[a\n" + boundary + "](/u)"
    literals = [
        span
        for span in find_document_protected_spans(text)
        if text.startswith("(", span[0])
    ]
    assert literals == []


def test_container_inline_html_keeps_one_global_token_boundary() -> None:
    text = "> Text <!DOCTYPE x {{ a\n> b }}> end"
    syntax = _syntax(text)
    assert _engine(text) == syntax
    assert syntax.markers == ((19, 30, " a\n> b ", True),)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize(
    "opening", ["<!doctype ", '<span title="long', "<!-- ", "<?x ", "<![CDATA["]
)
def test_learner_filter_does_not_keep_html_open_across_a_blank_line(
    opening: str, newline: str
) -> None:
    # Not HTML, so the unfinished example's first "}}" pair is the question's.
    source = "Show " + opening + "{{ x" + newline * 2 + QUESTION + ">"
    streams = [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]
    for stream in streams:
        syntax = InteractionSyntaxFilter()
        output = "".join(syntax.feed(chunk) for chunk in stream) + syntax.flush()
        assert syntax.spans == [], stream
        assert output == source


@pytest.mark.parametrize(
    ("source", "spans"),
    [
        ("Text \\\\" + QUESTION, [QUESTION]),
        ("Text \\" + QUESTION, []),
        ("Text \\\\\\" + QUESTION, []),
    ],
)
def test_learner_filter_counts_the_whole_backslash_run(
    source: str, spans: list[str]
) -> None:
    for chunk_size in (1, 2, 3, len(source)):
        syntax = InteractionSyntaxFilter()
        output = (
            "".join(
                syntax.feed(source[at : at + chunk_size])
                for at in range(0, len(source), chunk_size)
            )
            + syntax.flush()
        )
        assert syntax.spans == spans, chunk_size
        assert output + "".join(spans) == source


@pytest.mark.parametrize(
    ("text", "uses_syntax"),
    [
        ("?[A|B]", True),
        ("\\?[A|B]", False),
        ("\\\\?[A|B]", True),
        ("\\\\\\?[A|B]", False),
    ],
    ids=["plain", "escaped", "escaped-backslash", "escaped-after-escaped-backslash"],
)
def test_syntax_detection_counts_the_backslash_run(
    text: str, uses_syntax: bool
) -> None:
    # An even run is escaped backslashes, so the control still makes the script use syntax.
    from markdownflow.engine.script import detect_syntax

    assert detect_syntax(text) is uses_syntax
