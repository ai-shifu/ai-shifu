"""Keep native container boundaries separate from authored variable text."""

import json
from pathlib import Path

import pytest
from flaskr.service.learn.agent.engine import collected_names, substitute_variables
from flaskr.service.learn.agent.engine.marker_context import analyze_marker_context
from flaskr.service.learn.agent.engine.tools import _script_questions

QUESTION = "?[%{{ real }} A|B]"
CONTAINERS = [("> ", "> "), ("- ", "  "), ("1. ", "   "), ("> - ", ">   ")]


def _names(source: str) -> frozenset[str]:
    return frozenset(
        marker.name
        for marker in analyze_marker_context(source).markers
        if marker.name is not None
    )


def _assert_real(prefix: str) -> None:
    source = prefix + QUESTION
    assert collected_names(source) == frozenset({"real"})
    assert _script_questions(source)[-1].variable == "real"
    assert (
        substitute_variables(prefix + "{{ real }}", {"real": "VALUE"})
        == prefix + "VALUE"
    )
    for marker in analyze_marker_context(source).markers:
        assert marker.raw_name == source[marker.start + 2 : marker.end - 2]


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("delimiter", ["`", "$"])
@pytest.mark.parametrize(("first", "continued"), CONTAINERS)
def test_container_heading_stops_inline_delimiter_pairing(
    newline: str, delimiter: str, first: str, continued: str
) -> None:
    source = newline.join(
        [
            first + "Text " + delimiter + "{{ unfinished",
            continued + "# Heading " + delimiter + " end",
            "",
            QUESTION,
        ]
    )
    assert _names(source) == frozenset()
    assert _script_questions(source) == []


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize(("first", "continued"), CONTAINERS)
@pytest.mark.parametrize("tag", ["div", "custom"])
@pytest.mark.parametrize("blank", [False, True])
def test_container_html_ends_at_projected_blank_or_dedent(
    newline: str, first: str, continued: str, tag: str, blank: bool
) -> None:
    prefix = newline.join(
        [
            first + "<" + tag + ">",
            continued + "{{ unfinished",
            continued + "</" + tag + ">",
        ]
    )
    _assert_real(prefix + newline * (2 if blank else 1))


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("tag", ["script", "style", "pre", "textarea"])
def test_closed_raw_html_permits_the_following_indented_example(
    newline: str, tag: str
) -> None:
    _assert_real(
        newline.join(["<" + tag + ">", "</" + tag + ">", "    {{ unfinished", "", ""])
    )


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("fence", ["~~~", "```"])
def test_stray_document_control_stops_at_a_native_fence(
    newline: str, fence: str
) -> None:
    _assert_real(newline.join(["?[ unfinished", fence, "{{ x", fence, ""]))
    owned = newline.join(["?[%{{ unfinished", fence, "{{ x", fence, QUESTION])
    assert _names(owned) == frozenset()
    assert all(question.variable != "real" for question in _script_questions(owned))


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize(("first", "continued"), CONTAINERS)
def test_container_reference_starts_only_a_new_native_paragraph(
    newline: str, first: str, continued: str
) -> None:
    _assert_real(first + '[foo]: /url "{{ unfinished"' + newline * 2)
    source = (
        first
        + "Text"
        + newline
        + continued
        + '[foo]: /url "{{ unfinished"'
        + newline * 2
        + QUESTION
    )
    assert _names(source) == frozenset()


@pytest.mark.parametrize(
    "prefix",
    [
        '> [foo]: /url\n>   "{{ unfinished"',
        '> [foo]:\n> /url "{{ unfinished"',
        '- [foo]: /url\n  "{{ unfinished"',
        '> [foo]: /url\n"{{ unfinished"',
        '> [foo]:\n/url "{{ unfinished"',
    ],
)
def test_multiline_and_lazy_container_reference_continuations(prefix: str) -> None:
    _assert_real(prefix + "\n\n")


@pytest.mark.parametrize(
    "prefix",
    ["> <div>\n> %{{ a|b[🙂] }}\n> </div>\n\n", '> [foo]: /url "%{{ a|b[🙂] }}"\n\n'],
)
def test_complete_container_names_keep_original_source_offsets(prefix: str) -> None:
    source = prefix + "{{ other }}"
    assert _names(source) == frozenset({"a|b[🙂]", "other"})
    assert substitute_variables(source, {"other": "VALUE"}) == prefix + "VALUE"
    for marker in analyze_marker_context(source).markers:
        assert marker.raw_name == source[marker.start + 2 : marker.end - 2]


def test_inline_html_does_not_restart_indented_code() -> None:
    source = "Text <script></script>\n    {{ unfinished\n\n" + QUESTION
    assert _names(source) == frozenset()


@pytest.mark.parametrize("count", [1, 4, 2048])
def test_compressed_seed_labels_keep_each_remaining_ancestor(count: int) -> None:
    context = analyze_marker_context("[x]", final=False, label_counts={0: count})
    assert context.pending_label_counts == ([count - 1] if count > 1 else [])
    assert context.pending_labels == ([(False, True)] if count > 1 else [])
    assert context.pending_resource_opener
    assert context.pending_resource_label_start == 0


@pytest.mark.parametrize(
    ("source", "offset", "image"), [("[x](u)", 0, False), ("![x](u)", 1, True)]
)
def test_seed_label_counts_preserve_link_and_image_invalidation(
    source: str, offset: int, image: bool
) -> None:
    context = analyze_marker_context(source, final=False, label_counts={offset: 2048})
    assert context.pending_labels == [(image, image)]
    assert context.pending_label_starts == [offset]
    assert context.pending_label_counts == [2047]


def test_inner_link_invalidates_a_seed_run_without_expanding_it() -> None:
    context = analyze_marker_context("[[x](u)", final=False, label_counts={0: 2048})
    assert context.pending_labels == [(False, False)]
    assert context.pending_label_counts == [2048]


CONTAINER_COLUMN_CASES = [
    (">     {{ unfinished", True),
    ("> >     {{ unfinished", True),
    (">\t  {{ unfinished", True),
    ("> \t  {{ unfinished", True),
    ("-     {{ unfinished", True),
    ("- Intro\n\n      {{ unfinished", True),
    ("2. Intro\n\n       {{ unfinished", True),
    (">     {{ unfinished\n>\n>     still code", True),
    ("- Intro\n\n    ```\n  {{ unfinished\n    ```", True),
    ("2. Intro\n\n    ~~~\n   {{ unfinished\n    ~~~", True),
    ("- Intro\n\n\t  {{ unfinished", True),
    ("> \t~~~\n> {{ unfinished\n> \t~~~", True),
    ("> \t{{ unfinished", False),
    ("> Intro\n>     {{ unfinished", False),
    ("Paragraph\n    {{ unfinished", False),
    ("> - Intro\n>\n> \t  {{ unfinished", False),
]


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize(("prefix", "real"), CONTAINER_COLUMN_CASES)
def test_container_columns_preserve_native_literal_boundaries(
    newline: str, prefix: str, real: bool
) -> None:
    prefix = prefix.replace("\n", newline) + newline * 2
    source = prefix + QUESTION
    assert _names(source) == (frozenset({"real"}) if real else frozenset())
    assert bool(_script_questions(source)) == real
    assert substitute_variables(prefix + "{{ real }}", {"real": "VALUE"}) == (
        prefix + "VALUE" if real else prefix + "{{ real }}"
    )


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize(
    ("opening", "closing"),
    [
        ("<script>", "</script>"),
        ("<style>", "</style>"),
        ("<pre>", "</pre>"),
        ("<textarea>", "</textarea>"),
        ("<!--", "-->"),
        ("<?x", "?>"),
        ("<![CDATA[", "]]>"),
        ("<!DOCTYPE", ">"),
    ],
)
@pytest.mark.parametrize(("first", "continued"), [*CONTAINERS, ("> \t", "> ")])
def test_every_existing_html_block_uses_container_column_positions(
    newline: str, opening: str, closing: str, first: str, continued: str
) -> None:
    _assert_real(
        newline.join(
            [first + opening, continued + "{{ unfinished", continued + closing, "", ""]
        )
    )


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("tag", ["script", "style", "pre", "textarea"])
@pytest.mark.parametrize(("first", "continued"), [("", ""), *CONTAINERS])
def test_raw_html_prefix_admits_blocks_without_a_complete_opening_tag(
    newline: str, tag: str, first: str, continued: str
) -> None:
    _assert_real(
        newline.join(
            [
                first + "<" + tag,
                continued.rstrip(),
                continued + "{{ unfinished",
                continued + "</" + tag + ">",
                "",
                "",
            ]
        )
    )


@pytest.mark.parametrize("suffix", [">", "> "])
def test_partial_nested_container_retains_pending_raw_html(suffix: str) -> None:
    context = analyze_marker_context("> - <script>x\n" + suffix, final=False)
    assert context.pending_raw_html_tag == "script"
    assert context.pending_block_steps == (0, 2)


def test_partial_quote_prefix_is_not_an_html_declaration_terminator() -> None:
    context = analyze_marker_context("> <!DOCTYPE\n>", final=False)
    assert context.pending_html_start == 2
    assert context.pending_block_steps == (0,)
    assert context.literals == []


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("opening", ["<!--", "<?x", "<![CDATA[", "<!DOCTYPE"])
@pytest.mark.parametrize(("first", "continued"), CONTAINERS)
def test_unterminated_container_html_ends_at_confirmed_parent_dedent(
    newline: str, opening: str, first: str, continued: str
) -> None:
    _assert_real(
        newline.join(
            [
                first + opening,
                continued + "{{ unfinished",
                continued + "{{ still unfinished",
                "",
                "",
            ]
        )
    )


AUTOLINK_EXAMPLES = [
    "<foo:{{unfinished\x00>",
    "<foo:{{unfinished\ufffd>",
    "<foo:{{unfinished>",
    "<https://example.com/{{unfinished>",
    "<aa:{{unfinished>",
    "<" + "a" * 32 + ":{{unfinished>",
    "<foo:中文/{{unfinished>",
    "<{{unfinished@example.com>",
    "<{{unfinished@b>",
    "<{{unfinished@" + "a" * 63 + ".com>",
]
INVALID_AUTOLINK_EXAMPLES = [
    "<a:{{unfinished>",
    "<" + "a" * 33 + ":{{unfinished>",
    "<1foo:{{unfinished>",
    "<foo:{{unfinished space>",
    "<foo:{{unfinished\x7f>",
    "<foo:{{unfinished\x01>",
    "<foo:{{unfinished\n>",
    "<foo:{{unfinished",
    "<{{unfinished@-example.com>",
    "<{{unfinished@example-.com>",
    "<{{unfinished@" + "a" * 64 + ".com>",
    "<{{unfinished@@example.com>",
    "<{{unfinished@example..com>",
]
COMPLETE_AUTOLINK_KEYS = [
    ("<foo:%{{a|b[🙂]}}>", "a|b[🙂]"),
    (r"<foo:{{path\key}}>", r"path\key"),
    ("<{{question?}}@example.com>", "question?"),
    ("<foo:{{x<y}}>", "x<y"),
]


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("example", AUTOLINK_EXAMPLES)
def test_complete_angle_autolinks_bound_unfinished_variable_examples(
    newline: str, example: str
) -> None:
    _assert_real(example + newline * 2)


@pytest.mark.parametrize("example", INVALID_AUTOLINK_EXAMPLES)
def test_invalid_angle_links_do_not_claim_literal_scope(example: str) -> None:
    source = example + "\n\n" + QUESTION
    assert _names(source) == frozenset()
    assert _script_questions(source) == []


@pytest.mark.parametrize(("example", "key"), COMPLETE_AUTOLINK_KEYS)
def test_angle_link_declarations_keep_exact_keys(example: str, key: str) -> None:
    source = example + "\n\n" + QUESTION
    assert _names(source) == frozenset({key, "real"})
    assert collected_names(source) == (
        frozenset({key, "real"}) if "%{{" in example else frozenset({"real"})
    )
    assert substitute_variables(source, {key: "VALUE"}) == (
        source if "%{{" in example else source.replace("{{" + key + "}}", "VALUE")
    )
    for marker in analyze_marker_context(source).markers:
        assert marker.raw_name == source[marker.start + 2 : marker.end - 2]


def test_true_marker_names_own_angle_link_syntax() -> None:
    source = "{{ key<foo:?[Go]> }}\n\n" + QUESTION
    assert _names(source) == frozenset({"key<foo:?[Go]>", "real"})
    assert [question.variable for question in _script_questions(source)] == ["real"]


AUTOLINK_CORPUS = json.loads(
    (Path(__file__).parent / "fixtures" / "autolink-cases.json").read_text()
)


@pytest.mark.parametrize("case", AUTOLINK_CORPUS, ids=lambda case: case["id"])
def test_shared_native_angle_autolink_corpus(case: dict[str, object]) -> None:
    source = str(case["source"])
    assert sorted(_names(source)) == case["names"]
    assert sorted(collected_names(source)) == case["variables"]
    assert bool(_script_questions(source)) == ("real" in case["names"])
