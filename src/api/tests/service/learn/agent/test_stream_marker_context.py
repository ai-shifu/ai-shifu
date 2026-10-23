"""Keep document marker boundaries stable across arbitrary narration chunks."""

import pytest
from flaskr.service.learn.agent import interaction_syntax
from flaskr.service.learn.agent.engine import stream_marker_context
from flaskr.service.learn.agent.engine.marker_context import MarkerContext
from flaskr.service.learn.agent.interaction_syntax import InteractionSyntaxFilter

QUESTION = "?[%{{ real }} A|B]"


@pytest.mark.parametrize(
    "prefix",
    [
        "$x {{ y$\n\n",
        "$$x {{ y$$\n\n",
        r"\$$x {{ y$" + "\n\n",
        '[x](url "{{")\n\n',
        "[x](url '{{')\n\n",
        "[x](url ({{))\n\n",
        '[x](u(n) "{{")\n\n',
        '[x](<url> "{{")\n\n',
        '![x](url "{{")\n\n',
        '[x](url\n "{{")\n\n',
        '![outer [inner](u)](u "{{")\n\n',
        '$[x](u "{{")$\n\n',
        '[x]($u$ "{{")\n\n',
        "    {{ unfinished\n\n",
        "\t{{ unfinished\n\n",
        " \t{{ unfinished\n\n",
        "Text\n\n    {{ unfinished\n\n",
        *[
            f"<{tag}>\n{{{{ unfinished\n</{tag.upper()}>\n"
            for tag in ("script", "style", "pre", "textarea")
        ],
        *[
            f'<{tag} title="x">\n{{{{ unfinished\n</{tag}> {{{{ still literal\n'
            for tag in ("script", "style", "pre", "textarea")
        ],
        'Show <span title="{{">\n',
        'Show <span title="long\n\n{{">\n',
        "Show <!-- {{ -->\n",
        "Show <? {{ ?>\n",
        "Show <![CDATA[ {{ ]]>\n",
        "Show <!DECL {{ >\n",
        'i<n, {{ <span title="x }}\n',
    ],
)
def test_literal_marker_boundaries_survive_all_stream_cuts(prefix: str) -> None:
    source = prefix + QUESTION
    chunks = [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]
    for stream in chunks:
        syntax = InteractionSyntaxFilter()
        shown = "".join(syntax.feed(chunk) for chunk in stream) + syntax.flush()
        assert shown == prefix, stream
        assert syntax.spans == [QUESTION], stream


@pytest.mark.parametrize("delimiter", ["`", "$"])
@pytest.mark.parametrize("prefix", ["# Heading ", "#Heading ", "Text # ordinary "])
def test_heading_boundaries_use_the_original_physical_line(
    delimiter: str, prefix: str
) -> None:
    source = prefix + delimiter + "{{\nq" + delimiter + " then " + QUESTION
    syntax = InteractionSyntaxFilter()
    expected = syntax.feed(source) + syntax.flush(), syntax.spans
    for cut in range(len(source) + 1):
        syntax = InteractionSyntaxFilter()
        shown = syntax.feed(source[:cut]) + syntax.feed(source[cut:]) + syntax.flush()
        assert (shown, syntax.spans) == expected, cut


def test_completed_nested_link_keeps_an_outer_link_inactive_across_chunks() -> None:
    source = '[outer [inner](u)](u "{{")\n\n' + QUESTION
    for stream in [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]:
        syntax = InteractionSyntaxFilter()
        shown = "".join(syntax.feed(chunk) for chunk in stream) + syntax.flush()
        assert shown == source
        assert syntax.spans == []


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize(
    "lines",
    [
        ["> ```", "> {{ unfinished", "> ```", "", ""],
        ["- ```", "  {{ unfinished", "  ```", "", ""],
        ["1. ~~~", "   {{ unfinished", "   ~~~", "", ""],
        ["> - ```", ">   {{ unfinished", ">   ```", "", ""],
        ["<div>", "{{ unfinished", "</div>", "", ""],
        ["<custom>", "{{ unfinished", "</custom>", "", ""],
        ["<section>", "{{ unfinished", "", ""],
        ["```", "{{ unfinished", "```", ""],
        ["<script>", "{{ unfinished", "</script> {{ still literal", ""],
        ["    {{ unfinished", "", ""],
        ["# Heading", "    {{ unfinished", "", ""],
        ["---", "    {{ unfinished", "", ""],
        ["Title", "===", "    {{ unfinished", "", ""],
        ["```", "code", "```", "    {{ unfinished", "", ""],
        ["> ```", "> code", "> ```", "    {{ unfinished", "", ""],
        ['[foo]: /url "{{ unfinished"', "", ""],
        ["[foo]: /url", '  "{{ unfinished"', "", ""],
        ["[foo]: <url>", "  '{{ unfinished'", "", ""],
    ],
)
def test_literal_blocks_and_all_physical_endings_keep_the_external_question(
    lines: list[str], newline: str
) -> None:
    prefix = newline.join(lines)
    source = prefix + QUESTION
    for stream in [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]:
        syntax = InteractionSyntaxFilter()
        shown = "".join(syntax.feed(chunk) for chunk in stream) + syntax.flush()
        assert shown == prefix, stream
        assert syntax.spans == [QUESTION], stream


@pytest.mark.parametrize(
    "prefix",
    [
        "> ```\n> example\n> ```\n> {{ never closed\n\n",
        "- ```\n  example\n  ```\n{{ never closed\n\n",
        "<div>example</div>\n\n{{ never closed\n\n",
        '[foo]: /url "{{ unfinished\n\n',
        '[foo]: /url "{{ unfinished" invalid\n\n',
    ],
)
def test_closed_blocks_do_not_reopen_and_hide_a_real_outer_marker(prefix: str) -> None:
    source = prefix + QUESTION
    for stream in [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]:
        syntax = InteractionSyntaxFilter()
        shown = "".join(syntax.feed(chunk) for chunk in stream) + syntax.flush()
        assert shown == source
        assert syntax.spans == []


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_stray_interaction_stops_at_a_confirmed_blank_outside_markers(
    newline: str,
) -> None:
    prefix = newline.join(["?[ unfinished", "", "`{{`", "", ""])
    source = prefix + QUESTION
    for stream in [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]:
        syntax = InteractionSyntaxFilter()
        shown = "".join(syntax.feed(chunk) for chunk in stream) + syntax.flush()
        assert shown == prefix
        assert syntax.spans == [QUESTION]


@pytest.mark.parametrize(
    "text",
    [
        "if a<b, ordinary narration " * 100,
        "i<n 时，继续讲解 " * 100,
        '<span title="' + "x" * 3000 + '">',
        '<span title="' + "x" * 1500 + "\n\n" + "x" * 1500 + '">',
        "<!--" + "x" * 3000 + "-->",
        "<?" + "x" * 3000 + "?>",
        "<![CDATA[" + "x" * 3000 + "]]>",
        '[x](url "' + "x" * 3000 + '")',
        "<script>" + "x" * 3000 + "</script>\n",
        "<div>" + "x" * 3000 + "\n\n",
        "- ```\n  " + "x" * 3000 + "\n  ```\n\n",
        "> - ```\n>   " + "x" * 3000 + "\n>   ```\n\n",
        '[foo]: /url "' + "x" * 3000 + '"\n\n',
    ],
)
def test_retained_context_and_parser_work_do_not_grow_with_narration_content(
    text: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    inspected = 0
    original = stream_marker_context.analyze_marker_context

    def counted(source: str, **kwargs: object) -> MarkerContext:
        nonlocal inspected
        inspected += len(source)
        return original(source, **kwargs)

    monkeypatch.setattr(stream_marker_context, "analyze_marker_context", counted)
    monkeypatch.setattr(interaction_syntax, "analyze_marker_context", counted)
    syntax = InteractionSyntaxFilter()
    pieces = []
    for character in text:
        pieces.append(syntax.feed(character))
        assert len(syntax._context_prefix) <= 128
        assert len(syntax._line_so_far) <= 4
    assert "".join(pieces) + syntax.flush() == text
    assert syntax.spans == []
    assert inspected <= 400 * len(text)


@pytest.mark.parametrize("text", ["if a<b,", "i<n 时", "<x a=b=c", '<x a="x"oops'])
def test_impossible_html_prefixes_are_discarded(text: str) -> None:
    assert "<" not in stream_marker_context.compact_marker_context(text)


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
def test_new_container_paragraph_does_not_close_an_earlier_stream_literal(
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
        + QUESTION
    )
    for stream in [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]:
        syntax = InteractionSyntaxFilter()
        shown = "".join(syntax.feed(chunk) for chunk in stream) + syntax.flush()
        assert shown == source, stream
        assert syntax.spans == [], stream


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
        "Text `{{ unfinished\n2. ` end\n\n",
        "Text `{{ unfinished\nx > ` end\n\n",
    ],
)
def test_complete_same_container_stream_literals_keep_the_external_question(
    prefix: str,
) -> None:
    source = prefix + QUESTION
    for stream in [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]:
        syntax = InteractionSyntaxFilter()
        shown = "".join(syntax.feed(chunk) for chunk in stream) + syntax.flush()
        assert shown == prefix, stream
        assert syntax.spans == [QUESTION], stream


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("delimiter", ["`", "$"])
@pytest.mark.parametrize("underline", ["=", "===", "-", "--"])
def test_setext_heading_stops_stream_inline_delimiter_pairing(
    newline: str, delimiter: str, underline: str
) -> None:
    source = newline.join(
        [
            "Text " + delimiter + "{{ unfinished",
            underline,
            delimiter + " end",
            "",
            QUESTION,
        ]
    )
    for stream in [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]:
        syntax = InteractionSyntaxFilter()
        shown = "".join(syntax.feed(chunk) for chunk in stream) + syntax.flush()
        assert shown == source, stream
        assert syntax.spans == [], stream


@pytest.mark.parametrize("delimiter", ["`", "$"])
@pytest.mark.parametrize(
    "line", ["=", "===", "-", "--", "== ordinary text", "=-", "    ==="]
)
def test_setext_and_ordinary_lines_keep_already_closed_stream_literals(
    delimiter: str, line: str
) -> None:
    prefix = "Text " + delimiter + "{{ example }}" + delimiter + "\n" + line + "\n\n"
    source = prefix + QUESTION
    for stream in [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]:
        syntax = InteractionSyntaxFilter()
        shown = "".join(syntax.feed(chunk) for chunk in stream) + syntax.flush()
        assert shown == prefix, stream
        assert syntax.spans == [QUESTION], stream
