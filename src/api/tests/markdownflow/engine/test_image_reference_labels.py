"""Reference image labels compare projected paragraph text at original offsets."""

from string import punctuation

import pytest
from markdown_it import MarkdownIt
from markdownflow.engine import (
    ScriptBundle,
    collected_names,
    render_first_prompt,
    substitute_variables,
)
from markdownflow.engine.document_blocks import DocumentBlocks
from markdownflow.engine.marker_context import (
    _INLINE_HTML,
    _image_reference_label,
    analyze_marker_context,
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
    ("label", "definition"),
    [
        ("[course image]", "course image"),
        ("[course\nimage]", "course image"),
        ("[course\n\nimage]", "course image"),
        ("[course\n# heading\nimage]", "course image"),
        ("[\ncourse image\n]", "course image"),
        ("[course\\\nimage]", "course image"),
        ("[course\nimage", "course image"),
        ("[course\nimage][other]", "course image"),
        ("[course\timage]", "course image"),
        ("[course \n image]", "course image"),
        ("[course\n> image]", "course image"),
        ("[course\n1. image]", "course 1. image"),
        ("[course\n2. image]", "course 2. image"),
        ("[course\n===\nimage]", "course === image"),
        (r"[course\[image\]]", r"course\[image\]"),
        ("[course {{ key[thing] }}]", "course {{ key[thing] }}"),
        ("[course\n<!-- x -->\nimage]", "course image"),
    ],
)
def test_reference_image_labels_follow_native_paragraph_projection(
    opening: str,
    continuation: str,
    label: str,
    definition: str,
    spelling: str,
    newline: str,
) -> None:
    """Only renderer-confirmed images can deactivate their authored alt control."""
    source = (
        f"{opening}![?[{spelling} A | B]]"
        + label.replace("\n", "\n" + continuation)
        + f"\n\n[{definition}]: /x"
    ).replace("\n", newline)
    image = "<img " in MarkdownIt().render(source)
    expected_names = (
        frozenset({"goal"}) if spelling.startswith("%") or not image else frozenset()
    )
    assert collected_names(source) == expected_names
    assert script_options(source) == ({} if image else {"A": "A", "B": "B"})


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_multiline_reference_label_preserves_memory_and_following_control(
    newline: str,
) -> None:
    source = (
        "> ![?[{{goal}} A | B]][course\n> image]\n>\n> [course image]: /x"
    ).replace("\n", newline)
    assert "<img " in MarkdownIt().render(source)
    assert collected_names(source) == frozenset()
    assert '"current"' in render_first_prompt(
        ScriptBundle(script=source), {"goal": "current"}
    )
    assert "{{goal}}" not in substitute_variables(source, {"goal": "current"})
    source += newline * 2 + "?[{{visible}} C | D]"
    assert collected_names(source) == frozenset({"visible"})
    assert script_options(source) == {"C": "C", "D": "D"}


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("suffix", ["", "[]"])
@pytest.mark.parametrize(
    ("opening", "continuation"),
    [("> ", "> "), ("> ", ""), ("> - ", ">   "), ("- > ", "  > ")],
)
def test_existing_collapsed_and_shortcut_images_project_their_alt_label(
    opening: str, continuation: str, suffix: str, newline: str
) -> None:
    source = (
        f"{opening}![course\n{continuation}image]{suffix}\n\n[course image]: /x"
    ).replace("\n", newline)
    assert "<img " in MarkdownIt().render(source)
    context = analyze_marker_context(source)
    assert context.image_labels == [(source.index("![") + 1, source.index("]") + 1)]


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("size", [999, 1000])
@pytest.mark.parametrize("depth", [1, 8, 32])
def test_reference_label_bounds_count_projected_characters(
    depth: int, size: int, newline: str
) -> None:
    prefix = "> " * depth
    first = "x" * (size - 5)
    source = (
        f"{prefix}![?[{{{{goal}}}} A | B]][{first}\n{prefix}tail]\n\n[{first} tail]: /x"
    ).replace("\n", newline)
    # Raising this rendering policy tests grammar without dropping deep content.
    assert "<img " in MarkdownIt("commonmark", {"maxNesting": 128}).render(source)
    # Keep the native bound even though this renderer accepts oversized definitions.
    image = size == 999
    assert collected_names(source) == (frozenset() if image else frozenset({"goal"}))
    assert script_options(source) == ({} if image else {"A": "A", "B": "B"})


@pytest.mark.parametrize("depth", [16, 128, 1024])
def test_reference_label_cursor_does_not_rescan_physical_quote_prefixes(
    depth: int,
) -> None:
    work = 0

    class CountedText(str):
        __slots__ = ()

        def __getitem__(self, index: int | slice) -> str:
            nonlocal work
            result = super().__getitem__(index)
            work += len(result)
            return result

    prefix = "> " * depth
    text = CountedText(f"{prefix}![x][a\n{prefix}b]")
    blocks = DocumentBlocks(text, _INLINE_HTML)
    start = text.index("][") + 1
    work = 0
    assert _image_reference_label(text, start, blocks, len(text)) == "a\nb"
    assert work <= 12


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("spelling", ["{{goal}}", "%{{goal}}"])
@pytest.mark.parametrize("definition_first", [False, True])
@pytest.mark.parametrize(
    ("opening", "continuation"),
    [
        ("", ""),
        ("> ", "> "),
        ("> ", ""),
        ("> - ", ">   "),
        ("> - ", "> "),
        ("- > ", "  > "),
        ("1. ", "   "),
    ],
)
@pytest.mark.parametrize(
    ("label", "definition"),
    [
        ("course\\\nimage", "course\\ image"),
        ("course\\ image", "course\\\nimage"),
        ("course\\\nimage", "course\\\nimage"),
        ("course\\\\\nimage", "course\\\\ image"),
        ("course\\\\\\\nimage", "course\\\\\\ image"),
        ("course\\\\\\\\\nimage", "course\\\\\\\\ image"),
        ("course\\\n  image", "course\\ image"),
        ("course\\\timage", "course\\ image"),
        ("course\\ image", "course\\ image"),
        ("course\\\nimage", "course image"),
        ("course\\\nimage", "undefined"),
        ("course\\\n\nimage", "course\\ image"),
        ("course[image", "course[image"),
        ("course\\", "course\\"),
        ("course\\\\", "course\\\\"),
        ("course\\\\\\", "course\\\\\\"),
        ("course\\\\\\\\", "course\\\\\\\\"),
    ],
)
def test_reference_label_backslashes_preserve_projected_physical_endings(
    label: str,
    definition: str,
    opening: str,
    continuation: str,
    definition_first: bool,
    spelling: str,
    newline: str,
) -> None:
    """Reference identifiers keep literal slashes while folding label whitespace."""
    image_use = (
        f"{opening}![?[{spelling} A | B]]["
        + label.replace("\n", "\n" + continuation)
        + "]"
    )
    definition_text = f"[{definition}]: /x"
    source = (
        f"{definition_text}\n\n{image_use}"
        if definition_first
        else f"{image_use}\n\n{definition_text}"
    ).replace("\n", newline)
    image = "<img " in MarkdownIt().render(source)
    source += newline * 2 + "?[{{visible}} C | D]"
    expected_names = {"visible"} | (
        {"goal"} if spelling.startswith("%") or not image else set()
    )
    assert collected_names(source) == frozenset(expected_names)
    expected_options = {"C": "C", "D": "D"} | ({} if image else {"A": "A", "B": "B"})
    assert script_options(source) == expected_options
    if image and not spelling.startswith("%"):
        assert '"current"' in render_first_prompt(
            ScriptBundle(script=source), {"goal": "current"}
        )
        assert "{{goal}}" not in substitute_variables(source, {"goal": "current"})


@pytest.mark.parametrize("character", [*punctuation, "q", " ", "\t", "é"])
@pytest.mark.parametrize("matches", [False, True])
@pytest.mark.parametrize("spelling", ["{{goal}}", "%{{goal}}"])
def test_reference_label_escapes_retain_the_raw_identifier(
    character: str, matches: bool, spelling: str
) -> None:
    """Escaped punctuation and literal nonpunctuation never lose their slash."""
    label = f"course\\{character}image"
    definition = label if matches else f"course{character}image"
    source = f"![?[{spelling} A | B]][{label}]\n\n[{definition}]: /x"
    image = "<img " in MarkdownIt().render(source)
    expected_names = (
        frozenset({"goal"}) if spelling.startswith("%") or not image else frozenset()
    )
    assert collected_names(source) == expected_names
    assert script_options(source) == ({} if image else {"A": "A", "B": "B"})
