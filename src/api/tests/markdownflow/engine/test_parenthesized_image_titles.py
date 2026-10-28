"""Parenthesized image titles reject unescaped opening parentheses."""

import pytest
from markdown_it import MarkdownIt
from markdownflow.engine import (
    ScriptBundle,
    collected_names,
    render_first_prompt,
    substitute_variables,
)
from markdownflow.engine.marker_context import analyze_marker_context
from markdownflow.engine.tools import script_options


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("spelling", ["{{goal}}", "%{{goal}}"])
@pytest.mark.parametrize("angle", [False, True])
@pytest.mark.parametrize("form", ["inline", "reference", "reference-next-line"])
@pytest.mark.parametrize(
    ("opening", "continuation"),
    [("", ""), ("> ", "> "), ("> - ", ">   "), ("- > ", "  > ")],
)
@pytest.mark.parametrize(
    "title",
    [
        "(Diagram (draft)",
        "(Diagram (draft))",
        "(Diagram (draft)))",
        r"(Diagram \(draft)",
        r"(Diagram \(draft\))",
        r"(Diagram \\(draft))",
        r"(Diagram \\\(draft\))",
        '"Diagram (draft)"',
        "'Diagram (draft)'",
        "(Diagram &lpar;draft&rpar;)",
        "(Diagram &#40;draft&#41;)",
        "(Diagram &#x28;draft&#x29;)",
        "(Diagram\n(draft))",
        "(Diagram\n\\(draft\\))",
        '"Diagram\n(draft)"',
        "(Diagram (draft)\ntext)",
        "(Diagram\n&lpar;draft&rpar;)",
    ],
)
def test_parenthesized_image_titles_follow_renderer_grammar(
    title: str,
    opening: str,
    continuation: str,
    form: str,
    angle: bool,
    spelling: str,
    newline: str,
) -> None:
    """Escapes and quoted/entity parentheses stay valid across native containers."""
    destination = "</x>" if angle else "/x"
    title = title.replace("\n", "\n" + continuation)
    control = f"?[{spelling} A | B]"
    if form == "inline":
        source = f"{opening}![{control}]({destination} {title})"
    else:
        separator = "\n" + continuation if form == "reference-next-line" else " "
        source = (
            f"{opening}![{control}][image]\n{continuation}\n"
            f"{continuation}[image]: {destination}{separator}{title}"
        )
    source = source.replace("\n", newline)
    image = "<img " in MarkdownIt().render(source)
    expected_names = (
        frozenset({"goal"}) if spelling.startswith("%") or not image else frozenset()
    )
    assert collected_names(source) == expected_names
    assert script_options(source) == ({} if image else {"A": "A", "B": "B"})


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_invalid_later_reference_title_preserves_url_and_following_question(
    newline: str,
) -> None:
    source = (
        "![?[{{goal}} A | B]][image]\n\n[image]: /x\n"
        "(Diagram (draft ?[{{visible}} C | D])"
    ).replace("\n", newline)
    assert "<img " in MarkdownIt().render(source)
    assert collected_names(source) == frozenset({"visible"})
    assert script_options(source) == {"C": "C", "D": "D"}
    assert '"current"' in render_first_prompt(
        ScriptBundle(script=source), {"goal": "current"}
    )


@pytest.mark.parametrize("form", ["inline", "reference"])
def test_rejected_same_line_titles_keep_the_named_answer_fresh(form: str) -> None:
    source = (
        "![?[{{goal}} A | B]](/x (Diagram (draft))"
        if form == "inline"
        else "![?[{{goal}} A | B]][image]\n\n[image]: /x (Diagram (draft)"
    )
    assert "<img " not in MarkdownIt().render(source)
    assert collected_names(source) == frozenset({"goal"})
    assert "stale" not in render_first_prompt(
        ScriptBundle(script=source), {"goal": "stale"}
    )
    assert "{{goal}}" in substitute_variables(source, {"goal": "stale"})


@pytest.mark.parametrize("image", [False, True])
@pytest.mark.parametrize("destination", ["/x", "</x>"])
def test_title_image_validation_preserves_generic_resource_literal_spans(
    image: bool, destination: str
) -> None:
    """The historical opaque-resource guard remains separate from image admission."""
    prefix = ("!" if image else "") + f"[example]({destination} (Diagram ({{{{))"
    source = prefix + "\n\n?[{{visible}} C | D]\n\nRead {{value}}."
    assert (prefix.index("("), len(prefix)) in analyze_marker_context(source).literals
    assert collected_names(source) == frozenset({"visible"})
    assert script_options(source) == {"C": "C", "D": "D"}
    assert substitute_variables(source, {"value": "current"}).endswith("Read current.")
