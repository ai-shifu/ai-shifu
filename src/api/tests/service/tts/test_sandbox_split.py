from flaskr.service.tts.sandbox_split import split_text_by_sandbox_boundaries


def test_split_text_by_sandbox_boundaries_splits_on_common_sandbox_blocks():
    text = (
        "Intro.\n\n"
        '<svg width="800" height="600" xmlns="http://www.w3.org/2000/svg">'
        "<text>Hello</text>"
        "</svg>\n\n"
        "After svg.\n\n"
        "```mermaid\n"
        "graph TD;\n"
        "A-->B;\n"
        "```\n\n"
        "After mermaid.\n\n"
        "![alt](https://example.com/x.png)\n\n"
        "After md image.\n\n"
        '<img src="https://example.com/y.png" />\n\n'
        "After html img.\n\n"
        '<iframe data-tag="video" src="https://example.com"></iframe>\n\n'
        "After iframe."
    )

    parts = split_text_by_sandbox_boundaries(text)

    assert any("Intro." in p for p in parts)
    assert any("After svg." in p for p in parts)
    assert any("After mermaid." in p for p in parts)
    assert any("After md image." in p for p in parts)
    assert any("After html img." in p for p in parts)
    assert any("After iframe." in p for p in parts)

    joined = "\n".join(parts).lower()
    assert "<svg" not in joined
    assert "```mermaid" not in joined
    assert "![" not in joined
    assert "<img" not in joined
    assert "<iframe" not in joined


def test_split_text_by_sandbox_boundaries_unescapes_html_entities():
    text = "Before &amp;lt;svg&amp;gt;X&amp;lt;/svg&amp;gt; After"
    parts = split_text_by_sandbox_boundaries(text)

    assert len(parts) == 2
    assert parts[0].strip() == "Before"
    assert parts[1].strip() == "After"
