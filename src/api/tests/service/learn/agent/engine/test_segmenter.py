"""Listen-mode segmenter: splitting a stream into visuals and narration."""

from flaskr.service.learn.agent.engine import Narration, Segmenter, SegmentPiece, Visual


def run(text: str, chunk: int = 7) -> list[SegmentPiece]:
    seg = Segmenter()
    out = []
    for i in range(0, len(text), chunk):
        out.extend(seg.feed(text[i : i + chunk]))
    out.extend(seg.finish())
    return out


def kinds(pieces: list[SegmentPiece]) -> list[str]:
    return [
        p.kind if isinstance(p, Visual) else "N"
        for p in pieces
        if not (isinstance(p, Narration) and not p.text.strip())
    ]


def test_nested_html_is_one_visual_with_following_style() -> None:
    text = (
        '<div class="s">\n  <div>inner</div>\n  <div><div>deep</div></div>\n</div>\n'
        "<style>.s{color:red}</style>\n\nNarration line one.\n"
    )
    pieces = run(text)
    assert kinds(pieces) == ["html", "N"]
    v = pieces[0]
    assert v.content.startswith("<div")
    assert v.content.rstrip().endswith("</style>")


def test_visual_then_narration_then_visual() -> None:
    text = "<div>a</div>\nsay a\n\n<div>b</div>\nsay b\n"
    assert kinds(run(text)) == ["html", "N", "html", "N"]


def test_fenced_html_and_mermaid_and_code() -> None:
    text = "```html\n<div>x</div>\n```\nnarr\n```mermaid\ngraph TD; A-->B\n```\n```python\nprint(1)\n```\n"
    pieces = [p for p in run(text) if isinstance(p, Visual)]
    assert [p.kind for p in pieces] == ["html", "mermaid", "code"]
    assert pieces[0].content == "<div>x</div>\n"  # fence stripped
    assert pieces[2].language == "python"
    assert pieces[2].content.startswith("```python")


def test_image_and_table() -> None:
    text = "intro\n![alt](http://x/y.png)\n| a | b |\n|---|---|\n| 1 | 2 |\nafter\n"
    assert kinds(run(text)) == ["N", "image", "table", "N"]


def test_narration_streams_per_line_and_partial_tail() -> None:
    seg = Segmenter()
    got = list(seg.feed("line one\nline tw"))
    assert [p.text for p in got] == ["line one\n"]
    got += list(seg.finish())
    assert got[-1].text == "line tw"


def test_unterminated_html_flushes_on_finish() -> None:
    pieces = run("<div>\n<p>never closed\n")
    assert kinds(pieces) == ["html"]


def test_self_closing_and_void_tags_do_not_confuse_depth() -> None:
    text = "<div>\n<img src=x/>\n<br>\n<div/>\n</div>\ndone\n"
    assert kinds(run(text)) == ["html", "N"]


def test_unterminated_style_after_html_is_kept_on_finish() -> None:
    pieces = run("<div>a</div>\n<style>.a{color:red}\n")
    assert kinds(pieces) == ["html"]
    assert "<style>" in pieces[0].content


def test_style_closed_on_same_line() -> None:
    pieces = run("<div>a</div>\n<style>.a{}</style>\nnarr\n")
    assert kinds(pieces) == ["html", "N"]
    assert pieces[0].content.rstrip().endswith("</style>")


def test_html_only_then_end() -> None:
    pieces = run("<div>\n<div>x</div>\n</div>\n")
    assert kinds(pieces) == ["html"]


def test_narration_is_plain_text() -> None:
    from flaskr.service.learn.agent.engine.segmenter import plain_narration

    assert (
        plain_narration("## Token 是**大模型**眼里的 `文字` 单位\n")
        == "Token 是大模型眼里的 文字 单位\n"
    )
    assert (
        plain_narration("- 第一点 *强调* 和 [链接](http://x)") == "第一点 强调 和 链接"
    )
    assert plain_narration("> 引用 __粗__ ~~删~~") == "引用 粗 删"
    assert plain_narration("2 * 3 = 6 and a_b_c") == "2 * 3 = 6 and a_b_c"
    pieces = run("**重点**：先说结论。\n")
    assert isinstance(pieces[0], Narration)
    assert pieces[0].text == "重点：先说结论。\n"


def test_style_and_script_blocks_attach_to_the_visual() -> None:
    text = "<div>a</div>\n<style>.a{}</style>\n<script>gsap.to('.a',{x:1})</script>\nnarr\n"
    pieces = run(text)
    assert kinds(pieces) == ["html", "N"]
    assert "<script>" in pieces[0].content
    assert pieces[0].content.rstrip().endswith("</script>")


def test_an_unterminated_fence_keeps_its_last_line() -> None:
    """The stream ended mid-block, so there is no closing line to strip -- only content."""
    seg = Segmenter()
    out = list(seg.feed("```html\n<div>Explanation</div>\n"))
    out += list(seg.finish())
    visuals = [p for p in out if isinstance(p, Visual)]
    assert len(visuals) == 1
    assert "<div>Explanation</div>" in visuals[0].content


def test_a_shorter_fence_does_not_close_a_longer_one() -> None:
    """A ``` line inside a ```` block is content, so the visual must carry it through."""
    seg = Segmenter()
    out = list(seg.feed("````html\n<div>a</div>\n```\n<div>b</div>\n````\n"))
    out += list(seg.finish())
    visuals = [p for p in out if isinstance(p, Visual)]
    assert len(visuals) == 1
    assert "<div>a</div>" in visuals[0].content
    assert "<div>b</div>" in visuals[0].content


def test_a_closed_fence_still_drops_its_delimiters() -> None:
    seg = Segmenter()
    out = list(seg.feed("```html\n<div>x</div>\n```\n"))
    out += list(seg.finish())
    visuals = [p for p in out if isinstance(p, Visual)]
    assert len(visuals) == 1
    assert visuals[0].content.strip() == "<div>x</div>"


def test_an_indented_marker_does_not_close_a_visual_fence() -> None:
    seg = Segmenter()
    out = list(seg.feed("```html\n<div>a</div>\n    ```\n<div>b</div>\n```\n"))
    out += list(seg.finish())
    visuals = [p for p in out if isinstance(p, Visual)]
    assert len(visuals) == 1
    assert "<div>a</div>" in visuals[0].content
    assert "<div>b</div>" in visuals[0].content
