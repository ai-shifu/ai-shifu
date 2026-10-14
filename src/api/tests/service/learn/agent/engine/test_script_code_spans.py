"""Bound inline-code matching work for adversarial authored Markdown."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest
from flaskr.service.learn.agent.engine import script_code_spans
from flaskr.service.learn.agent.engine.script_code_spans import build_code_span_index
from flaskr.service.learn.agent.engine.script_comments import strip_comments

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("`a`", {0: 3}),
        ("`a`b`", {0: 3, 2: 5}),
        ("`a``b`c``", {0: 6, 2: 9}),
        ("`a\nb`", {0: 5}),
        ("`a\rb`", {0: 5}),
        ("`a\r\nb`", {0: 6}),
        ("`a\n\nb`", {}),
        ("`a\r\rb`", {}),
        ("`a\r\n\r\nb`", {}),
        ("`a\n \t\nb`", {}),
        ("`a\nline\nb`", {0: 10}),
        (r"\``a`", {2: 5}),
        (r"\``a\``b`", {1: 7, 2: 9, 6: 9}),
        (r"`a\``b`", {0: 7, 4: 7}),
    ],
)
def test_indexes_the_next_matching_run_in_the_same_paragraph(
    source: str, expected: dict[int, int]
) -> None:
    assert build_code_span_index(source) == expected


@pytest.mark.parametrize("linebreak", ["\n", "\r", "\r\n"])
def test_code_examples_can_cross_one_physical_linebreak(linebreak: str) -> None:
    source = f"`<!-- literal{linebreak}example -->` <!-- private -->"
    assert strip_comments(source) == source.removesuffix("<!-- private -->")


def test_skipped_comment_delimiters_do_not_consume_a_later_code_opening() -> None:
    source = "Intro <!-- `private` --> `<!-- literal -->` <!-- private -->"
    assert strip_comments(source) == "Intro  `<!-- literal -->` "


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (r"\``<!-- literal -->` <!-- private -->", r"\``<!-- literal -->` "),
        (r"`literal\`` <!-- private -->", r"`literal\`` "),
        (r"`literal\` <!-- private -->", r"`literal\` "),
    ],
)
def test_escaped_openers_and_literal_backslashes_keep_code_examples(
    source: str, expected: str
) -> None:
    assert strip_comments(source) == expected


def test_unmatched_run_lengths_are_indexed_with_one_document_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = " ".join("`" * length for length in range(1, 1001))
    scans: list[int] = []
    visits = 0
    tokens = re.compile(r"`+|\r\n|[\r\n]")

    class CountingTokens:
        def finditer(self, text: str) -> Iterator[re.Match[str]]:
            nonlocal visits
            scans.append(len(text))
            for token in tokens.finditer(text):
                visits += 1
                yield token

    monkeypatch.setattr(script_code_spans, "_TOKENS", CountingTokens())
    assert build_code_span_index(source) == {}
    assert scans == [len(source)]
    assert visits == 1000


def test_comment_filter_uses_one_index_for_all_unmatched_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Starting after prose keeps the long runs outside a fenced code block.
    source = "prose " + " ".join("`" * length for length in range(1, 1001))
    source += " <!-- private -->"
    scans: list[int] = []
    tokens = re.compile(r"`+|\r\n|[\r\n]")

    class CountingTokens:
        def finditer(self, text: str) -> Iterator[re.Match[str]]:
            scans.append(len(text))
            yield from tokens.finditer(text)

    monkeypatch.setattr(script_code_spans, "_TOKENS", CountingTokens())
    assert strip_comments(source) == source.removesuffix("<!-- private -->")
    assert scans == [len(source)]
