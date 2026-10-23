"""Stream settled raw names without retaining or repeatedly copying their body."""

import pytest
from flaskr.service.learn.agent import interaction_syntax
from flaskr.service.learn.agent.engine import stream_marker_context
from flaskr.service.learn.agent.engine.marker_context import MarkerContext
from flaskr.service.learn.agent.interaction_syntax import InteractionSyntaxFilter

QUESTION = "?[%{{ real }} A|B]"


@pytest.mark.parametrize("length", [1024, 4096, 16384])
def test_genuinely_unfinished_raw_name_emits_with_bounded_work_and_storage(
    length: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    inspected = 0
    original = stream_marker_context.analyze_marker_context

    def counted(source: str, **kwargs: object) -> MarkerContext:
        nonlocal inspected
        inspected += len(source)
        return original(source, **kwargs)

    monkeypatch.setattr(stream_marker_context, "analyze_marker_context", counted)
    monkeypatch.setattr(interaction_syntax, "analyze_marker_context", counted)
    source = "{{" + "x" * length
    syntax = InteractionSyntaxFilter()
    pieces: list[str] = []
    copied_input = 0
    for character in source:
        copied_input += len(syntax._held) + len(character)
        pieces.append(syntax.feed(character))
        assert len(syntax._held) <= 2
        assert len(syntax._context_prefix) <= 128
        assert syntax._pending_literal is None
        assert syntax._pending_literal_chunks == []
    assert "".join(pieces) == source
    assert syntax.flush() == ""
    assert syntax.spans == []
    assert copied_input <= 3 * len(source)
    assert inspected <= 80 * len(source)
    assert syntax.feed(QUESTION) + syntax.flush() == ""
    assert syntax.spans == [QUESTION]


@pytest.mark.parametrize("body", ["`", "$", "~", "?", "{", "}x"])
def test_owned_raw_name_does_not_buffer_native_delimiter_runs(body: str) -> None:
    source = "{{" + body * 2048
    syntax = InteractionSyntaxFilter()
    pieces: list[str] = []
    for character in source:
        pieces.append(syntax.feed(character))
        assert len(syntax._held) <= 2
        assert len(syntax._context_prefix) <= 128
    assert "".join(pieces) + syntax.flush() == source
    assert syntax.spans == []


@pytest.mark.parametrize(
    "body",
    [
        "nested {{?[A|B] end",
        "\n```\n?[A|B]\n``` end",
        "\n<div>\n?[A|B]\n</div> end",
        "`?[A|B]` $?[C|D]$ end",
        "value\\}x end",
    ],
)
@pytest.mark.parametrize("closing", ["", "}}", "}}" + QUESTION])
def test_streamed_raw_name_keeps_opaque_body_and_first_closing_pair(
    body: str, closing: str
) -> None:
    source = "{{" + body + closing
    expected = source.removesuffix(QUESTION) if closing.endswith(QUESTION) else source
    spans = [QUESTION] if closing.endswith(QUESTION) else []
    for chunks in [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]:
        syntax = InteractionSyntaxFilter()
        shown = "".join(syntax.feed(chunk) for chunk in chunks) + syntax.flush()
        assert (shown, syntax.spans) == (expected, spans), chunks


@pytest.mark.parametrize("run", ["`", "``", "$", "$$"])
def test_unfinished_inline_literal_keeps_raw_marker_ownership_provisional(
    run: str,
) -> None:
    inner = "?[A|B]"
    source = "Text " + run + "{{" + inner + " value" + run + " outside"
    expected = source.replace(inner, "")
    for chunks in [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]:
        syntax = InteractionSyntaxFilter()
        shown = "".join(syntax.feed(chunk) for chunk in chunks) + syntax.flush()
        assert (shown, syntax.spans) == (expected, [inner]), chunks


@pytest.mark.parametrize("suffix", ["", "suffix"])
def test_raw_name_closer_can_straddle_chunks_before_a_question(suffix: str) -> None:
    prefix = "{{" + "x" * 4096 + "}"
    syntax = InteractionSyntaxFilter()
    assert syntax.feed(prefix) == prefix
    assert syntax.feed("}" + suffix + QUESTION) + syntax.flush() == "}" + suffix
    assert syntax.spans == [QUESTION]


def test_raw_name_replaces_a_single_brace_that_did_not_close_it() -> None:
    syntax = InteractionSyntaxFilter()
    assert syntax.feed("{{value}") == "{{value}"
    assert syntax.feed("x}") == "x}"
    assert syntax.feed("}" + QUESTION) + syntax.flush() == "}"
    assert syntax.spans == [QUESTION]


@pytest.mark.parametrize(
    "literal",
    ["\n```\n?[A|B]\n```\n", "\n~~~\n?[A|B]\n~~~\n", " `{{` then "],
)
def test_closed_raw_name_restores_native_code_and_fence_boundaries(
    literal: str,
) -> None:
    prefix = "{{value}}" + literal
    source = prefix + QUESTION
    for chunks in [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]:
        syntax = InteractionSyntaxFilter()
        shown = "".join(syntax.feed(chunk) for chunk in chunks) + syntax.flush()
        assert (shown, syntax.spans) == (prefix, [QUESTION]), chunks
