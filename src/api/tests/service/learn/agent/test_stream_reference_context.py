"""Settle native reference definitions before classifying their raw marker text."""

import pytest
from flaskr.service.learn.agent.interaction_syntax import InteractionSyntaxFilter
from markdownflow.engine.stream_marker_context import (
    compact_marker_context,
    pending_literal_context,
)

INNER = "?[A|B]"
QUESTION = "?[%{{ real }} C|D]"


def _assert_streams(source: str, expected: tuple[str, list[str]]) -> None:
    streams = [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]
    for chunks in streams:
        syntax = InteractionSyntaxFilter()
        shown = "".join(syntax.feed(chunk) for chunk in chunks) + syntax.flush()
        assert (shown, syntax.spans) == expected, chunks


@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize(
    ("body", "extract"),
    [
        ("{{?[A|B]}}", True),
        ("{{?[A|B]}} text", False),
        ('{{?[A|B]}} "note"', True),
        ('{{?[A|B]}} "note" extra', False),
        ("<{{?[A|B]}}>", True),
        ("<{{?[A|B]}}", False),
        ("{{?[A|B] answer}}", False),
        ("<{{?[A|B] answer}}>", True),
        ('{{?[A|B]}}\n"note"', True),
        ("{{?[A|B]}}\ntext", True),
    ],
)
def test_reference_literal_and_raw_marker_fallback_agree_at_every_cut(
    ending: str, body: str, extract: bool
) -> None:
    source = "[ref]: " + body.replace("\n", ending)
    expected = (
        source.replace(INNER, "") if extract else source,
        [INNER] if extract else [],
    )
    _assert_streams(source, expected)


@pytest.mark.parametrize("container", ["", "> ", "- "])
@pytest.mark.parametrize("extract", [False, True])
def test_reference_resolution_does_not_consume_the_following_authored_question(
    container: str, extract: bool
) -> None:
    prefix = (
        container + "[ref]: {{" + INNER + "}}" + ("" if extract else " text") + "\n\n"
    )
    source = prefix + QUESTION
    _assert_streams(
        source,
        (
            prefix.replace(INNER, "") if extract else prefix,
            ([INNER] if extract else []) + [QUESTION],
        ),
    )


@pytest.mark.parametrize("slashes", range(4))
@pytest.mark.parametrize("valid", [False, True])
def test_reference_raw_marker_escape_parity_survives_prefix_compaction(
    slashes: int, valid: bool
) -> None:
    source = (
        "[ref]: " + "\\" * slashes + "{{" + INNER + "}}" + ("" if valid else " text")
    )
    extract = valid or slashes % 2 == 1
    _assert_streams(
        source,
        (source.replace(INNER, "") if extract else source, [INNER] if extract else []),
    )


def test_pending_reference_ranges_are_native_bounded_and_skip_escaped_openers() -> None:
    source = "[ref]: \\{{escaped}}-{{" + INNER
    spans: list[tuple[int, int]] = []
    pending = pending_literal_context(source, reference_markers=spans)
    assert pending is not None
    assert spans == [(source.index("{{", source.index("-")), len(source))]
    invalid_spans: list[tuple[int, int]] = []
    assert (
        pending_literal_context(
            "[ref]: {{" + INNER + "}} text", reference_markers=invalid_spans
        )
        is None
    )
    assert invalid_spans == []


def test_long_reference_deferral_keeps_only_bounded_syntax_witnesses() -> None:
    prefix = "[ref]: {{" + INNER
    source = prefix + "x" * 3000 + "}} text\n\n" + QUESTION
    syntax = InteractionSyntaxFilter()
    shown: list[str] = []
    for character in source:
        shown.append(syntax.feed(character))
        assert len(syntax._context_prefix) <= 128
        assert syntax._pending_literal is None or len(syntax._pending_literal) <= 128
    shown.append(syntax.flush())
    assert "".join(shown) == source[: -len(QUESTION)]
    assert syntax.spans == [QUESTION]
    witness = ""
    for character in "[ref]: " + "x" * 3000 + "{{":
        witness = compact_marker_context(witness + character)
        assert len(witness) <= 128
    assert witness.endswith("{{")
