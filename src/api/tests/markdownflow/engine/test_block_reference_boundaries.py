"""Native block precedence keeps image references outside interaction parsing."""

import re
from types import SimpleNamespace

import pytest
from markdown_it import MarkdownIt
from markdownflow.engine import collected_names, document_blocks
from markdownflow.engine.marker_context import analyze_marker_context
from markdownflow.engine.tools import script_options


@pytest.mark.parametrize("marker", ["*", "-", "_"])
@pytest.mark.parametrize("padding", [" ", "\t"])
@pytest.mark.parametrize(
    ("container", "continuation"),
    [
        ("", ""),
        ("> ", "> "),
        ("- ", "  "),
        ("1. ", "   "),
        ("> - ", ">   "),
        ("- > ", "  > "),
    ],
)
def test_thematic_breaks_keep_following_image_references_inactive(
    marker: str, padding: str, container: str, continuation: str
) -> None:
    """Real image alt text stays outside interaction parsing after a thematic rule."""
    thematic = padding.join([marker] * 3)
    source = (
        "![?[{{goal}} A | B]][image]\n\n"
        f"{container}{thematic}\n{continuation}[image]: /x"
    )
    assert "<hr" in MarkdownIt().render(source)
    assert "<img " in MarkdownIt().render(source)
    assert collected_names(source) == frozenset()
    assert script_options(source) == {}


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize(
    "prefix",
    ["* * *", "- - -", "_ _ _", "* * * text", "- - - text", "* - *", "- * -"],
)
def test_thematic_reference_admission_matches_native_rendering(
    prefix: str, newline: str
) -> None:
    """Only genuine rules end the paragraph before the following definition."""
    source = ("![?[{{goal}} A | B]][image]\n\n" + prefix + "\n[image]: /x").replace(
        "\n", newline
    )
    image = "<img " in MarkdownIt().render(source)
    assert collected_names(source) == (frozenset() if image else frozenset({"goal"}))
    assert script_options(source) == ({} if image else {"A": "A", "B": "B"})


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("thematic", ["* * *", "- - -", "_ _ _"])
@pytest.mark.parametrize("inside_list", [False, True])
def test_thematic_rules_keep_only_their_actual_list_container(
    newline: str, thematic: str, inside_list: bool
) -> None:
    """A rule closes a lazy list paragraph without inventing or retaining an item."""
    source = (
        "![?[{{goal}} A | B]][image]\n\n- text\n"
        + ("  " if inside_list else "")
        + thematic
        + "\n    [image]: /x"
    ).replace("\n", newline)
    image = "<img " in MarkdownIt().render(source)
    assert image is inside_list
    assert collected_names(source) == (frozenset() if image else frozenset({"goal"}))
    assert script_options(source) == ({} if image else {"A": "A", "B": "B"})


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("thematic", ["* * *", "- - -", "_ _ _"])
@pytest.mark.parametrize("padding", ["  ", "    "])
def test_thematic_quote_exit_preserves_its_outer_list(
    newline: str, thematic: str, padding: str
) -> None:
    """A definition after a quoted rule can remain in the surrounding list item."""
    source = (
        f"![?[{{{{goal}}}} A | B]][image]\n\n- > {thematic}\n{padding}[image]: /x"
    ).replace("\n", newline)
    assert "<img " in MarkdownIt().render(source)
    assert collected_names(source) == frozenset()
    assert script_options(source) == {}


@pytest.mark.parametrize("depth", [256, 1024, 4096])
def test_thematic_precedence_does_not_rescan_each_nested_list_tail(
    monkeypatch: pytest.MonkeyPatch, depth: int
) -> None:
    """Long non-thematic lists must retain a bounded amount of suffix matching."""
    work = 0
    original = document_blocks.COMPILED_DOCUMENT_BREAK_REGEX

    def counted(value: str) -> re.Match[str] | None:
        nonlocal work
        work += len(value)
        return original.fullmatch(value)

    monkeypatch.setattr(
        document_blocks,
        "COMPILED_DOCUMENT_BREAK_REGEX",
        SimpleNamespace(fullmatch=counted),
    )
    source = "- " * depth + "paragraph"
    content, steps, _ = document_blocks.container_opening_info(source)
    assert source[content:] == "paragraph"
    assert steps == (2,) * depth
    assert work <= 4 * len(source)


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize(
    ("opening", "continuation"),
    [("", ""), ("> ", "> "), ("- ", "  "), ("> - ", ">   ")],
)
@pytest.mark.parametrize(
    ("body", "expected_image"),
    [
        ("<!-- x -->", True),
        ("<!-- x\n2. raw\n-->", True),
        ("<!-->", True),
        ("<!--->", True),
        ("<?instruction?>", True),
        ("<?instruction\n?>", True),
        ("<![CDATA[x]]>", True),
        ("<![CDATA[\n]]>", True),
        ("<!DOCTYPE x>", True),
        ("<script>x</script>", True),
        ("<style>\n2. raw\n</style>", True),
        ("<pre>\nraw\n</pre>", True),
        ("<textarea>\nraw\n</textarea>", True),
        ("    code", True),
        ("    code\n    more", True),
        ("\tcode", True),
        ("Heading\n===", True),
        ("Heading\n---", True),
        ("```\n2. code\n```", True),
        ("~~~\n2. code\n~~~", True),
        ("paragraph\n    continuation", False),
        ("paragraph\n\tcontinuation", False),
        ("paragraph\n<span>", False),
        ("paragraph\n</script>", False),
        ("<div>\nraw\n</div>", False),
        ("<span>\nraw\n</span>", False),
        ("<!-- incomplete", False),
        ("<script>incomplete", False),
        ("```\nincomplete", False),
        ("Heading\n2. continuation", False),
    ],
)
def test_fresh_ordered_items_follow_confirmed_nonparagraph_blocks(
    body: str,
    expected_image: bool,
    opening: str,
    continuation: str,
    newline: str,
) -> None:
    """Block closures admit fresh list items without interrupting ordinary paragraphs."""
    lines = body.split("\n")
    prefix = opening + lines[0] + "\n"
    prefix += "".join(continuation + line + "\n" for line in lines[1:])
    source = (
        "![?[{{goal}} A | B]][image]\n\n" + prefix + continuation + "2. [image]: /x"
    ).replace("\n", newline)
    image = "<img " in MarkdownIt().render(source)
    if not opening:
        assert image is expected_image
    assert collected_names(source) == (frozenset() if image else frozenset({"goal"}))
    assert script_options(source) == ({} if image else {"A": "A", "B": "B"})


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize(
    "opener", ["<!-- x", "<?instruction", "<![CDATA[x", "<!DOCTYPE x"]
)
@pytest.mark.parametrize("marker", ["1. ", "2. ", "- "])
@pytest.mark.parametrize(
    ("opening", "continuation"),
    [("", ""), ("> ", "> "), ("- ", "  "), ("> - ", ">   ")],
)
def test_open_html_cannot_supply_image_definitions_but_keeps_control_fallback(
    opener: str, marker: str, opening: str, continuation: str, newline: str
) -> None:
    """Image admission is stricter than the established unfinished-HTML fallback."""
    source = (
        "![?[{{goal}} A | B]][image]\n\n"
        f"{opening}{opener}\n{continuation}{marker}[image]: /x\n"
        f"{continuation}?[{{{{visible}}}} C | D]"
    ).replace("\n", newline)
    assert "<img " not in MarkdownIt().render(source)
    assert collected_names(source) == frozenset({"goal", "visible"})
    assert script_options(source) == {"A": "A", "B": "B", "C": "C", "D": "D"}


@pytest.mark.parametrize(
    "prefix",
    [
        "[image]: /x\n\n<!-- unfinished\n1. [other]: /other",
        "```\n<!-- unfinished\n```\n2. [image]: /x",
        "<pre>\n<!-- unfinished\n</pre>\n2. [image]: /x",
        "> <!-- unfinished\n2. [image]: /x",
    ],
)
def test_html_admission_guard_stays_inside_its_actual_block(prefix: str) -> None:
    """Earlier definitions and HTML examples remain outside an unfinished block."""
    source = "![?[{{goal}} A | B]][image]\n\n" + prefix
    assert "<img " in MarkdownIt().render(source)
    assert collected_names(source) == frozenset()
    assert script_options(source) == {}


def test_open_html_keeps_the_existing_generic_reference_literal_fallback() -> None:
    source = "<!-- unfinished\n1. [image]: /x"
    context = analyze_marker_context(source)
    assert any(source[start:end] == "1. [image]: /x" for start, end in context.literals)


@pytest.mark.parametrize(
    "opener", ["<!-- x", "<?instruction", "<![CDATA[x", "<!DOCTYPE x"]
)
@pytest.mark.parametrize(
    "content",
    [
        "![?[{{goal}} A | B]](/x)",
        "![?[{{goal}} A | B]][image]",
        "?[{{goal}} A | B]",
    ],
)
@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_open_html_image_syntax_keeps_the_existing_control_fallback(
    opener: str, content: str, newline: str
) -> None:
    """Source inside unfinished HTML does not acquire a rendered-image boundary."""
    source = ("[image]: /x\n\n" + opener + "\n" + content).replace("\n", newline)
    assert "<img " not in MarkdownIt().render(source)
    assert collected_names(source) == frozenset({"goal"})
    assert script_options(source) == {"A": "A", "B": "B"}


@pytest.mark.parametrize("opener", ["<!doctype x", "<!z x", "<![cdata[x", "< !-- x"])
def test_only_native_html_openers_limit_image_admission(opener: str) -> None:
    source = "![?[{{goal}} A | B]][image]\n\n" + opener + "\n1. [image]: /x"
    assert "<img " in MarkdownIt().render(source)
    assert collected_names(source) == frozenset()
    assert script_options(source) == {}


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize(
    "prefix",
    ["- text\n# Heading", "- text\nHeading\n===", "> text\n# Heading"],
)
def test_heading_closures_do_not_retain_lazy_list_indentation(
    prefix: str, newline: str
) -> None:
    """A heading outside an item cannot turn following root code into a definition."""
    source = ("![?[{{goal}} A | B]][image]\n\n" + prefix + "\n    [image]: /x").replace(
        "\n", newline
    )
    assert "<img " not in MarkdownIt().render(source)
    assert collected_names(source) == frozenset({"goal"})
    assert script_options(source) == {"A": "A", "B": "B"}
