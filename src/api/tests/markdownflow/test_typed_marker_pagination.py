"""Keep the existing typed stream contract when marker cleanup is explicitly enabled."""

from __future__ import annotations

import pytest
from markdown_flow import StreamFormatter
from markdownflow.pagination import LessonPager
from markdownflow.preserve_markers import PreserveMarkerFilter

HTML = "<div>===visible===<script>const equal = a === b;</script></div>"
SVG = "<svg><text>===label===</text></svg>"
CODE = "```text\n!===\n===literal===\n```"
MERMAID = '```mermaid\ngraph TD; A["===label==="] --> B\n```'


def _format(chunks: list[str]) -> list[tuple[str, str, int]]:
    """Read types and numbers from the installed formatter, without cleanup."""
    formatter = StreamFormatter()
    pieces = [
        (element.content, str(element.type), element.number)
        for chunk in chunks
        for element in formatter.process(chunk)
    ]
    pieces.extend(
        (element.content, str(element.type), element.number)
        for element in formatter.flush()
    )
    return pieces


def _page(chunks: list[str], *, clean: bool) -> list[tuple[str, str, int]]:
    """Collect a turn through the public legacy or marker-cleaning interface."""
    pager = LessonPager(clean_markers=True) if clean else LessonPager()
    pieces = [part for chunk in chunks for part in pager.add(chunk)]
    pieces.extend(pager.flush())
    assert pager.flush() == []
    return pieces


def _chunkings(source: str) -> list[list[str]]:
    return [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]


def test_marker_cleaning_remains_opt_in_for_the_legacy_pager() -> None:
    source = f"!===\n===intro===\n{HTML}\n{CODE}\n!===\n===after===\n\n"
    for chunks in _chunkings(source):
        assert _page(chunks, clean=False) == _format(chunks)


def test_cleaning_prose_keeps_the_native_visual_types_and_element_numbers() -> None:
    source = f"===intro===\n# ===heading===\n{HTML}\n===after===\n{SVG}\n{CODE}\n{MERMAID}\n===end==="
    expected = [
        ("intro\n", "text", 0),
        ("# heading\n", "title", 0),
        (HTML + "\n", "html", 1),
        ("after\n", "text", 2),
        (SVG + "\n", "svg", 3),
        ("```text\n", "code", 4),
        ("!===\n", "code", 4),
        ("===literal===\n", "code", 4),
        ("```\n", "code", 4),
        ("```mermaid\n", "mermaid", 5),
        ('graph TD; A["===label==="] --> B\n', "mermaid", 5),
        ("```\n", "mermaid", 5),
        ("end", "text", 6),
    ]
    for chunks in _chunkings(source):
        actual = _page(chunks, clean=True)
        assert actual == expected
        assert [(kind, number) for _, kind, number in actual] == [
            (kind, number) for _, kind, number in _format(chunks)
        ]


@pytest.mark.parametrize("wrapper", ["inline", "fenced"])
def test_clean_display_and_complete_saved_source_use_the_same_cleanup(
    wrapper: str,
) -> None:
    wrapped = f"==={HTML}===" if wrapper == "inline" else f"!===\n{HTML}\n!==="
    source = f"===intro===\n{wrapped}\n===after==="
    expected = f"intro\n{HTML}\nafter"
    for chunks in _chunkings(source):
        displayed = "".join(content for content, _, _ in _page(chunks, clean=True))
        marker_filter = PreserveMarkerFilter()
        saved = marker_filter.feed(source) + marker_filter.flush()
        assert displayed == saved == expected


def test_clean_pager_releases_unambiguous_complete_prose_lines() -> None:
    pager = LessonPager(clean_markers=True)
    assert pager.add("===first===\n") == [("first\n", "text", 0)]
    assert pager.add("Plain second line.\n") == [("Plain second line.\n", "text", 0)]
    assert pager.flush() == []


@pytest.mark.parametrize(
    ("opening", "kind"),
    [("<div>", "html"), ("<svg>", "svg"), ("```text", "code")],
)
def test_a_new_question_resets_unfinished_opaque_content_after_flushing_it(
    opening: str, kind: str
) -> None:
    pager = LessonPager(clean_markers=True)
    source = opening + "\n===literal==="
    narration = pager.add(source) + pager.start_block()
    assert "".join(content for content, _, _ in narration) == source
    assert {(stream_type, number) for _, stream_type, number in narration} == {
        (kind, 0)
    }
    assert pager.add("===Question===\n") == [("Question\n", "text", 1)]
    assert pager.flush() == []


def test_cleaning_preserves_html_append_identity_and_the_next_question_number() -> None:
    pager = LessonPager(clean_markers=True)
    style = '<style>p::after { content: "==="; }</style>'
    pieces = pager.add(HTML + "\n===narration===\n" + style + "\n")
    assert pieces == [
        (HTML + "\n", "html", 0),
        ("narration\n", "text", 1),
        (style + "\n", "html", 0),
    ]
    assert pager.start_block() == []
    assert pager.add("===Question===\n") == [("Question\n", "text", 2)]
    assert pager.flush() == []


@pytest.mark.parametrize("wrapper", ["inline", "fenced"])
@pytest.mark.parametrize("ending", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_removed_outer_mdf_wrappers_do_not_allocate_empty_elements(
    wrapper: str, ending: str
) -> None:
    wrapped = (
        f"==={HTML}===" if wrapper == "inline" else f"!==={ending}{HTML}{ending}!==="
    )
    source = wrapped + ending + "===after===" + ending
    expected = [(HTML + ending, "html", 0), ("after" + ending, "text", 1)]
    for chunks in _chunkings(source):
        assert _page(chunks, clean=True) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("Checklist [ ] ===now===\n", "Checklist [ ] now\n"),
        ("Literal [] ===now===\n", "Literal [] now\n"),
        (
            "See [docs](https://example/a===b). ===Now===\n",
            "See [docs](https://example/a===b). Now\n",
        ),
        (
            r"Use `[literal] a===b` and ===now===." + "\n",
            r"Use `[literal] a===b` and now." + "\n",
        ),
        (r"Escaped \[label and ===now===." + "\n", r"Escaped \[label and now." + "\n"),
        (
            "Use <git+ssh://example/a===b> and ===now===.\n",
            "Use <git+ssh://example/a===b> and now.\n",
        ),
    ],
)
def test_resolved_inline_syntax_does_not_hold_later_visuals(
    source: str, expected: str
) -> None:
    """A complete link/code span must release before a turn or interaction boundary."""
    for chunks in _chunkings(source):
        pager = LessonPager(clean_markers=True)
        pieces = [part for chunk in chunks for part in pager.add(chunk)]
        assert "".join(content for content, _, _ in pieces) == expected
        assert pager.add(HTML + "\n") == [(HTML + "\n", "html", 1)]
        assert pager.flush() == []


def test_reference_definitions_keep_native_titles_and_resolve_later_pieces() -> None:
    """A definition's next-line title must finish before its environment is committed."""
    cleaner = PreserveMarkerFilter()
    definition = '[id]: /a===b\n"===title=== cup"\n'
    assert cleaner.feed("[id]: /a===b\n") == ""
    assert cleaner.feed('"===title=== cup"\n') == ""
    assert cleaner.feed("\n") == definition + "\n"
    assert cleaner.feed(HTML + "\n") == HTML + "\n"
    assert cleaner.feed("[===caption===][id]\n") == "[caption][id]\n"
    assert cleaner.flush() == ""


def test_a_forward_definition_releases_queued_prose_and_visuals_at_its_boundary() -> (
    None
):
    """Only unresolved reference syntax needs to wait for later document context."""
    cleaner = PreserveMarkerFilter()
    assert cleaner.feed("[===caption===][id]\n") == ""
    assert cleaner.feed(HTML + "\n") == ""
    assert cleaner.feed("[id]: /a===b\n") == ""
    assert cleaner.feed("\n") == f"[caption][id]\n{HTML}\n[id]: /a===b\n\n"
    assert cleaner.feed("===after===\n") == "after\n"
    assert cleaner.flush() == ""


def test_an_empty_inline_link_label_waits_for_its_multiline_destination() -> None:
    """An empty checkbox is literal, but a pending inline destination still needs its closer."""
    cleaner = PreserveMarkerFilter()
    assert cleaner.feed("See [](/a===b\n") == ""
    assert cleaner.feed(") ===now===\n") == "See [](/a===b\n) now\n"
    assert cleaner.flush() == ""


@pytest.mark.parametrize("opening", ["``` `", "````lang`info"])
@pytest.mark.parametrize("prefix", ["", "==="])
@pytest.mark.parametrize("ending", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_invalid_fence_info_stays_prose_before_real_code(
    opening: str, prefix: str, ending: str
) -> None:
    """Only valid openers allocate opaque code elements in the cleaning pager."""
    code = ending.join(["```js", "const equal = a === b;", "```", ""])
    source = f"{prefix}{opening}{ending}===after==={ending}{ending}{code}===end==="
    expected = f"{opening}{ending}after{ending}{ending}{code}end"
    for chunks in _chunkings(source):
        pieces = _page(chunks, clean=True)
        assert "".join(content for content, _, _ in pieces) == expected
        assert "".join(content for content, kind, _ in pieces if kind == "code") == code
        assert {number for _, kind, number in pieces if kind == "code"} == {1}
        assert opening in "".join(
            content
            for content, kind, number in pieces
            if kind == "text" and number == 0
        )
        assert pieces[-1] == ("end", "text", 2)
        assert _page(chunks, clean=False) == _format(chunks)
