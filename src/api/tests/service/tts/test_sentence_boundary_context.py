"""Keep sentence boundaries stable around contextual quotation marks."""

import pytest
from flaskr.service.tts.sentence_boundary import (
    SentenceBoundaryPattern,
    strip_leading_closing_quotes,
)


@pytest.fixture
def pattern() -> SentenceBoundaryPattern:
    return SentenceBoundaryPattern(
        r"[\p{Sentence_Terminal};\uFF1B\u061B\u037E]+",
        r"[\p{Pe}\p{Pf}\"']",
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("„Hallo!“ Weiter.", ["„Hallo!“", "Weiter."]),
        ("‚Hallo!‘ Weiter.", ["‚Hallo!‘", "Weiter."]),
        ("»Hallo!« Weiter.", ["»Hallo!«", "Weiter."]),
        ("第一句。「第二句。」", ["第一句。", "「第二句。」"]),
        ("第一句。“第二句。”", ["第一句。", "“第二句。”"]),
        ('First."Next."', ["First.", '"Next."']),
        ("First. « Bonjour. »", ["First.", "« Bonjour. »"]),
        ("» Hallo! « Weiter.", ["» Hallo! «", "Weiter."]),
        ("«\u00a0Bonjour.\u00a0» Après.", ["«\u00a0Bonjour.\u00a0»", "Après."]),
        ("〝你好！〞继续。", ["〝你好！〞", "继续。"]),
        ("〝你好！〟继续。", ["〝你好！〟", "继续。"]),
        ("｢你好！｣继续。", ["｢你好！｣", "继续。"]),
        ('"Ready?!" Next.', ['"Ready?!"', "Next."]),
    ],
)
def test_contextual_quote_boundaries(
    pattern: SentenceBoundaryPattern, text: str, expected: list[str]
) -> None:
    units = []
    cursor = 0
    for match in pattern.finditer(text):
        units.append(text[cursor : match.end()].strip())
        cursor = match.end()
    if text[cursor:].strip():
        units.append(text[cursor:].strip())
    assert units == expected


@pytest.mark.parametrize("opening", ["「", "『", "〝", "“", "‘", "«", "‹"])
def test_opening_quote_at_current_buffer_end_is_not_consumed(
    pattern: SentenceBoundaryPattern, opening: str
) -> None:
    text = f"第一句。{opening}"
    matches = list(pattern.finditer(text))
    assert len(matches) == 1
    assert matches[0].group() == "。"
    assert text[matches[0].end() :] == opening
    assert matches[0].quote_state == ()


@pytest.mark.parametrize(
    "quote_run", ['"', "'", '""', "''", "\"'", "'\"", '")', "»", "›", "”", "’"]
)
def test_live_buffer_keeps_the_entire_unmatched_quote_run(
    pattern: SentenceBoundaryPattern, quote_run: str
) -> None:
    source = f"First.{quote_run}"
    match = next(pattern.finditer(source, is_final=False))
    assert match.group() == "."
    assert match.end() == len("First.")
    assert source[match.end() :] == quote_run
    assert match.quote_state == ()
    # Complete-text consumers retain the established unmatched-closer policy.
    assert next(pattern.finditer(source)).end() == len(source)


@pytest.mark.parametrize(
    ("opener", "closer"),
    [('"', '"'), ("'", "'"), ("»", "«"), ("›", "‹"), ("”", "”"), ("’", "’")],
)
def test_unconsumed_quote_opens_the_next_streamed_sentence(
    pattern: SentenceBoundaryPattern, opener: str, closer: str
) -> None:
    first_chunk = f"First.{opener}"
    first_match = next(pattern.finditer(first_chunk, is_final=False))
    remaining = first_chunk[first_match.end() :] + f"Next.{closer}"
    matches = list(
        pattern.finditer(
            remaining, initial_quote_state=first_match.quote_state, is_final=False
        )
    )
    assert remaining == f"{opener}Next.{closer}"
    assert matches[0].end() == len(remaining)
    assert matches[0].quote_state == ()


def test_live_buffer_consumes_a_known_closer_before_a_new_ambiguous_quote(
    pattern: SentenceBoundaryPattern,
) -> None:
    source = '"First.""'
    match = next(pattern.finditer(source, is_final=False))
    assert source[: match.end()] == '"First."'
    assert source[match.end() :] == '"'
    assert match.quote_state == ()


def test_source_offsets_and_nested_quote_state_are_preserved(
    pattern: SentenceBoundaryPattern,
) -> None:
    text = "  «„Hallo! Noch da?“» Weiter."
    matches = list(pattern.finditer(text))
    assert [match.group() for match in matches] == ["!", "?“»", "."]
    assert matches[0].start() == text.index("!")
    assert matches[0].end() == text.index("!") + 1
    assert matches[0].quote_state_before == ()
    assert matches[0].quote_state == ("«", "„")
    assert matches[1].quote_state_before == ("«", "„")
    assert matches[1].quote_state == ()
    assert matches[-1].end() == len(text)


def test_late_german_closer_uses_state_from_consumed_sentence(
    pattern: SentenceBoundaryPattern,
) -> None:
    first = list(pattern.finditer("„Hallo!"))[-1]
    assert first.quote_state == ("„",)
    second = "“ Weiter."
    matches = list(pattern.finditer(second, initial_quote_state=first.quote_state))
    assert matches[0].quote_state_before == ("„",)
    assert matches[0].quote_state == ()
    assert matches[0].start() == second.index(".")
    assert matches[0].end() == len(second)
    assert strip_leading_closing_quotes(second, first.quote_state) == "Weiter."
    assert strip_leading_closing_quotes("“", first.quote_state) == ""


@pytest.mark.parametrize(
    ("text", "state", "expected"),
    [
        ("”» Next.", ("«", "“"), "Next."),
        (")”» Next.", ("«", "“"), "Next."),
        (")”» Next.", (), ")”» Next."),
        (")« Next.", ("„",), ")« Next."),
        ('» "Next."', ("«",), '"Next."'),
        ("“Weiter.", ("„",), "Weiter."),
        (" « Bonjour. »", (), " « Bonjour. »"),
        ("« Bonjour. »", ("„",), "« Bonjour. »"),
        ('"Next."', (), '"Next."'),
        ('" Next."', (), '" Next."'),
        ("'tis fine.", ("'",), "'tis fine."),
        ("’tis fine.", ("‘",), "’tis fine."),
        ("»Hallo!«", (), "»Hallo!«"),
    ],
)
def test_only_pending_quote_closers_are_removed(
    text: str, state: tuple[str, ...], expected: str
) -> None:
    assert strip_leading_closing_quotes(text, state) == expected


def test_word_internal_apostrophes_do_not_create_quote_state(
    pattern: SentenceBoundaryPattern,
) -> None:
    matches = list(pattern.finditer("Don't stop. O’Neill agrees! The students' work."))
    assert [match.quote_state for match in matches] == [(), (), ()]


@pytest.mark.parametrize("mark", ['"', "\uff02", "\u201d"])
def test_measurement_marks_do_not_consume_a_later_opening_quote(
    pattern: SentenceBoundaryPattern, mark: str
) -> None:
    source = f'5{mark} screen. "Try it."'
    matches = list(pattern.finditer(source))
    assert source[: matches[0].end()] == f"5{mark} screen."
    assert source[matches[0].end() : matches[1].end()].strip() == '"Try it."'
    assert [match.quote_state for match in matches] == [(), ()]
    assert strip_leading_closing_quotes('"Try it."', matches[0].quote_state) == (
        '"Try it."'
    )


def test_only_matched_quote_spacing_is_added_to_the_source_span(
    pattern: SentenceBoundaryPattern,
) -> None:
    source = "« Bonjour. »  « Nouveau. »"
    matches = list(pattern.finditer(source))
    assert matches[0].group() == ". »"
    assert source[: matches[0].end()] == "« Bonjour. »"
    assert source[matches[0].end() :] == "  « Nouveau. »"
    assert matches[0].quote_state == ()
    assert matches[1].quote_state_before == ()


@pytest.mark.parametrize(("opener", "apostrophe"), [("'", "'"), ("‘", "’")])
def test_apostrophe_starting_the_next_sentence_does_not_close_the_quote(
    pattern: SentenceBoundaryPattern, opener: str, apostrophe: str
) -> None:
    source = f"{opener}Hello. {apostrophe}tis a fine day.{apostrophe}"
    matches = list(pattern.finditer(source))
    assert source[: matches[0].end()] == f"{opener}Hello."
    assert source[matches[0].end() : matches[1].end()].strip() == (
        f"{apostrophe}tis a fine day.{apostrophe}"
    )
    assert matches[0].quote_state == (opener,)
    assert matches[1].quote_state_before == (opener,)
    assert matches[1].quote_state == ()


@pytest.mark.parametrize("text", ["!?”", "!?”)", "!?”]", '!?”"'])
def test_legacy_unpaired_closing_marks_remain_attached(
    pattern: SentenceBoundaryPattern, text: str
) -> None:
    matches = list(pattern.finditer(text))
    assert len(matches) == 1
    assert matches[0].end() == len(text)
