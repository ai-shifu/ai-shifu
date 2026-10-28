"""Image eligibility uses the renderer's URL policy without changing literals."""

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
@pytest.mark.parametrize(
    ("opening", "continuation"),
    [("", ""), ("> ", "> "), ("> - ", ">   "), ("- > ", "  > ")],
)
@pytest.mark.parametrize(
    "destination",
    [
        "/x",
        "https://example.com/image.png",
        "//example.com/x",
        "mailto:a@example.com",
        "http://example.com/x",
        "javascript:alert",
        "JaVaScRiPt:alert",
        "java&#x73;cript:alert",
        r"javascript\:alert",
        "&#106;avascript:alert",
        "vbscript:alert",
        "file:///x",
        "data:text/plain,hello",
        "data:image/svg+xml;base64,abc",
        "data:image/png;base64,abc",
        "data:image/gif;base64,abc",
        "data:image/jpeg;base64,abc",
        "data:image/webp;base64,abc",
        "DATA:IMAGE/PNG;base64,abc",
        "java%73cript:alert",
        "javascript&colon;alert",
        "data&colon;image/svg+xml;base64,abc",
        "",
        "urn:asset:image",
    ],
)
def test_only_renderer_eligible_inline_images_hide_alt_controls(
    destination: str,
    opening: str,
    continuation: str,
    angle: bool,
    spelling: str,
    newline: str,
) -> None:
    """Escape/entity normalization and allowed data images match rendering."""
    resource = f"<{destination}>" if angle else destination
    source = (
        f"{opening}![?[{spelling} A | B]](\n{continuation}{resource}\n{continuation})"
    ).replace("\n", newline)
    image = "<img " in MarkdownIt().render(source)
    expected_names = (
        frozenset({"goal"}) if spelling.startswith("%") or not image else frozenset()
    )
    assert collected_names(source) == expected_names
    assert script_options(source) == ({} if image else {"A": "A", "B": "B"})


@pytest.mark.parametrize("angle", [False, True])
@pytest.mark.parametrize(
    "destination",
    ["javascript:alert", "data:image/svg+xml;base64,abc"],
)
def test_rejected_images_keep_their_named_answer_fresh(
    destination: str, angle: bool
) -> None:
    resource = f"<{destination}>" if angle else destination
    source = f"![?[{{{{goal}}}} A | B]]({resource})"
    assert "<img " not in MarkdownIt().render(source)
    assert collected_names(source) == frozenset({"goal"})
    assert "stale" not in render_first_prompt(
        ScriptBundle(script=source), {"goal": "stale"}
    )
    assert "{{goal}}" in substitute_variables(source, {"goal": "stale"})


@pytest.mark.parametrize("image", [False, True])
@pytest.mark.parametrize(
    "resource",
    [
        '(javascript:alert "{{")',
        '(javascript\\:alert "{{")',
        '(data:image/svg+xml;base64,abc "{{")',
        '(<javascript:alert> "{{")',
    ],
)
def test_image_url_policy_does_not_change_generic_resource_literal_spans(
    resource: str, image: bool
) -> None:
    """Rejected destinations still shield opaque examples in completed resources."""
    prefix = ("!" if image else "") + "[example]" + resource
    source = prefix + "\n\n?[{{visible}} C | D]\n\nRead {{value}}."
    context = analyze_marker_context(source)
    assert (prefix.index("("), len(prefix)) in context.literals
    assert collected_names(source) == frozenset({"visible"})
    assert script_options(source) == {"C": "C", "D": "D"}
    assert substitute_variables(source, {"value": "current"}).endswith("Read current.")
