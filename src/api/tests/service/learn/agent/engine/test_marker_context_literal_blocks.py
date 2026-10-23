"""Keep incomplete Markdown examples inside their literal document regions."""

import pytest
from flaskr.service.learn.agent.engine import collected_names, substitute_variables
from flaskr.service.learn.agent.engine.marker_context import analyze_marker_context
from flaskr.service.learn.agent.engine.tools import _script_questions
from flaskr.service.learn.agent.interaction_syntax import InteractionSyntaxFilter


@pytest.mark.parametrize(
    "prefix",
    [
        "    {{ unfinished\n\n",
        "\t{{ unfinished\n\n",
        " \t{{ unfinished\n\n",
        "Text\n\n    {{ unfinished\n\n",
        *[
            f"<{tag}>\n{{{{ unfinished\n</{tag.upper()}>\n"
            for tag in ("script", "style", "pre", "textarea")
        ],
    ],
)
def test_block_examples_do_not_consume_external_named_questions(prefix: str) -> None:
    question = "?[%{{ real }} A|B]"
    source = prefix + question
    assert collected_names(source) == frozenset({"real"})
    assert [marker.name for marker in analyze_marker_context(source).markers] == [
        "real"
    ]
    questions = _script_questions(source)
    assert len(questions) == 1
    assert questions[0].variable == "real"
    assert [choice.strip() for choice in questions[0].choices] == ["A", "B"]
    assert (
        substitute_variables(prefix + "{{ real }}", {"real": "VALUE"})
        == prefix + "VALUE"
    )


@pytest.mark.parametrize("width", [2, 3, 4])
def test_escaped_first_tick_keeps_suffix_code_boundary_across_consumers(
    width: int,
) -> None:
    prefix = "\\" + "`" * width + "{{" + "`" * (width - 1) + "\n"
    question = "?[%{{ real }} A|B]"
    source = prefix + question
    assert collected_names(source) == frozenset({"real"})
    assert _script_questions(source)[0].variable == "real"
    assert (
        substitute_variables(prefix + "{{ real }}", {"real": "VALUE"})
        == prefix + "VALUE"
    )
    for chunk_size in (1, 2, len(source)):
        syntax = InteractionSyntaxFilter()
        output = (
            "".join(
                syntax.feed(source[at : at + chunk_size])
                for at in range(0, len(source), chunk_size)
            )
            + syntax.flush()
        )
        assert output == prefix
        assert syntax.spans == [question]


def test_block_literals_preserve_complete_markers_and_separate_opening_attributes() -> (
    None
):
    source = (
        '<script title="{{">\n%{{ example }} {{ value }}\n</script>\n?[%{{ real }} A|B]'
    )
    assert collected_names(source) == frozenset({"example", "real"})
    assert substitute_variables(source, {"value": "VALUE"}) == source.replace(
        "{{ value }}", "VALUE"
    )


@pytest.mark.parametrize(
    "prefix",
    [
        "$x {{ y$",
        "$$x {{ y$$",
        r"\$$x {{ y$",
        '[x](url "{{")',
        "[x](url '{{')",
        "[x](url ({{))",
        '[x](u(n) "{{")',
        '[x](<url> "{{")',
        '![x](url "{{")',
        '[x](url\n "{{")',
    ],
)
def test_math_and_link_examples_cannot_hide_the_following_real_question(
    prefix: str,
) -> None:
    source = prefix + "\n\n?[%{{ real }} A|B]"
    assert collected_names(source) == frozenset({"real"})
    questions = _script_questions(source)
    assert len(questions) == 1
    assert questions[0].variable == "real"
    assert (
        substitute_variables(prefix + "\n\n{{ real }}", {"real": "VALUE"})
        == prefix + "\n\nVALUE"
    )


@pytest.mark.parametrize(
    "source",
    ["$x %{{ example }} {{ value }}$", '[x](url "%{{ example }} {{ value }}")'],
)
def test_complete_math_and_resource_examples_keep_exact_variable_names(
    source: str,
) -> None:
    assert collected_names(source) == frozenset({"example"})
    assert substitute_variables(source, {"value": "VALUE"}) == source.replace(
        "{{ value }}", "VALUE"
    )


def test_completed_inner_link_disables_an_outer_link_but_allows_an_image() -> None:
    inactive = '[outer [inner](u)](u "{{")\n\n?[%{{ real }} A|B]'
    assert collected_names(inactive) == frozenset()
    image = '![outer [inner](u)](u "{{")\n\n?[%{{ real }} A|B]'
    assert collected_names(image) == frozenset({"real"})


@pytest.mark.parametrize("delimiter", ["`", "$"])
def test_heading_boundaries_do_not_pair_inline_delimiters_across_lines(
    delimiter: str,
) -> None:
    source = "# Heading " + delimiter + "{{\nq" + delimiter + " then ?[%{{ real }} A|B]"
    assert collected_names(source) == frozenset()
    assert [marker.name for marker in analyze_marker_context(source).markers] == [
        "q" + delimiter + " then ?[%{{ real"
    ]
    assert _script_questions(source) == []
    same_line = "# Heading " + delimiter + "{{" + delimiter + "\n\n?[%{{ real }} A|B]"
    assert collected_names(same_line) == frozenset({"real"})
    assert len(_script_questions(same_line)) == 1


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_raw_html_closing_line_bounds_local_examples(newline: str) -> None:
    prefix = newline.join(["<script>", "code", "</script> {{ unfinished", ""])
    source = prefix + "?[%{{ real }} A|B]"
    assert collected_names(source) == frozenset({"real"})
    assert _script_questions(source)[0].variable == "real"
    complete = prefix.replace("{{ unfinished", "{{ example }}") + "{{ real }}"
    assert substitute_variables(
        complete, {"example": "local", "real": "outside"}
    ).endswith("local" + newline + "outside")


def test_partial_document_metadata_exposes_raw_html_closing_line_and_link_state() -> (
    None
):
    opened = analyze_marker_context("<script>body", final=False)
    assert opened.pending_raw_html_tag == "script"
    assert opened.pending_raw_html_closed is False
    closed = analyze_marker_context("<script></script> {{", final=False)
    assert closed.pending_raw_html_tag == "script"
    assert closed.pending_raw_html_closed is True
    assert (
        analyze_marker_context("<script></script>\n", final=False).pending_raw_html_tag
        is None
    )
    label = analyze_marker_context("![outer [inner", final=False)
    assert label.pending_labels == [(True, True), (False, True)]
    opener = analyze_marker_context("![image]", final=False)
    assert opener.pending_resource_opener is True
    assert opener.pending_resource_image is True


@pytest.mark.parametrize("width", [2, 3, 4])
def test_escaped_first_dollar_suffix_bounds_examples(width: int) -> None:
    prefix = "\\" + "$" * width + "{{" + "$" * (width - 1)
    source = prefix + "\n\n?[%{{ real }} A|B]"
    assert collected_names(source) == frozenset({"real"})
    assert _script_questions(source)[0].variable == "real"


@pytest.mark.parametrize(
    ("depth", "expected"), [(32, frozenset({"real"})), (33, frozenset())]
)
def test_link_destination_nesting_uses_the_native_limit(
    depth: int, expected: frozenset[str]
) -> None:
    source = (
        "[x]("
        + "(" * depth
        + "u"
        + ")" * depth
        + ' "{{ unfinished")\n\n?[%{{ real }} A|B]'
    )
    assert collected_names(source) == expected


@pytest.mark.parametrize("images", [False, True])
def test_many_link_ancestors_keep_native_active_state_without_repeated_work(
    images: bool,
) -> None:
    count = 2048
    source = ("![" if images else "[") * count + "[x](u)" * count
    context = analyze_marker_context(source)
    assert len(context.pending_labels) == count
    assert all(
        image == images and active == images for image, active in context.pending_labels
    )
    assert (
        substitute_variables(source + " {{ real }}", {"real": "VALUE"})
        == source + " VALUE"
    )


LATE_CONTEXT_PREFIXES = [
    "- ~~~\n  {{ unfinished\n  ~~~\n",
    "> ~~~\n> {{ unfinished\n> ~~~\n",
    "> - ~~~\n>   {{ unfinished\n>   ~~~\n",
    "1. ~~~\n   {{ unfinished\n   ~~~\n",
    "- > ~~~\n  > {{ unfinished\n  > ~~~\n",
    "~~~\n{{ unfinished\n~~~\n",
    "<div>\n{{ unfinished\n</div>\n\n",
    "<custom>\n{{ unfinished\n</custom>\n\n",
    "# Title\n    {{ unfinished\n\n",
    "~~~\ncode\n~~~\n    {{ unfinished\n\n",
    "Text\n---\n    {{ unfinished\n\n",
    "Text\n===\n    {{ unfinished\n\n",
    '[foo]: /url "{{ unfinished"\n\n',
    '[foo]: /url\n  "{{ unfinished"\n\n',
    "?[ unfinished\n\n`{{`\n\n",
]


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("prefix", LATE_CONTEXT_PREFIXES)
def test_late_document_contexts_keep_external_names_and_exact_raw_offsets(
    prefix: str, newline: str
) -> None:
    prefix = prefix.replace("\n", newline)
    source = prefix + "?[%{{ real }} A|B]"
    assert collected_names(source) == frozenset({"real"})
    assert _script_questions(source)[-1].variable == "real"
    assert (
        substitute_variables(prefix + "{{ real }}", {"real": "VALUE"})
        == prefix + "VALUE"
    )
    for marker in analyze_marker_context(source).markers:
        assert marker.raw_name == source[marker.start + 2 : marker.end - 2]


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize(
    ("delimiter", "container"),
    [
        ("`", "> "),
        ("`", "- "),
        ("$", "> "),
        ("$", "1. "),
        ("`", "---\n"),
        ("$", "---\n"),
        ("`", "<div>\n"),
        ("$", "<div>\n"),
    ],
)
def test_new_container_paragraph_does_not_close_an_earlier_inline_literal(
    newline: str, delimiter: str, container: str
) -> None:
    container = container.replace("\n", newline)
    source = (
        "Text "
        + delimiter
        + "{{ unfinished"
        + newline
        + container
        + delimiter
        + " end"
        + newline * 2
        + "?[%{{ real }} A|B]"
    )
    assert collected_names(source) == frozenset()
    assert _script_questions(source) == []


@pytest.mark.parametrize("prefix", ["2. ", "x > "])
def test_noninterrupting_line_keeps_the_complete_inline_literal(prefix: str) -> None:
    source = "Text `{{ unfinished\n" + prefix + "` end\n\n?[%{{ real }} A|B]"
    assert collected_names(source) == frozenset({"real"})


@pytest.mark.parametrize(
    "prefix",
    [
        "> `{{` then ",
        "- `{{` then ",
        "> `{{\n> x` then\n\n",
        "> `{{\nplain` then\n\n",
        "- `{{\n  x` then\n\n",
        "> ${{\n> x$ then\n\n",
        "> ${{\nplain$ then\n\n",
    ],
)
def test_same_container_and_lazy_lines_keep_complete_inline_literals(
    prefix: str,
) -> None:
    source = prefix + "?[%{{ real }} A|B]"
    assert collected_names(source) == frozenset({"real"})
    assert _script_questions(source)[-1].variable == "real"
