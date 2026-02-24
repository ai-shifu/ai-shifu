"""
Unit tests for visual boundary detection patterns.

Tests cover all 9 visual content types:
  SVG, Mermaid, Code blocks, Markdown image, HTML img,
  Markdown table, iframe, HTML block, Math (LaTeX + MathML).
"""

from flaskr.service.tts.visual_patterns import (
    find_earliest_complete_visual,
    has_incomplete_visual,
)


# -----------------------------------------------------------------------
# 8.1 — Visual boundary pattern detection (all 9 types)
# -----------------------------------------------------------------------


class TestFindEarliestCompleteVisual:
    """Tests for find_earliest_complete_visual()."""

    # --- SVG ---

    def test_svg_simple(self):
        text = 'Before. <svg width="100"><circle r="5"/></svg> After.'
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "svg"
        assert m.content.startswith("<svg")
        assert m.content.endswith("</svg>")

    def test_svg_multiline(self):
        text = (
            "Text before.\n"
            '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600">\n'
            "  <rect x='0' y='0' width='800' height='600' fill='#f5f5f5'/>\n"
            "  <text x='400' y='300'>Hello</text>\n"
            "</svg>\n"
            "Text after."
        )
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "svg"
        assert "<rect" in m.content
        assert "</svg>" in m.content

    # --- Mermaid ---

    def test_mermaid_block(self):
        text = "Some text\n```mermaid\ngraph TD\n  A-->B\n```\nMore text"
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "mermaid"
        assert "graph TD" in m.content

    # --- Code blocks ---

    def test_code_block_python(self):
        text = "Before:\n```python\nprint('hello')\n```\nAfter."
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "code"
        assert "print('hello')" in m.content

    def test_code_block_bare(self):
        text = "Before:\n```\nsome code\n```\nAfter."
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "code"

    def test_inline_backtick_not_matched(self):
        """Inline `code` should NOT match as a code block."""
        text = "Use `var x = 1` in your code."
        m = find_earliest_complete_visual(text)
        assert m is None

    # --- Markdown image ---

    def test_markdown_image(self):
        text = "See the diagram: ![Architecture](https://example.com/arch.png) below."
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "image"
        assert "arch.png" in m.content

    def test_markdown_image_with_title(self):
        text = '![alt text](url.png "Title") rest'
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "image"

    # --- HTML img ---

    def test_html_img_self_closing(self):
        text = 'Before <img src="photo.jpg" alt="photo" /> After'
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "image"
        assert "photo.jpg" in m.content

    def test_html_img_void(self):
        text = 'Before <img src="photo.jpg"> After'
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "image"

    # --- Markdown table ---

    def test_markdown_table(self):
        text = (
            "Text before\n"
            "| Name | Age |\n"
            "| --- | --- |\n"
            "| Alice | 30 |\n"
            "| Bob | 25 |\n"
            "Text after"
        )
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "table"
        assert "Alice" in m.content
        assert "Bob" in m.content

    def test_markdown_table_with_alignment(self):
        text = "| Left | Center | Right |\n| :--- | :---: | ---: |\n| 1 | 2 | 3 |\n"
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "table"

    # --- iframe ---

    def test_iframe_bilibili(self):
        text = (
            "Watch this:\n"
            '<iframe src="//player.bilibili.com/player.html?bvid=BV1xx" '
            'width="800" height="450" frameborder="0" allowfullscreen>'
            "</iframe>\n"
            "Done."
        )
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "iframe"
        assert "bilibili" in m.content

    def test_iframe_youtube(self):
        text = (
            '<iframe width="560" height="315" '
            'src="https://www.youtube.com/embed/abc123" '
            'frameborder="0" allowfullscreen></iframe>'
        )
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "iframe"

    # --- HTML block ---

    def test_html_div(self):
        text = "Before\n<div class='custom'>Content here</div>\nAfter"
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "html"
        assert "Content here" in m.content

    def test_html_figure(self):
        text = "<figure><img src='x.png'/><figcaption>Caption</figcaption></figure>"
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "html"

    def test_html_details(self):
        text = "<details><summary>Click</summary>Hidden content</details>"
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "html"

    def test_html_blockquote(self):
        text = "<blockquote>A wise quote</blockquote>"
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "html"

    # --- Math (LaTeX display) ---

    def test_latex_display_math(self):
        text = "The formula is $$E = mc^2$$ which is famous."
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "math"
        assert "E = mc^2" in m.content

    def test_latex_display_math_multiline(self):
        text = "Formula:\n$$\n\\int_0^1 f(x) dx\n$$\nEnd."
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "math"
        assert "\\int" in m.content

    # --- Math (MathML) ---

    def test_mathml_tag(self):
        text = "Result: <math><mi>x</mi><mo>=</mo><mn>5</mn></math> done."
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "math"
        assert "<mi>x</mi>" in m.content

    # --- No match ---

    def test_plain_text_no_match(self):
        text = "This is just plain text with no visual elements."
        m = find_earliest_complete_visual(text)
        assert m is None

    def test_empty_string(self):
        m = find_earliest_complete_visual("")
        assert m is None

    def test_none_like_empty(self):
        m = find_earliest_complete_visual("")
        assert m is None


# -----------------------------------------------------------------------
# 8.2 — Priority, multiple patterns, earliest match
# -----------------------------------------------------------------------


class TestEarliestMatch:
    """Test that find_earliest_complete_visual returns the EARLIEST match."""

    def test_svg_before_image(self):
        text = "<svg><circle/></svg> then ![img](url.png)"
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "svg"

    def test_image_before_table(self):
        text = "![img](url.png) and then\n| H |\n| --- |\n| V |\n"
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "image"

    def test_code_before_math(self):
        text = "```python\nx=1\n```\nthen $$y=2$$"
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "code"

    def test_math_before_code(self):
        text = "$$y=2$$ then\n```python\nx=1\n```"
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "math"

    def test_mermaid_vs_code(self):
        """Mermaid block should be detected as 'mermaid', not generic 'code'."""
        text = "```mermaid\ngraph TD\n  A-->B\n```"
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "mermaid"

    def test_multiple_same_type_returns_first(self):
        text = "![a](1.png) and ![b](2.png)"
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert "1.png" in m.content

    def test_match_offsets_correct(self):
        text = "ABC![img](url.png)DEF"
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.start == 3
        assert text[m.start : m.end] == "![img](url.png)"


# -----------------------------------------------------------------------
# 8.2 — has_incomplete_visual
# -----------------------------------------------------------------------


class TestHasIncompleteVisual:
    """Tests for has_incomplete_visual()."""

    def test_incomplete_svg(self):
        assert has_incomplete_visual("<svg width='100'>circle") is True

    def test_complete_svg(self):
        assert has_incomplete_visual("<svg><circle/></svg>") is False

    def test_incomplete_iframe(self):
        assert has_incomplete_visual('<iframe src="x">content') is True

    def test_complete_iframe(self):
        assert has_incomplete_visual("<iframe>x</iframe>") is False

    def test_incomplete_fenced_code(self):
        assert has_incomplete_visual("```python\nprint('hi')") is True

    def test_complete_fenced_code(self):
        assert has_incomplete_visual("```python\nprint('hi')\n```") is False

    def test_incomplete_latex_math(self):
        assert has_incomplete_visual("$$E = mc^2") is True

    def test_complete_latex_math(self):
        assert has_incomplete_visual("$$E = mc^2$$") is False

    def test_incomplete_math_tag(self):
        assert has_incomplete_visual("<math><mi>x</mi>") is True

    def test_incomplete_div(self):
        assert has_incomplete_visual("<div>content") is True

    def test_incomplete_blockquote(self):
        assert has_incomplete_visual("<blockquote>quote") is True

    def test_incomplete_table_header_only(self):
        """A table header row without separator should be incomplete."""
        assert has_incomplete_visual("| Name | Age |") is True

    def test_complete_table(self):
        text = "| Name | Age |\n| --- | --- |\n| Alice | 30 |"
        assert has_incomplete_visual(text) is False

    def test_plain_text(self):
        assert has_incomplete_visual("Just plain text.") is False

    def test_empty_string(self):
        assert has_incomplete_visual("") is False

    def test_mixed_complete_and_incomplete(self):
        """If any visual is incomplete, return True."""
        text = "<svg><circle/></svg> then <div>open"
        assert has_incomplete_visual(text) is True


# -----------------------------------------------------------------------
# Edge cases
# -----------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases for visual pattern detection."""

    def test_nested_svg_matches_outer(self):
        """Nested SVG: should match the outer (greedy to first </svg>)."""
        text = "<svg><svg><circle/></svg></svg>"
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "svg"

    def test_adjacent_visuals(self):
        """Two adjacent visuals: first one should be returned."""
        text = "![a](1.png)![b](2.png)"
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert "1.png" in m.content
        assert m.end <= len(text)

    def test_visual_at_start(self):
        text = "![img](url.png) trailing text"
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.start == 0

    def test_visual_at_end(self):
        text = "leading text ![img](url.png)"
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.end == len(text)

    def test_case_insensitive_svg(self):
        text = "<SVG><circle/></SVG>"
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "svg"

    def test_case_insensitive_iframe(self):
        text = "<IFRAME src='x'></IFRAME>"
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "iframe"

    def test_table_content_excludes_leading_newline(self):
        """Table match content should start with '|', not a newline."""
        text = "\n| H |\n| --- |\n| V |\n"
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "table"
        assert m.content.startswith("|")

    def test_html_img_with_many_attrs(self):
        text = '<img src="x.png" alt="x" width="100" height="100" loading="lazy" />'
        m = find_earliest_complete_visual(text)
        assert m is not None
        assert m.visual_type == "image"

    def test_latex_inline_dollar_not_matched(self):
        """Single $ should NOT match as display math."""
        text = "Price is $5 and $10."
        m = find_earliest_complete_visual(text)
        assert m is None

    def test_consecutive_visuals_can_be_iterated(self):
        """After consuming the first match, the remainder yields the second."""
        text = "![a](1.png) text ![b](2.png)"
        m1 = find_earliest_complete_visual(text)
        assert m1 is not None
        remainder = text[m1.end :]
        m2 = find_earliest_complete_visual(remainder)
        assert m2 is not None
        assert "2.png" in m2.content
