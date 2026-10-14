"""Authored note filtering preserves native legacy source positions."""

import pytest
from flaskr.service.learn.legacy_block_positions import project_legacy_block_positions
from markdown_flow import MarkdownFlow


@pytest.mark.parametrize("linebreak", ["\n", "\r\n"])
def test_duplicate_questions_keep_their_original_positions(linebreak: str) -> None:
    document = (
        "<!--\nprivate note\n-->\n---\n?[Continue]\n---\n?[Continue]\n---\nEnd."
    ).replace("\n", linebreak)
    original = MarkdownFlow(document, llm_provider=None)
    before = [(block.content, block.index) for block in original.get_all_blocks()]

    public, execution, _code = project_legacy_block_positions(original)

    assert [block.index for block in public] == list(range(len(before)))
    assert [block.content for block in public] == [
        "",
        "?[Continue]",
        "?[Continue]",
        "End.",
    ]
    assert [block.index for block in execution] == [block.index for block in public]
    assert [
        (block.content, block.index) for block in original.get_all_blocks()
    ] == before


def test_cr_only_source_keeps_the_native_library_separator_contract() -> None:
    original = MarkdownFlow(
        "<!--\rprivate\r-->\r---\r?[Continue]\r---\rEnd.", llm_provider=None
    )
    public, _execution, _code = project_legacy_block_positions(original)
    assert len(public) == len(original.get_all_blocks())
    assert [block.index for block in public] == list(range(len(public)))
    assert "private" not in "".join(block.content for block in public)
    assert public[0].content == "---"


def test_unclosed_note_removes_all_subsequent_slots_globally() -> None:
    original = MarkdownFlow(
        "Visible.\n---\n<!-- unclosed note\n---\nVisible.\n?[Hidden]\n---\nTail.",
        llm_provider=None,
    )
    public, execution, _code = project_legacy_block_positions(original)
    assert [block.content for block in public] == ["Visible.", "", "", "", ""]
    assert [block.content for block in execution] == ["Visible.", "", "", "", ""]


def test_note_interaction_cannot_merge_or_reassign_visible_slots() -> None:
    original = MarkdownFlow(
        "before <!-- first --> <!-- second ?[%{{hidden}} Hidden] --> after",
        llm_provider=None,
    )
    public, _execution, _code = project_legacy_block_positions(original)
    assert [(block.index, block.content) for block in public] == [
        (0, "before"),
        (1, ""),
        (2, "after"),
    ]


def test_code_source_is_public_but_protected_from_private_substitution() -> None:
    original = MarkdownFlow(
        "Teach {{name}}.\n```html\n{{name}} <!-- literal -->\n```\n<!-- private -->",
        llm_provider=None,
    )
    public, execution, code = project_legacy_block_positions(original)
    assert public[0].content == (
        "Teach {{name}}.\n```html\n{{name}} <!-- literal -->\n```"
    )
    assert "private" not in execution[0].content
    assert "literal" not in execution[0].content
    assert list(code.values()) == ["```html\n{{name}} <!-- literal -->\n```"]


def test_closed_comment_prefix_and_suffix_stay_in_the_original_content_slot() -> None:
    original = MarkdownFlow(
        "prefix <!-- private\n--> ?[A]\n---\n?[B]", llm_provider=None
    )
    public, _execution, _code = project_legacy_block_positions(original)
    assert [(block.index, block.content) for block in public] == [
        (0, "prefix \n ?[A]"),
        (1, "?[B]"),
    ]


def test_native_inline_deletion_cannot_repair_a_backtick_and_expose_a_note() -> None:
    document = "`literal <!-- first ` comment --> <!-- private --> `"
    original = MarkdownFlow(document, llm_provider=None)
    assert original.get_block(0).content == "`literal  <!-- private --> `"
    public, execution, _code = project_legacy_block_positions(original)
    assert public[0].content == "`literal <!-- first ` comment -->  `"
    assert execution[0].content == public[0].content
    assert "private" not in public[0].content


def test_restored_code_examples_do_not_declare_public_variables() -> None:
    original = MarkdownFlow(
        "Teach {{actual}}.\n```text\n{{example}} %{{answer}}\n```\n<!-- private -->",
        llm_provider=None,
    )
    public, execution, _code = project_legacy_block_positions(original)
    assert public[0].variables == execution[0].variables == ["actual"]
    assert "{{example}}" in public[0].content


def test_duplicate_deleted_and_retained_native_lines_keep_exact_provenance() -> None:
    original = MarkdownFlow("<!-- x -->\n<!-- a --><!-- x -->\n?[A]", llm_provider=None)
    assert original.get_processed_document() == "<!-- x -->\n?[A]"
    public, _execution, _code = project_legacy_block_positions(original)
    assert [(block.index, block.content) for block in public] == [(0, ""), (1, "?[A]")]
