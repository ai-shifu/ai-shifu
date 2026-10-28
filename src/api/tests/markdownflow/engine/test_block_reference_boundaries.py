"""Native block precedence keeps image references outside interaction parsing."""

import re
from types import SimpleNamespace

import pytest
from markdown_it import MarkdownIt
from markdownflow.engine import collected_names, document_blocks
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
