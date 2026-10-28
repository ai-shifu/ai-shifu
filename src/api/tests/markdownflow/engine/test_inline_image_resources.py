"""Inline image resources use paragraph text after physical container prefixes."""

import pytest
from markdown_it import MarkdownIt
from markdownflow.engine import (
    ScriptBundle,
    collected_names,
    marker_context,
    render_first_prompt,
    substitute_variables,
)
from markdownflow.engine.tools import script_options


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("spelling", ["{{goal}}", "%{{goal}}"])
@pytest.mark.parametrize(
    ("opening", "continuation"),
    [
        ("", ""),
        ("", "> "),
        ("> ", "> "),
        ("> ", ""),
        ("> ", "> > "),
        ("> - ", ">   "),
        ("> - ", "> "),
        ("- > ", "  > "),
        ("- > ", "  "),
        ("- > ", ""),
        ("1. ", "   "),
        ("1. ", ""),
        ("1. ", "2. "),
        ("> > ", "> > "),
        ("> > ", "> "),
        ("> > ", ""),
        ("> ", "   > "),
        ("> ", ">    "),
    ],
)
@pytest.mark.parametrize(
    "resource",
    [
        "(/x)",
        "(\n/x\n)",
        '(/x\n"title")',
        '(/x "one\ntwo")',
        '(/x "one\n\ntwo")',
        '(\n/x "title"\n)',
        "(\n<x>\n)",
        "(/x(a)\n 'title')",
        '(/x "a\\"b\nc")',
        '(/x "a\n# heading\nb")',
        "(\n/x\n",
        "(\n/x trailing\n)",
        "(\n\n/x\n)",
        "(\n/x\n# heading\n)",
        '(/x "a\n```\nb")',
        '(/x "a\n<!-- x -->\nb")',
        '(/x "a\n- next\nb")',
        '(/x "a\n---\nb")',
        '(/x "a\n===\nb")',
        '(/x "a\n<script>\nb")',
        '(/x "a\n<div>\nb")',
        '(/x "a\n<custom>\nb")',
    ],
)
def test_inline_image_resource_admission_matches_native_rendering(
    opening: str,
    continuation: str,
    resource: str,
    spelling: str,
    newline: str,
) -> None:
    """Real images hide their alt controls; malformed or interrupted images do not."""
    source = (
        f"{opening}![?[{spelling} A | B]]" + resource.replace("\n", "\n" + continuation)
    ).replace("\n", newline)
    image = "<img " in MarkdownIt().render(source)
    # Percent declarations retain their established global collection behavior.
    expected_names = (
        frozenset({"goal"}) if spelling.startswith("%") or not image else frozenset()
    )
    assert collected_names(source) == expected_names
    assert script_options(source) == ({} if image else {"A": "A", "B": "B"})


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize(
    "image",
    [
        "> ![?[{{goal}} A | B]](\n> /x\n> )",
        '> ![?[{{goal}} A | B]](/x\n> "title")',
        '> - ![?[{{goal}} A | B]](/x "one\n>   two")',
        "- > ![?[{{goal}} A | B]](\n  > /x\n  > )",
        '> > ![?[{{goal}} A | B]](/x "one\n> two")',
        '> ![?[{{goal}} A | B]](/x "one\n===\ntwo")',
    ],
)
def test_multiline_image_alt_preserves_existing_memory_and_following_question(
    image: str, newline: str
) -> None:
    image = image.replace("\n", newline)
    assert "<img " in MarkdownIt().render(image)
    source = image + newline * 2 + "Read {{goal}}."
    assert collected_names(source) == frozenset()
    assert '"current"' in render_first_prompt(
        ScriptBundle(script=source), {"goal": "current"}
    )
    assert "{{goal}}" not in substitute_variables(source, {"goal": "current"})
    source += newline * 2 + "?[{{visible}} C | D]"
    assert collected_names(source) == frozenset({"visible"})
    assert script_options(source) == {"C": "C", "D": "D"}


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("spelling", ["{{goal}}", "%{{goal}}"])
@pytest.mark.parametrize(
    ("prefix", "opening", "continuation", "image"),
    [
        ("> prefix\n", "", "", True),
        ("> - prefix\n", "> ", "> ", True),
        ("- > prefix\n", "  ", "  ", True),
        ("prefix\n", "", "", False),
        ("> # heading\n", "", "", False),
        ("> <!-- x -->\n", "", "", False),
    ],
)
def test_inline_resources_follow_the_owning_paragraph_after_lazy_lines(
    prefix: str,
    opening: str,
    continuation: str,
    image: bool,
    spelling: str,
    newline: str,
) -> None:
    """Lazy underlines belong to the original paragraph, not a missing prefix."""
    source = (
        prefix
        + f'{opening}![?[{spelling} A | B]](/x "a\n'
        + continuation
        + "===\n"
        + continuation
        + 'b")'
    ).replace("\n", newline)
    assert ("<img " in MarkdownIt().render(source)) is image
    expected_names = (
        frozenset({"goal"}) if spelling.startswith("%") or not image else frozenset()
    )
    assert collected_names(source) == expected_names
    assert script_options(source) == ({} if image else {"A": "A", "B": "B"})


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("spelling", ["{{goal}}", "%{{goal}}"])
@pytest.mark.parametrize("html", ["<div>", "<table>", "</div>", "<custom>"])
@pytest.mark.parametrize("title_line", ["1.", "2. next"])
@pytest.mark.parametrize(
    ("html_container", "image_container"),
    [("> ", ""), ("> > ", "> "), ("> - ", "> "), ("- > ", "  "), ("- ", "")],
)
def test_inline_image_titles_follow_html_container_dedents(
    html_container: str,
    image_container: str,
    html: str,
    title_line: str,
    spelling: str,
    newline: str,
) -> None:
    """A completed HTML container cannot make title text start a new list."""
    source = (
        f"{html_container}{html}\n"
        f'{image_container}![?[{spelling} A | B]](/x "a\n'
        f"{image_container}{title_line}\n"
        f'{image_container}b")'
    ).replace("\n", newline)
    assert "<img " in MarkdownIt().render(source)
    expected_names = frozenset({"goal"}) if spelling.startswith("%") else frozenset()
    assert collected_names(source) == expected_names
    assert script_options(source) == {}


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("html", ["<div>", "<custom>"])
@pytest.mark.parametrize("body", ["> body", "> - body"])
def test_quoted_blank_ends_html_before_the_next_image_paragraph(
    html: str, body: str, newline: str
) -> None:
    """The constructor recognizes blank bodies before future prefixes are indexed."""
    source = (
        f'> {html}\n{body}\n>\n> ![?[{{{{goal}}}} A | B]](/x "a\n> 1.\n> b")'
    ).replace("\n", newline)
    assert "<img " in MarkdownIt().render(source)
    assert collected_names(source) == frozenset()
    assert script_options(source) == {}


@pytest.mark.parametrize("size", [100, 200, 400])
def test_resource_boundaries_reuse_lazy_suffixes_without_repeated_scans(
    monkeypatch: pytest.MonkeyPatch, size: int
) -> None:
    """Many complete images cannot repeatedly scan the same later lazy lines."""
    calls = 0
    original = marker_context.container_content_start

    def counted(
        line: str, steps: tuple[int, ...], *, partial: bool = False
    ) -> int | None:
        nonlocal calls
        calls += 1
        return original(line, steps, partial=partial)

    monkeypatch.setattr(marker_context, "container_content_start", counted)
    source = "> " + "![image](/x) " * size + "\n" + "===\n" * size + "tail"
    assert MarkdownIt().render(source).count("<img ") == size
    assert len(marker_context.analyze_marker_context(source).image_labels) == size
    assert calls <= 4 * size
