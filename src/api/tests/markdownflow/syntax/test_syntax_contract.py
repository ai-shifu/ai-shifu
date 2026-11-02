"""Pin the syntax layer to the results of the markdown-flow 0.4.2 package it came from."""

from __future__ import annotations

import pytest
from markdownflow.syntax import (
    InteractionParser,
    MarkdownFlowDocument,
    StreamFormatter,
    find_unescaped,
    replace_variables_in_text,
)

BLOCK_CASES = {
    "separator_splits": (
        "Intro {{name}}\n\n---\n\nSecond block",
        [
            ("Intro {{name}}", "content", 0, ["name"]),
            ("Second block", "content", 1, []),
        ],
        ["name"],
    ),
    "separator_in_code_fence": (
        "```\na\n---\nb\n```\n\n---\n\nAfter",
        [
            ("__MDFLOW_CODE_BLOCK_1__", "content", 0, []),
            ("After", "content", 1, []),
        ],
        [],
    ),
    "interaction_split": (
        "Pick one:\n?[%{{level}} Beginner | Advanced]\nThanks {{level}}",
        [
            ("Pick one:", "content", 0, []),
            ("?[%{{level}} Beginner | Advanced]", "interaction", 1, ["level"]),
            ("Thanks {{level}}", "content", 2, ["level"]),
        ],
        ["level"],
    ),
    "preserved_block": (
        "!===\nKeep this exactly\n!===\n\n---\n\nTeach {{topic}}",
        [
            ("!===\nKeep this exactly\n!===", "preserved_content", 0, []),
            ("Teach {{topic}}", "content", 1, ["topic"]),
        ],
        ["topic"],
    ),
    "variables_ignored_in_code_and_comments": (
        "Use {{real}}\n\n```\n{{in_code}}\n```\n<!-- {{in_comment}} -->",
        [("Use {{real}}\n\n__MDFLOW_CODE_BLOCK_1__", "content", 0, ["real"])],
        ["real"],
    ),
}


@pytest.mark.parametrize("case", BLOCK_CASES.values(), ids=BLOCK_CASES.keys())
def test_document_blocks_and_variables(
    case: tuple[str, list[tuple[str, str, int, list[str]]], list[str]],
) -> None:
    source, blocks, variables = case
    document = MarkdownFlowDocument(source)

    assert [
        (block.content, block.block_type.value, block.index, block.variables)
        for block in document.get_all_blocks()
    ] == blocks
    assert document.block_count == len(blocks)
    assert document.extract_variables() == variables


def _buttons(*labels: str) -> list[dict[str, str]]:
    return [{"display": label, "value": label} for label in labels]


INTERACTION_CASES = {
    "?[%{{level}} Beginner | Advanced]": {
        "type": "buttons_only",
        "variable": "level",
        "buttons": _buttons("Beginner", "Advanced"),
        "is_multi_select": False,
    },
    "?[%{{goals}} Speak || Read || Write]": {
        "type": "buttons_multi_select",
        "variable": "goals",
        "buttons": _buttons("Speak", "Read", "Write"),
        "is_multi_select": True,
    },
    "?[%{{name}}...What is your name?]": {
        "type": "text_only",
        "variable": "name",
        "question": "What is your name?",
        "is_multi_select": False,
    },
    "?[%{{level}} Beginner | Advanced | ...Other]": {
        "type": "buttons_with_text",
        "variable": "level",
        "buttons": _buttons("Beginner", "Advanced"),
        "question": "Other",
        "is_multi_select": False,
    },
    "?[Continue]": {
        "type": "non_assignment_button",
        "buttons": _buttons("Continue"),
        "is_multi_select": False,
    },
    "?[%{{}} A | B]": {"type": None, "error": "Parsing error: Invalid variable name"},
}


@pytest.mark.parametrize(("source", "expected"), INTERACTION_CASES.items())
def test_interaction_parser_results(source: str, expected: dict[str, object]) -> None:
    result = InteractionParser().parse(source)

    kind = result["type"]
    assert {**result, "type": kind.value if kind is not None else None} == expected


def test_variable_replacement_skips_code_and_marks_missing_values() -> None:
    assert (
        replace_variables_in_text(
            "Hi {{name}}, ```{{name}}``` {{missing}}", {"name": "Ada"}
        )
        == 'Hi """Ada""", ```"""Ada"""``` """UNKNOWN"""'
    )


def test_find_unescaped_skips_escaped_delimiters() -> None:
    assert find_unescaped(r"a \| b | c", "|") == 7


def test_stream_formatter_numbers_text_and_code_elements() -> None:
    formatter = StreamFormatter()
    elements = []
    for chunk in ("Hello\n\n```py\nx = 1\n```\n", "Tail"):
        elements.extend(formatter.process(chunk))
    elements.extend(formatter.flush())

    assert [
        (element.type, element.content, element.number) for element in elements
    ] == [
        ("text", "Hello\n\n", 0),
        ("code", "```py\n", 1),
        ("code", "x = 1\n", 1),
        ("code", "```\n", 1),
        ("text", "Tail", 2),
    ]
