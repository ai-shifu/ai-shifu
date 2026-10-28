"""Validated reference resources, rather than prefixes, close a paragraph."""

import re

import pytest
from markdown_it import MarkdownIt
from markdown_it.common.html_re import HTML_TAG_RE
from markdownflow.engine import collected_names, document_blocks
from markdownflow.engine.document_blocks import DocumentBlocks
from markdownflow.engine.tools import script_options

REFERENCE_BODIES = [
    "[one]: /one",
    "[one]: <one>",
    "[one]: <>",
    "[one]: /one (title)",
    '[one]: /one\n "title"',
    '[one]: /one "title\nmore"',
    "[one]:\n/one",
    "[one]:\n<one>",
    "[o\nne]: /one",
    r"[o\[ne]: /one",
    " [one]: /one",
    "[one]: /one trailing",
    '[one]: /one "unclosed',
    '[one]: /one "a\n\nb"',
    '[one]: /one\n "a\n\nb"',
    "[one]:",
    "[one] /one",
    "[o[ne]]: /one",
    "[o[ne]: /one",
    r"\[one]: /one",
    "[one]: <bad\nurl>",
    "[one]: /bad(unclosed",
    "[one]: /bad)end",
    "paragraph\n[one]: /one",
    "[one]: /one\nparagraph",
    "[one]: /one\n[two]: /two",
    "[one]: /one\n[two]: /two trailing",
    "[one]:\n\n/one",
    '[one]: /one "a\n2. item\nb"',
    '[one]: /one "a\n# heading\nb"',
    '[one]: /one "a\n===\nb"',
    '[one]: /one "a\n<!-- comment -->\nb"',
    "[one]: javascript:alert",
    "[one]: <javascript:alert>",
    r"[one]: javascript\:alert",
    "[one]: java&#x73;cript:alert",
    "[one]: &#106;avascript:alert",
    "[one]: vbscript:alert",
    "[one]: file:///one",
    "[one]: data:text/html,x",
    "[one]: data:image/svg+xml,x",
    "[one]: data:image/png;base64,x",
    "[one]: data:image/jpeg;base64,x",
    "[one]: https://example.com/one",
    "[one]: <relative path>",
]
CONTAINER_CONTEXTS = [
    ("", ""),
    ("> ", "> "),
    ("- ", "  "),
    ("1. ", "   "),
    ("> - ", ">   "),
    ("- > ", "  > "),
]
HTML_PATTERN = re.compile(HTML_TAG_RE.pattern.removeprefix("^"))


@pytest.mark.parametrize("body", REFERENCE_BODIES)
@pytest.mark.parametrize(("opening", "continuation"), CONTAINER_CONTEXTS)
@pytest.mark.parametrize("marker", ["2. ", "9) ", "2. [other]: /other\n3. "])
@pytest.mark.parametrize("spelling", ["{{goal}}", "%{{goal}}"])
def test_only_validated_reference_resources_admit_fresh_ordered_items(
    body: str, opening: str, continuation: str, marker: str, spelling: str
) -> None:
    prefix = opening + body.replace("\n", "\n" + continuation)
    following = continuation + marker.replace("\n", "\n" + continuation)
    source = f"![?[{spelling} A | B]][image]\n\n{prefix}\n{following}[image]: /x"
    image = "<img " in MarkdownIt().render(source)
    expected_names = (
        frozenset({"goal"}) if spelling.startswith("%") or not image else frozenset()
    )
    assert collected_names(source) == expected_names
    assert script_options(source) == ({} if image else {"A": "A", "B": "B"})


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize(
    "body",
    [
        "> [one]:\n>\n> /one\n> 2. [image]: /x",
        '> [one]: /one "a\n>\n> b"\n> 2. [image]: /x',
        "> [o\n> # heading\n> ne]: /one\n> 2. [image]: /x",
        "> [o\n> - item\n> ne]: /one\n> 2. [image]: /x",
        "> [o\n> <!-- comment -->\n> ne]: /one\n> 2. [image]: /x",
        "[first]: /first\n2. > [o\n   > ne]: /one\n   > 3. [image]: /x",
        '[first]: /first\n2. > [one]: /one "a\n   > line\n   > b"\n   > 3. [image]: /x',
        "[first]: /first\n2. > [one]:\n   >\n   > /one\n   > 3. [image]: /x",
    ],
)
def test_reference_future_projection_uses_the_owning_container(
    body: str, newline: str
) -> None:
    source = ("![?[{{goal}} A | B]][image]\n\n" + body).replace("\n", newline)
    image = "<img " in MarkdownIt().render(source)
    assert collected_names(source) == (frozenset() if image else frozenset({"goal"}))
    assert script_options(source) == ({} if image else {"A": "A", "B": "B"})


@pytest.mark.parametrize("size", [100, 200, 400])
@pytest.mark.parametrize(
    "unit",
    ["[one]: /one\n", "> [o\n> ne]: /one\n", '> [one]: /one "a\n> line\n> b"\n'],
)
def test_reference_closure_lookahead_has_bounded_work(
    monkeypatch: pytest.MonkeyPatch, size: int, unit: str
) -> None:
    calls = 0
    original = document_blocks.DocumentBlocks.reference_projection

    def counted(
        self: DocumentBlocks, index: int, steps: tuple[int, ...]
    ) -> tuple[int, str, bool]:
        nonlocal calls
        calls += 1
        return original(self, index, steps)

    monkeypatch.setattr(DocumentBlocks, "reference_projection", counted)
    source = unit * size
    blocks = DocumentBlocks(source, HTML_PATTERN)
    assert calls <= 8 * len(blocks.lines)
