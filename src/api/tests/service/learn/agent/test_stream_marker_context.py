"""Keep document marker boundaries stable across arbitrary narration chunks."""

import json
from pathlib import Path

import pytest
from flaskr.service.learn.agent import interaction_syntax
from flaskr.service.learn.agent.engine import stream_marker_context
from flaskr.service.learn.agent.engine.marker_context import MarkerContext
from flaskr.service.learn.agent.interaction_syntax import InteractionSyntaxFilter

QUESTION = "?[%{{ real }} A|B]"
AUTOLINK_CASES = json.loads(
    (Path(__file__).parent / "engine" / "fixtures" / "autolink-cases.json").read_text()
)


@pytest.mark.parametrize("case", AUTOLINK_CASES, ids=lambda case: case["id"])
def test_shared_angle_link_corpus_keeps_stream_boundary_agreement(
    case: dict[str, object],
) -> None:
    source = str(case["source"])
    expected = None
    for stream in [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]:
        syntax = InteractionSyntaxFilter()
        shown = "".join(syntax.feed(chunk) for chunk in stream) + syntax.flush()
        actual = (shown, syntax.spans)
        if expected is None:
            expected = actual
        assert actual == expected, stream
        assert syntax.spans.count(QUESTION) == (1 if case["variables"] else 0), stream


@pytest.mark.parametrize(
    ("prefix", "real"),
    [
        ("<https://{{unfinished>\n\n", True),
        ("<ab:{{unfinished>\n\n", True),
        ("<" + "a" * 32 + ":{{unfinished>\n\n", True),
        ("<a:{{unfinished>\n\n", False),
        ("<" + "a" * 33 + ":{{unfinished>\n\n", False),
        ("<https://{{unfinished value>\n\n", False),
        ("<https://{{unfinished\nvalue>\n\n", False),
        ("<https://{{unfinished\x7f>\n\n", False),
        ("<{{unfinished@example.com>\n\n", True),
        ("<{{unfinished@" + "a" * 63 + ".com>\n\n", True),
        ("<{{unfinished@" + "a" * 64 + ".com>\n\n", False),
        ("<{{unfinished@example-.com>\n\n", False),
        ("Text <!{{unfinished@example.com>\n\n", True),
        ("Text <?{{unfinished@example.com>\n\n", True),
        ("Text </{{unfinished@example.com>\n\n", True),
        ("<https://\\{{unfinished value>\n\n", True),
        ("{{unfinished <https://example.com>\n\n", False),
        ("<scripture>\n{{unfinished\n</scripture>\n\n", True),
        ("<script attr>\n{{unfinished\n</script>\n\n", True),
    ],
)
def test_angle_link_boundaries_and_invalid_fallback_survive_every_stream_cut(
    prefix: str, real: bool
) -> None:
    source = prefix + QUESTION
    for stream in [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]:
        syntax = InteractionSyntaxFilter()
        shown = "".join(syntax.feed(chunk) for chunk in stream) + syntax.flush()
        assert shown == (prefix if real else source), stream
        assert syntax.spans == ([QUESTION] if real else []), stream


@pytest.mark.parametrize(
    "prefix",
    [
        "<https://{{" + "x" * 3000 + ">\n\n",
        "<{{" + "x" * 3000 + "@example.com>\n\n",
        "<{{x@" + "example." * 400 + "com>\n\n",
        "<https://" + "[" * 1000 + "x" + "]" * 1000 + ">\n\n",
    ],
)
def test_angle_link_continuations_keep_bounded_state_and_parser_work(
    prefix: str, monkeypatch: pytest.MonkeyPatch
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
    for character in prefix + QUESTION:
        pieces.append(syntax.feed(character))
        assert len(syntax._context_prefix) <= 128
        assert len(syntax._held) <= 128
    pieces.append(syntax.flush())
    assert "".join(pieces) == prefix
    assert syntax.spans == [QUESTION]
    assert inspected <= 400 * (len(prefix) + len(QUESTION))


def test_invalid_angle_link_releases_an_earlier_raw_marker_only_at_its_closer() -> None:
    source = "<https://{{unfinished value>\n\n" + QUESTION + " then " + QUESTION
    for stream in [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]:
        syntax = InteractionSyntaxFilter()
        shown = "".join(syntax.feed(chunk) for chunk in stream) + syntax.flush()
        assert shown == source[: -len(QUESTION)], stream
        assert syntax.spans == [QUESTION], stream


def test_angle_link_fallback_keeps_counted_label_and_resource_state() -> None:
    prefix = "<https://" + "[" * 24 + "x" + "]" * 24 + '(u "{{")\n\n'
    source = prefix + QUESTION
    for stream in [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]:
        syntax = InteractionSyntaxFilter()
        shown = "".join(syntax.feed(chunk) for chunk in stream) + syntax.flush()
        assert shown == prefix, stream
        assert syntax.spans == [QUESTION], stream


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize(
    ("prefix", "real"),
    [
        *[
            (f"> Text {run}{{{{ unfinished\n> # Heading {run} end\n\n", False)
            for run in ("`", "$")
        ],
        *[
            (f"2. Text {run}{{{{ unfinished\n    # Heading {run} end\n\n", False)
            for run in ("`", "$")
        ],
        *[
            (f"Text {run}{{{{ unfinished\n2. # Heading\n{run} end\n\n", True)
            for run in ("`", "$")
        ],
        ("> <div>\n> {{ unfinished\n> </div>\n\n", True),
        ("- <div>\n  {{ unfinished\n  </div>\n\n", True),
        ("<script>\n</script>\n    {{ unfinished\n\n", True),
        ("?[ unfinished\n~~~\n{{ x\n~~~\n", True),
        ('> [foo]: /url "{{ unfinished"\n\n', True),
        ('> [foo]: /url\n>   "{{ unfinished"\n\n', True),
        ('> [foo]:\n> /url "{{ unfinished"\n\n', True),
        ('> [foo]: /url\n"{{ unfinished"\n\n', True),
        ('> [foo]:\n/url "{{ unfinished"\n\n', True),
        ('- [foo]: /url\n  "{{ unfinished"\n\n', True),
        ('> Intro\n> [foo]: /url "{{ unfinished"\n\n', False),
        ("{{ unfinished\n> <div>\n> {{ other\n> </div>\n\n", False),
    ],
)
def test_container_document_context_survives_every_stream_cut(
    newline: str, prefix: str, real: bool
) -> None:
    prefix = prefix.replace("\n", newline)
    source = prefix + QUESTION
    for stream in [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]:
        syntax = InteractionSyntaxFilter()
        shown = "".join(syntax.feed(chunk) for chunk in stream) + syntax.flush()
        assert syntax.spans == ([QUESTION] if real else []), stream
        assert shown == (prefix if real else source), stream


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
        "[" * 1000,
        "[ordinary " * 300,
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


@pytest.mark.parametrize("inner", [False, True])
def test_counted_labels_keep_real_long_link_titles_and_outer_invalidation(
    inner: bool,
) -> None:
    depth = 24
    prefix = "[" * depth + "label"
    if inner:
        prefix += '](url "{{")' + "]" * (depth - 1)
    else:
        prefix += "]" * depth + '(url "{{")'
    prefix += "\n\n"
    source = prefix + QUESTION
    for stream in [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]:
        syntax = InteractionSyntaxFilter()
        shown = "".join(syntax.feed(chunk) for chunk in stream) + syntax.flush()
        assert shown == prefix, stream
        assert syntax.spans == [QUESTION], stream


def test_batch_inactive_label_runs_keep_bounded_state_and_real_closing_semantics(
    monkeypatch: pytest.MonkeyPatch,
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
    seed = "[" * 1000 + "[x](u)"
    pieces = [syntax.feed(seed)]
    for character in "ordinary text " * 100 + "]" * 1000 + '(url "{{")\n\n' + QUESTION:
        pieces.append(syntax.feed(character))
        assert len(syntax._context_prefix) <= 128
        assert len(syntax._context_label_counts) <= 1
    pieces.append(syntax.flush())
    source = seed + "ordinary text " * 100 + "]" * 1000 + '(url "{{")\n\n' + QUESTION
    assert "".join(pieces) == source
    assert syntax.spans == []  # A completed inner link disables the outer resource.
    assert inspected <= 400 * len(source)


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize(
    ("opening", "continuation"),
    [
        ("> ", "> "),
        ("- ", "  "),
        ("> - ", ">   "),
        ("12345. ", " " * 7),
        ("123456789. ", " " * 11),
    ],
)
@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("<script>", "</script>"),
        ("<style>", "</style>"),
        ("<pre>", "</pre>"),
        ("<textarea>", "</textarea>"),
        ("<!--", "-->"),
        ("<?x", "?>"),
        ("<![CDATA[", "]]>"),
        ("<!DOCTYPE", ">"),
        ("<div>", "</div>"),
        ("~~~", "~~~"),
    ],
)
def test_container_literal_witnesses_keep_actual_marker_width_and_columns(
    newline: str, opening: str, continuation: str, start: str, end: str
) -> None:
    prefix = newline.join(
        [opening + start, continuation + "{{ unfinished", continuation + end, "", ""]
    )
    source = prefix + QUESTION
    for stream in [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]:
        syntax = InteractionSyntaxFilter()
        shown = "".join(syntax.feed(chunk) for chunk in stream) + syntax.flush()
        assert shown == prefix, stream
        assert syntax.spans == [QUESTION], stream


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize(
    "prefix",
    [
        ">     {{ unfinished\n\n",
        "-     {{ unfinished\n\n",
        "> -     {{ unfinished\n\n",
        "12345.     {{ unfinished\n\n",
        "123456789.     {{ unfinished\n\n",
        "- Intro\n\n\t  {{ unfinished\n\n",
        "> - Intro\n>\n> \t    {{ unfinished\n\n",
    ],
)
def test_container_indented_code_witnesses_keep_the_external_question(
    newline: str, prefix: str
) -> None:
    prefix = prefix.replace("\n", newline)
    source = prefix + QUESTION
    for stream in [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]:
        syntax = InteractionSyntaxFilter()
        shown = "".join(syntax.feed(chunk) for chunk in stream) + syntax.flush()
        assert shown == prefix, stream
        assert syntax.spans == [QUESTION], stream


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("token", ["<!--", "<?x", "<![CDATA[", "<!DOCTYPE"])
@pytest.mark.parametrize(
    ("opening", "continuation"), [("> ", "> "), ("- ", "  "), ("> - ", ">   ")]
)
def test_unclosed_container_html_stops_at_a_confirmed_dedent(
    newline: str, token: str, opening: str, continuation: str
) -> None:
    prefix = newline.join(
        [opening + token, continuation + "{{ unfinished", "Outside", "", ""]
    )
    source = prefix + QUESTION
    for stream in [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]:
        syntax = InteractionSyntaxFilter()
        shown = "".join(syntax.feed(chunk) for chunk in stream) + syntax.flush()
        assert shown == prefix, stream
        assert syntax.spans == [QUESTION], stream


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


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize(
    ("opening", "closing"),
    [("<!--", "-->"), ("<?x", "?>"), ("<![CDATA[", "]]>"), ("<!DOCTYPE", ">")],
)
def test_complete_html_blocks_keep_closing_line_examples_local_across_stream_cuts(
    newline: str, opening: str, closing: str
) -> None:
    prefix = newline.join([opening, "{{ unfinished", closing + " {{ still literal", ""])
    source = prefix + QUESTION
    for stream in [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]:
        syntax = InteractionSyntaxFilter()
        shown = "".join(syntax.feed(chunk) for chunk in stream) + syntax.flush()
        assert shown == prefix, stream
        assert syntax.spans == [QUESTION], stream


@pytest.mark.parametrize(
    ("opening", "closing"),
    [("<!--", "-->"), ("<?x", "?>"), ("<![CDATA[", "]]>"), ("<!DOCTYPE", ">")],
)
def test_html_closing_line_witness_does_not_retain_body_text(
    opening: str, closing: str
) -> None:
    prefix = (
        opening + "\n" + "x" * 1000 + "\n" + closing + " {{ still literal" + "x" * 1000
    )
    syntax = InteractionSyntaxFilter()
    shown = []
    for character in prefix:
        shown.append(syntax.feed(character))
        assert len(syntax._context_prefix) < 128
    shown.append(syntax.feed("\n" + QUESTION))
    shown.append(syntax.flush())
    assert "".join(shown) == prefix + "\n"
    assert syntax.spans == [QUESTION]
