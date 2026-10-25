"""Settle native reference definitions without giving ordinary braces lexical ownership."""

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
        ("{{?[A|B]}}", False),
        ("{{?[A|B]}} text", True),
        ('{{?[A|B]}} "note"', False),
        ('{{?[A|B]}} "note" extra', True),
        ("<{{?[A|B]}}>", False),
        ("<{{?[A|B]}}", True),
        ("{{?[A|B] answer}}", True),
        ("<{{?[A|B] answer}}>", False),
        ('{{?[A|B]}}\n"note"', False),
        ("{{?[A|B]}}\ntext", False),
    ],
)
def test_reference_literal_and_plain_text_fallback_agree_at_every_cut(
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
            prefix if extract else prefix.replace(INNER, ""),
            ([] if extract else [INNER]) + [QUESTION],
        ),
    )


@pytest.mark.parametrize("slashes", range(4))
@pytest.mark.parametrize("valid", [False, True])
def test_reference_validity_is_independent_of_standalone_brace_escape_parity(
    slashes: int, valid: bool
) -> None:
    source = (
        "[ref]: " + "\\" * slashes + "{{" + INNER + "}}" + ("" if valid else " text")
    )
    extract = not valid
    _assert_streams(
        source,
        (source.replace(INNER, "") if extract else source, [INNER] if extract else []),
    )


def test_pending_reference_ranges_use_native_scope_without_brace_ownership() -> None:
    source = "[ref]: \\{{escaped}}-{{" + INNER
    pending = pending_literal_context(source)
    assert pending is not None
    assert pending[0] == 0
    assert pending[1] == "[x]: x"
    assert pending_literal_context("[ref]: {{" + INNER + "}} text") is None


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
    assert "".join(shown) == source.replace(INNER, "").removesuffix(QUESTION)
    assert syntax.spans == [INNER, QUESTION]
    witness = ""
    for character in "[ref]: " + "x" * 3000 + "{{":
        witness = compact_marker_context(witness + character)
        assert len(witness) <= 128
    assert witness == "[x]: {"
