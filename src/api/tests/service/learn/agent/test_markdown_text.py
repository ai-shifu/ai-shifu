"""Exercise only classified Markdown prose; opaque elements belong to the caller."""

from __future__ import annotations

import pytest
from flaskr.service.learn.agent.markdown_text import (
    analyze_markdown_text,
    clean_markdown_text,
)

CASES = [
    ("===hello===", "hello"),
    ("before\n!===\nlesson\n!===\nafter", "before\nlesson\nafter"),
    ("\t!===\r\nlesson\r\n    !===", "lesson\r\n"),
    ("===Use=== `a === b`.", "Use `a === b`."),
    ("Use ``a ` === b`` ===after===", "Use ``a ` === b`` after"),
    ("Use `a\n===inside===` ===after===", "Use `a\n===inside===` after"),
    ("Use `a\n!===\nb` ===after===", "Use `a\n!===\nb` after"),
    ("Press ` then ===after===", "Press ` then after"),
    ("# ===Heading=== `a === b`", "# Heading `a === b`"),
    ("- ===Item=== `a === b`", "- Item `a === b`"),
    ("> ===Quote=== `a === b`", "> Quote `a === b`"),
    (">\t===Quote=== `a === b`", ">\tQuote `a === b`"),
    ("- > ===Item=== `a === b`", "- > Item `a === b`"),
    ("[===label===](/x?q===1)", "[label](/x?q===1)"),
    ('[===label===](</x===y> "===title===")', '[label](</x===y> "===title===")'),
    (
        '[label](/x "line\n===title===") ===after===',
        '[label](/x "line\n===title===") after',
    ),
    ("[label](/bad ===prose===", "[label](/bad prose"),
    ("![===alt===](/x?q===1)", "![alt](/x?q===1)"),
    ("![`a === b` ===alt===](/x===y)", "![`a === b` alt](/x===y)"),
    ("[![===alt===](/x===y)](/z===q)", "[![alt](/x===y)](/z===q)"),
    ("<https://example.com/x===y> ===after===", "<https://example.com/x===y> after"),
    ("<xmpp:room===one> ===after===", "<xmpp:room===one> after"),
    (
        'Use <span title="===attr===">===text===</span>',
        'Use <span title="===attr===">text</span>',
    ),
    (
        'Use <span title="first\n\n===attr==="> ===after===',
        'Use <span title="first\n\nattr"> after',
    ),
    (
        "Use <!-- first\n\n===hidden=== --> ===after===",
        "Use <!-- first\n\nhidden --> after",
    ),
    (
        'Explain <span title="unfinished ===after===',
        'Explain <span title="unfinished after',
    ),
    ("<a===b@example.com> ===after===", "<a===b@example.com> after"),
    (
        "[===label===][id===x]\n\n[id===x]: /x===y\n",
        "[label][id===x]\n\n[id===x]: /x===y\n",
    ),
    ("[id===x]\n\n[id===x]: /x===y\n", "[id===x]\n\n[id===x]: /x===y\n"),
    ("[id===x][]\n\n[id===x]: /x===y\n", "[id===x][]\n\n[id===x]: /x===y\n"),
    (
        '[id]: /x===y "===title==="\n\n===after===',
        '[id]: /x===y "===title==="\n\nafter',
    ),
    (
        '> [===label===][id]\n>\n> [id]: /x===y "===title==="\n',
        '> [label][id]\n>\n> [id]: /x===y "===title==="\n',
    ),
    ("===before===\r\n`a === b`\r\n===after===", "before\r\n`a === b`\r\nafter"),
    ("text\0 `a === b` ===after===", "text\0 `a === b` after"),
    ("text\u2028`a === b` ===after===", "text\u2028`a === b` after"),
    ("===before===\r`a === b`\r===after===", "before\r`a === b`\rafter"),
]


@pytest.mark.parametrize(("source", "expected"), CASES)
def test_classified_prose_cleanup(source: str, expected: str) -> None:
    assert clean_markdown_text(source) == expected


def test_references_can_be_shared_from_prior_pieces() -> None:
    environment = {}
    assert clean_markdown_text("[key]: /x===y\n", environment) == "[key]: /x===y\n"
    assert clean_markdown_text("[===label===][key]", environment) == "[label][key]"


def test_classified_prose_can_mix_plain_lines_and_inline_code() -> None:
    source = "===first===\n\nnext `a === b`\n\n===last==="
    assert clean_markdown_text(source) == "first\n\nnext `a === b`\n\nlast"


def test_native_html_attributes_keep_markers_opaque_across_lines() -> None:
    source = 'plain\n\n<span title="start\n===attr==="> ===after==='
    assert (
        clean_markdown_text(source) == 'plain\n\n<span title="start\n===attr==="> after'
    )


@pytest.mark.parametrize("prefix", ["===", "!==="])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_native_definitions_keep_metadata_after_a_leading_mdf_prefix(
    prefix: str, newline: str
) -> None:
    body = f"[id]: /x===y==={newline}{newline}[docs][id]{newline}"
    environment = {}
    assert clean_markdown_text(prefix + body, environment) == body
    assert environment["references"]["ID"]["href"] == "/x===y==="


def test_wrapped_native_definitions_resolve_forward_reference_keys() -> None:
    source = "[===label===][id===x]\n\n===[id===x]: /x===y\n"
    expected = "[label][id===x]\n\n[id===x]: /x===y\n"
    assert clean_markdown_text(source) == expected


@pytest.mark.parametrize(
    "body",
    [
        "===literal",
        "===[id]: /x===y",
        "!===\n[id===x]: /url\nend",
        "===# Heading\n[id===x]: /url\nend",
    ],
)
def test_a_definition_probe_keeps_leading_markers_inside_multiline_code(
    body: str,
) -> None:
    source = f"``\n{body}`` ===after==="
    environment = {}
    assert clean_markdown_text(source, environment) == source.replace(
        "===after===", "after"
    )
    assert not environment.get("references")


@pytest.mark.parametrize(
    ("source", "references", "incomplete"),
    [
        ("[docs](/url===value)\n", False, False),
        ("[docs`literal](/url)\n", False, False),
        ("![alt <span](/image)\n", False, False),
        ("`array[0] === value`\n", False, False),
        ("\\[literal\\] ===after===\n", False, False),
        ("Use <span title='===attr==='>===text===</span>\n", False, False),
        ("<xmpp:room===one>\n", False, False),
        ("[docs][later]\n", True, False),
        ("[later]\n", True, False),
        ("![alt][later]\n", True, False),
        ("`unfinished\n", False, True),
        ("[unfinished\n", False, True),
        ("![unfinished\n", False, True),
        ('Explain <span title="unfinished\n', False, True),
        ("[id]: /url\n", False, True),
        ("[id]: /url\n\n", False, False),
        ('[id]: /url\n "===title==="\n', False, True),
        ('[id]: /url\n "===title==="\n\n', False, False),
        ("===[id]: /url===value\n", False, True),
        ("===[id]: /url===value\n\n[docs][id]\n", False, False),
        ("[docs][id]\n\n[id]: /url\n\n", False, False),
    ],
)
def test_native_analysis_distinguishes_references_from_inline_incompleteness(
    source: str, references: bool, incomplete: bool
) -> None:
    result = analyze_markdown_text(source)
    assert result.content == clean_markdown_text(source)
    assert result.needs_references is references
    assert result.incomplete is incomplete


def test_native_analysis_uses_definitions_from_prior_paragraphs() -> None:
    environment = {}
    definition = analyze_markdown_text("[id]: /url\n\n", environment)
    assert not definition.needs_references
    assert not definition.incomplete
    result = analyze_markdown_text("[===label===][id]\n", environment)
    assert result.content == "[label][id]\n"
    assert not result.needs_references
    assert not result.incomplete
