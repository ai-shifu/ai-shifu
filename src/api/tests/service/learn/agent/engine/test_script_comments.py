"""Keep author notes out of prompts while preserving lesson code examples."""

import pytest
from flaskr.service.learn.agent.engine.script_comments import strip_comments


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("visible <!-- hidden --> tail", "visible  tail"),
        ("a<!-- first --><!-- second -->b", "ab"),
        ("before <!-- hidden\nmore --> after", "before \n after"),
        ("before <!-- hidden\r\nmore --> after", "before \r\n after"),
        ("before <!-- hidden\nsecret", "before \n"),
        ("<!-- hidden\n---\n?[No]\n-->", "\n\n\n"),
        ("<!-- hidden -->\n---\nvisible", "\n---\nvisible"),
        ("`<!-- literal -->` <!-- hidden -->", "`<!-- literal -->` "),
        ("`` `<!-- literal -->` ``", "`` `<!-- literal -->` ``"),
        ("`<!-- literal\nexample -->`", "`<!-- literal\nexample -->`"),
        ("`unclosed <!-- hidden -->", "`unclosed "),
        ("`unclosed\n\n<!-- hidden -->`", "`unclosed\n\n`"),
        (r"\<!-- literal --> <!-- hidden -->", r"\<!-- literal --> "),
        (r"\\<!-- hidden -->", r"\\"),
    ],
)
def test_removes_comments_without_losing_visible_text(
    source: str, expected: str
) -> None:
    assert strip_comments(source) == expected


@pytest.mark.parametrize("marker", ["```", "~~~~"])
@pytest.mark.parametrize("indent", ["", "   "])
def test_fenced_comments_are_literal_examples(marker: str, indent: str) -> None:
    source = (
        f"{indent}{marker}html\n"
        "<!-- literal example -->\n"
        f"{indent}{marker}\n"
        "<!-- hidden -->visible"
    )
    assert strip_comments(source) == source.replace("<!-- hidden -->", "")


def test_shorter_and_nonmatching_fences_do_not_expose_code_comments() -> None:
    source = (
        "````html\n```\n~~~\n<!-- literal example -->\n"
        "```` trailing text\n<!-- also literal -->\n````\n<!-- hidden -->"
    )
    assert strip_comments(source) == source.removesuffix("<!-- hidden -->")


def test_commented_fences_do_not_start_code_blocks() -> None:
    source = "<!--\n```\n-->\nvisible <!-- hidden -->"
    assert strip_comments(source) == "\n\n\nvisible "


@pytest.mark.parametrize("indent", ["    ", "\t", " \t"])
def test_indented_comments_are_literal_code_examples(indent: str) -> None:
    source = f"{indent}<!-- literal example -->\n\nvisible <!-- hidden -->"
    assert strip_comments(source) == source.removesuffix("<!-- hidden -->")
