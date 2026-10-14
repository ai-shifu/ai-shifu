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


@pytest.mark.parametrize("indent", ["    ", "\t", " \t"])
@pytest.mark.parametrize("intro", ["Topic", "- Topic", "1. Topic", "10. Topic"])
def test_indented_paragraph_and_list_notes_are_comments(
    intro: str, indent: str
) -> None:
    source = f"{intro}\n{indent}<!-- private note -->\n{indent}Explain the topic"
    assert strip_comments(source) == source.replace("<!-- private note -->", "")


@pytest.mark.parametrize(
    "intro", ["- Topic", "1. Topic", "10. Topic", "1. First\n2. Topic"]
)
@pytest.mark.parametrize("indent", ["    ", "\t"])
def test_blank_lines_do_not_turn_list_notes_into_code(intro: str, indent: str) -> None:
    source = f"{intro}\n\n{indent}<!-- private note -->\n{indent}Explain the topic"
    assert strip_comments(source) == source.replace("<!-- private note -->", "")


def test_nested_list_notes_use_their_container_indentation() -> None:
    source = (
        "- Topic\n    - Detail\n\n        <!-- private note -->\n"
        "        Explain the detail\n\n          <!-- literal code -->"
    )
    assert strip_comments(source) == source.replace("<!-- private note -->", "")


def test_consecutive_indented_paragraph_notes_are_removed() -> None:
    source = "Topic\n    <!-- private note -->\n    <!-- another private note -->"
    assert strip_comments(source) == "Topic\n    \n    "


@pytest.mark.parametrize(
    ("intro", "indent"), [("- Topic", "      "), ("1. Topic", "       ")]
)
def test_list_code_examples_need_indentation_beyond_the_list(
    intro: str, indent: str
) -> None:
    source = f"{intro}\n\n{indent}<!-- literal code -->\n\nvisible <!-- hidden -->"
    assert strip_comments(source) == source.removesuffix("<!-- hidden -->")


def test_indented_code_can_follow_a_heading_and_outlive_blank_lines() -> None:
    source = "# Example\n    <!-- literal code -->\n\n    <!-- also literal -->"
    assert strip_comments(source) == source


def test_new_sibling_list_item_ends_an_indented_code_example() -> None:
    source = (
        "- Topic\n\n      <!-- literal code -->\n"
        "- Next topic\n    <!-- private note -->\n    Explain the next topic"
    )
    assert strip_comments(source) == source.replace("<!-- private note -->", "")


@pytest.mark.parametrize("intro", ["- - -", "* * *", "Paragraph\n2. Still a paragraph"])
def test_non_list_blocks_do_not_change_the_indented_code_margin(intro: str) -> None:
    source = f"{intro}\n\n    <!-- literal code -->"
    assert strip_comments(source) == source


@pytest.mark.parametrize("marker", ["-", "1."])
def test_list_items_can_start_with_an_indented_code_example(marker: str) -> None:
    source = f"{marker}     <!-- literal code -->\n\nvisible <!-- hidden -->"
    assert strip_comments(source) == source.removesuffix("<!-- hidden -->")
