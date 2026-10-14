"""Nested Markdown containers preserve examples without exposing author notes."""

import importlib

import pytest
from flaskr.service.learn.agent.engine.script import (
    ScriptBundle,
    collected_names,
    detect_v1_syntax,
    render_first_prompt,
    substitution_names,
)
from flaskr.service.learn.agent.engine.script_code_blocks import build_code_block_index
from flaskr.service.learn.agent.engine.script_comments import strip_comments


@pytest.mark.parametrize("marker", ["~~~", "```"])
@pytest.mark.parametrize(
    ("opening", "continuation"),
    [
        ("> ", "> "),
        ("> > ", "> > "),
        ("- ", "  "),
        ("1. ", "   "),
        ("- Topic\n\n    ", "    "),
        ("> - ", ">   "),
        ("- > ", "  > "),
    ],
)
def test_container_fences_keep_comments_as_code_examples(
    marker: str, opening: str, continuation: str
) -> None:
    source = (
        f"{opening}{marker}html\n"
        f"{continuation}<!-- literal example -->\n"
        f"{continuation}{marker}\n"
        f"{continuation}<!-- private note -->"
    )
    assert strip_comments(source) == source.removesuffix("<!-- private note -->")


@pytest.mark.parametrize("linebreak", ["\n", "\r\n", "\r"])
def test_code_block_offsets_refer_to_the_original_physical_lines(
    linebreak: str,
) -> None:
    prefix = "Intro." + linebreak + linebreak
    code = linebreak.join(["> ~~~html", "> <!-- literal -->", "> ~~~", ""])
    source = prefix + code + "<!-- private -->"
    assert build_code_block_index(source) == {len(prefix): len(prefix + code)}
    assert strip_comments(source) == prefix + code


def test_fence_hidden_inside_a_comment_does_not_activate_its_later_lines() -> None:
    source = "Intro <!--\n~~~\n-->\n<!-- private note -->\n~~~"
    assert strip_comments(source) == "Intro \n\n\n\n~~~"


@pytest.mark.parametrize("container", ["> ", "> > ", "- "])
def test_leaving_a_container_ends_an_unclosed_fenced_example(container: str) -> None:
    continuation = "  " if container == "- " else container
    source = (
        f"{container}~~~html\n{continuation}<!-- literal -->\n<!-- private note -->"
    )
    assert strip_comments(source) == source.removesuffix("<!-- private note -->")


@pytest.mark.parametrize("container", ["> ", "> > ", "- "])
def test_prefixed_author_notes_are_removed_outside_code(container: str) -> None:
    source = f"{container}Topic\n{container}<!-- private note -->"
    assert strip_comments(source) == source.removesuffix("<!-- private note -->")


def test_indented_code_and_paragraph_continuation_inside_a_quote() -> None:
    source = (
        "> Topic\n>     <!-- private note -->\n>\n"
        ">     <!-- literal example -->\n"
        "<!-- another private note -->"
    )
    assert strip_comments(source) == source.replace(
        "<!-- private note -->", ""
    ).removesuffix("<!-- another private note -->")


@pytest.mark.parametrize(
    ("opening", "closing"),
    [
        ("<script>", "</script>"),
        ("<!-- author note", "-->"),
        ("<?instruction", "?>"),
        ("<!DECLARATION", ">"),
        ("<![CDATA[", "]]>"),
        ("<div>", "</div>"),
        ('<custom title="value">', "</custom>"),
        ("</custom>", ""),
    ],
)
def test_raw_html_blocks_do_not_turn_their_text_into_markdown_code(
    opening: str, closing: str
) -> None:
    source = f"{opening}\n~~~html\nExample text\n~~~\n{closing}\n\n"
    code = "~~~html\n<!-- literal example -->\n~~~"
    assert build_code_block_index(source + code) == {len(source): len(source + code)}


def test_code_block_parser_never_evaluates_the_unsafe_html_tag_regex(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("markdown_it.rules_block.html_block")

    class ForbiddenRegex:
        def search(self, _text: str) -> None:
            pytest.fail("The backtracking generic HTML-tag regex was evaluated")

    sequences = list(module.HTML_SEQUENCES)
    sequences[6] = (ForbiddenRegex(), sequences[6][1], False)
    monkeypatch.setattr(module, "HTML_SEQUENCES", sequences)
    malformed = "<A\t:=" + "!\t\t:=" * 10000
    code = "~~~html\n<!-- literal example -->\n~~~"
    for source in ["<div>\n" + code, '<custom title="value">\n' + code, malformed]:
        assert build_code_block_index(source) == {}


@pytest.mark.parametrize("container", ["> ", "  "])
def test_preserved_code_comments_do_not_declare_runtime_variables(
    container: str,
) -> None:
    prefix = "- Topic\n\n" if container == "  " else ""
    source = prefix + (
        f"{container}~~~html\n"
        f"{container}<!-- literal %{{{{example}}}} {{{{secret}}}} -->\n"
        f"{container}~~~\n"
    )
    bundle = ScriptBundle(script=source)
    assert source in render_first_prompt(bundle, {"secret": "Historical learner value"})
    assert collected_names(source) == frozenset()
    assert substitution_names(bundle) == frozenset()
    assert not detect_v1_syntax(source)
    assert collected_names(source + "%{{real}}") == frozenset({"real"})
