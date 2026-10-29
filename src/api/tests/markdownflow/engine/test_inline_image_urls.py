"""Image syntax owns its alt text before the browser cleans the destination URL."""

from unittest.mock import patch

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
def test_inline_image_syntax_hides_alt_controls_before_url_cleanup(
    destination: str,
    opening: str,
    continuation: str,
    angle: bool,
    spelling: str,
    newline: str,
) -> None:
    """Cleaning an image URL must not turn its alt text into learner controls."""
    resource = f"<{destination}>" if angle else destination
    source = (
        f"{opening}![?[{spelling} A | B]](\n{continuation}{resource}\n{continuation})"
    ).replace("\n", newline)
    renderer = MarkdownIt()
    # Browser Markdown creates image nodes before ReactMarkdown cleans their src.
    with patch.object(renderer, "validateLink", return_value=True):
        image = "<img " in renderer.render(source)
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
def test_sanitized_images_keep_existing_memory_available(
    destination: str, angle: bool
) -> None:
    resource = f"<{destination}>" if angle else destination
    source = f"![?[{{{{goal}}}} A | B]]({resource})"
    assert "<img " not in MarkdownIt().render(source)
    assert collected_names(source) == frozenset()
    assert "current" in render_first_prompt(
        ScriptBundle(script=source), {"goal": "current"}
    )
    assert "{{goal}}" not in substitute_variables(source, {"goal": "current"})
    assert script_options(source + "\n\n?[{{visible}} C | D]") == {"C": "C", "D": "D"}


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
def test_image_url_cleanup_does_not_change_generic_resource_literal_spans(
    resource: str, image: bool
) -> None:
    """Sanitized destinations still shield opaque examples in completed resources."""
    prefix = ("!" if image else "") + "[example]" + resource
    source = prefix + "\n\n?[{{visible}} C | D]\n\nRead {{value}}."
    context = analyze_marker_context(source)
    assert (prefix.index("("), len(prefix)) in context.literals
    assert collected_names(source) == frozenset({"visible"})
    assert script_options(source) == {"C": "C", "D": "D"}
    assert substitute_variables(source, {"value": "current"}).endswith("Read current.")


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("spelling", ["{{goal}}", "%{{goal}}"])
@pytest.mark.parametrize("angle", [False, True])
@pytest.mark.parametrize("definition_first", [False, True])
@pytest.mark.parametrize(
    "destination",
    [
        "data:image/svg+xml;base64,PHN2Zy8+",
        "data:image/png;base64,abc",
        "data:text/plain,hello",
        "javascript:alert",
        "java&#x73;cript:alert",
        r"javascript\:alert",
        "vbscript:alert",
        "file:///x",
        "/x",
    ],
)
def test_reference_images_own_alt_controls_before_url_cleanup(
    destination: str,
    definition_first: bool,
    angle: bool,
    spelling: str,
    newline: str,
) -> None:
    """URL cleanup preserves the reference image and its inactive alt controls."""
    resource = f"<{destination}>" if angle else destination
    image = f"![?[{spelling} A | B]][image]"
    definition = f"[image]: {resource}"
    source = (
        f"{definition}\n\n{image}" if definition_first else f"{image}\n\n{definition}"
    )
    source += "\n\nRead {{goal}}.\n\n?[{{visible}} C | D]"
    source = source.replace("\n", newline)
    renderer = MarkdownIt()
    with patch.object(renderer, "validateLink", return_value=True):
        assert "<img " in renderer.render(source)
    expected = {"visible"} | ({"goal"} if spelling.startswith("%") else set())
    assert collected_names(source) == frozenset(expected)
    assert script_options(source) == {"C": "C", "D": "D"}
    if not spelling.startswith("%"):
        assert "current" in render_first_prompt(
            ScriptBundle(script=source), {"goal": "current"}
        )
        assert "{{goal}}" not in substitute_variables(source, {"goal": "current"})


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("spelling", ["{{goal}}", "%{{goal}}"])
@pytest.mark.parametrize(
    "suffix",
    [
        "(<data:image/svg+xml;\nbase64,abc>)",
        "(data:image/svg+xml;base64,abc\ntrailing)",
        "[image]\n\n[image]: <data:image/svg+xml;\nbase64,abc>",
        "[image]\n\n[image]: data:image/svg+xml;base64,abc trailing",
    ],
)
def test_url_policy_change_does_not_admit_invalid_multiline_destinations(
    suffix: str, spelling: str, newline: str
) -> None:
    """Invalid destination syntax still exposes its visible authored controls."""
    source = (f"![?[{spelling} A | B]]{suffix}").replace("\n", newline)
    renderer = MarkdownIt()
    with patch.object(renderer, "validateLink", return_value=True):
        assert "<img " not in renderer.render(source)
    assert collected_names(source) == frozenset({"goal"})
    assert script_options(source) == {"A": "A", "B": "B"}
    assert "stale" not in render_first_prompt(
        ScriptBundle(script=source), {"goal": "stale"}
    )
