"""Keep generic TTS tag removal linear without changing malformed-tag behavior."""

import subprocess
import sys

import pytest
from flaskr.service.tts import (
    _strip_complete_angle_bracket_tags,
    preprocess_for_tts,
)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("Before <p>words</p> after", "Before words after"),
        ("Before <foo<bar> after", "Before  after"),
        ("a <> b <\n>tag</\n> end", "a  b tag end"),
        ("a < 3 and > b", "a  b"),
        ("a > b < unfinished", "a > b < unfinished"),
        ("a <tag> b <<unfinished", "a  b <<unfinished"),
    ],
)
def test_complete_tag_removal_keeps_existing_delimiter_semantics(
    source: str, expected: str
) -> None:
    assert _strip_complete_angle_bracket_tags(source) == expected


def test_preprocess_preserves_speech_around_malformed_nested_tags() -> None:
    assert preprocess_for_tts("Before <foo<bar> after") == "Before after"


def test_long_unclosed_brackets_finish_within_process_deadline() -> None:
    subprocess.run(
        [
            sys.executable,
            "-c",
            "from flaskr.service.tts import preprocess_for_tts; "
            "source = 'Before ' + '<' * 200000 + ' tail'; "
            "assert preprocess_for_tts(source) == source",
        ],
        check=True,
        timeout=20,
    )
