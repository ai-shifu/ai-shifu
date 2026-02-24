"""
Integration tests for visual-aware TTS processing.

These tests verify the full pipeline from raw text input through
VisualAwareTTSOrchestrator, checking that the correct sequence
of AUDIO_COMPLETE and VISUAL_MARKER events is emitted with
proper position tracking.

Tests 8.4–8.7 from the task list:
  8.4  Block with SVG generates multiple positional audio records
  8.5  Block with table + image generates correct positions and markers
  8.6  Block with Bilibili iframe generates correct visual marker
  8.7  Block without visual elements — single audio (backward compatible)
"""

import pytest

from flaskr.service.learn.learn_dtos import (
    GeneratedType,
    RunMarkdownFlowDTO,
    AudioCompleteDTO,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


class FakeProcessor:
    """Lightweight stand-in for StreamingTTSProcessor."""

    def __init__(self, *, position: int = 0, **_kw):
        self._position = position
        self._buffer = ""
        self._segment_index = 0

    def process_chunk(self, chunk: str):
        if chunk:
            self._buffer += chunk
            self._segment_index = 1
        yield from ()

    def finalize(self, *, commit: bool = True):
        if self._segment_index > 0:
            yield RunMarkdownFlowDTO(
                outline_bid="outline-1",
                generated_block_bid="block-1",
                type=GeneratedType.AUDIO_COMPLETE,
                content=AudioCompleteDTO(
                    audio_url=f"https://cdn/audio_{self._position}.mp3",
                    audio_bid=f"audio-{self._position}",
                    duration_ms=1000,
                    position=self._position,
                ),
            )

    def finalize_preview(self):
        if self._segment_index > 0:
            yield RunMarkdownFlowDTO(
                outline_bid="outline-1",
                generated_block_bid="block-1",
                type=GeneratedType.AUDIO_COMPLETE,
                content=AudioCompleteDTO(
                    audio_url="",
                    audio_bid=f"audio-{self._position}",
                    duration_ms=1000,
                    position=self._position,
                ),
            )


def _require_app(app):
    if app is None:
        pytest.skip("App fixture disabled")


def _collect(gen):
    return list(gen)


@pytest.fixture
def orchestrator_factory(app):
    """Create a VisualAwareTTSOrchestrator with mocked child processors."""
    _require_app(app)

    from flaskr.service.tts.visual_aware_tts import VisualAwareTTSOrchestrator

    def _create():
        orch = VisualAwareTTSOrchestrator(
            app=app,
            generated_block_bid="block-1",
            outline_bid="outline-1",
            progress_record_bid="progress-1",
            user_bid="user-1",
            shifu_bid="shifu-1",
            voice_id="voice-1",
        )
        # Replace the real initial processor and monkey-patch factory
        orch._current_processor = FakeProcessor(position=0)
        orch._create_processor = lambda: FakeProcessor(position=orch._position)
        return orch

    return _create


def _summarize(events):
    """Produce a concise summary list of (type, position, extra) tuples."""
    out = []
    for e in events:
        if e.type == GeneratedType.AUDIO_COMPLETE:
            out.append(("AUDIO", e.content.position))
        elif e.type == GeneratedType.VISUAL_MARKER:
            out.append(("VISUAL", e.content.position, e.content.visual_type))
    return out


# ---------------------------------------------------------------------------
# 8.4 — Block with SVG generates multiple positional audio records
# ---------------------------------------------------------------------------


class TestBlockWithSVG:
    """Integration test: block containing an SVG should produce positional audio."""

    def test_text_svg_text_produces_three_events(self, orchestrator_factory):
        orch = orchestrator_factory()

        text = (
            "This is the introduction to the diagram.\n"
            '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600">\n'
            "  <rect x='0' y='0' width='800' height='600' fill='#f5f5f5'/>\n"
            "  <text x='400' y='300'>Architecture</text>\n"
            "</svg>\n"
            "As you can see from the diagram above, the system is modular."
        )

        events = _collect(orch.process_chunk(text))
        events += _collect(orch.finalize())

        summary = _summarize(events)

        # Expected: AUDIO(0), VISUAL(1, svg), AUDIO(2)
        audio_events = [s for s in summary if s[0] == "AUDIO"]
        visual_events = [s for s in summary if s[0] == "VISUAL"]

        assert len(visual_events) == 1
        assert visual_events[0][2] == "svg"

        # At least 2 audio segments (before and after SVG)
        assert len(audio_events) >= 2

        # Positions are monotonically increasing
        all_positions = [s[1] for s in summary]
        assert all_positions == sorted(all_positions)

    def test_svg_with_surrounding_text_has_correct_audio_positions(
        self, orchestrator_factory
    ):
        orch = orchestrator_factory()

        text = "Intro. <svg><circle/></svg> Outro."
        events = _collect(orch.process_chunk(text))
        events += _collect(orch.finalize())

        summary = _summarize(events)
        audio_positions = [s[1] for s in summary if s[0] == "AUDIO"]
        visual_positions = [s[1] for s in summary if s[0] == "VISUAL"]

        # Audio before visual has lower position than visual
        assert audio_positions[0] < visual_positions[0]

        # Audio after visual has higher position than visual
        if len(audio_positions) > 1:
            assert audio_positions[-1] > visual_positions[0]


# ---------------------------------------------------------------------------
# 8.5 — Block with table + image generates correct positions and markers
# ---------------------------------------------------------------------------


class TestBlockWithTableAndImage:
    """Integration test: block with table + image produces correct events."""

    def test_table_and_image(self, orchestrator_factory):
        orch = orchestrator_factory()

        text = (
            "Here are the results:\n"
            "| Name | Score |\n"
            "| --- | --- |\n"
            "| Alice | 95 |\n"
            "| Bob | 87 |\n"
            "And here is the chart:\n"
            "![results chart](https://example.com/chart.png)\n"
            "That concludes the analysis."
        )

        events = _collect(orch.process_chunk(text))
        events += _collect(orch.finalize())

        summary = _summarize(events)
        visual_events = [s for s in summary if s[0] == "VISUAL"]

        # Should have 2 visual markers: table and image
        assert len(visual_events) == 2
        visual_types = [v[2] for v in visual_events]
        assert "table" in visual_types
        assert "image" in visual_types

        # Table appears before image in the text
        table_pos = next(v[1] for v in visual_events if v[2] == "table")
        image_pos = next(v[1] for v in visual_events if v[2] == "image")
        assert table_pos < image_pos

        # Positions are monotonically increasing overall
        all_positions = [s[1] for s in summary]
        assert all_positions == sorted(all_positions)


# ---------------------------------------------------------------------------
# 8.6 — Block with Bilibili iframe generates correct visual marker
# ---------------------------------------------------------------------------


class TestBlockWithBilibiliIframe:
    """Integration test: block with Bilibili iframe."""

    def test_bilibili_iframe(self, orchestrator_factory):
        orch = orchestrator_factory()

        text = (
            "Watch this video tutorial:\n"
            '<iframe src="//player.bilibili.com/player.html?bvid=BV1xx411c7mD" '
            'width="800" height="450" frameborder="0" allowfullscreen>'
            "</iframe>\n"
            "After watching, you should understand the concept."
        )

        events = _collect(orch.process_chunk(text))
        events += _collect(orch.finalize())

        summary = _summarize(events)
        visual_events = [s for s in summary if s[0] == "VISUAL"]

        assert len(visual_events) == 1
        assert visual_events[0][2] == "iframe"

        # Audio before and after
        audio_events = [s for s in summary if s[0] == "AUDIO"]
        assert len(audio_events) >= 2

    def test_youtube_iframe(self, orchestrator_factory):
        orch = orchestrator_factory()

        text = (
            "Here is a demo:\n"
            '<iframe width="560" height="315" '
            'src="https://www.youtube.com/embed/dQw4w9WgXcQ" '
            'frameborder="0" allowfullscreen></iframe>\n'
            "Pretty neat, right?"
        )

        events = _collect(orch.process_chunk(text))
        events += _collect(orch.finalize())

        summary = _summarize(events)
        visual_events = [s for s in summary if s[0] == "VISUAL"]
        assert len(visual_events) == 1
        assert visual_events[0][2] == "iframe"


# ---------------------------------------------------------------------------
# 8.7 — Block without visual elements — single audio (backward compatible)
# ---------------------------------------------------------------------------


class TestBlockWithoutVisuals:
    """Integration test: plain text block produces single audio at position 0."""

    def test_plain_text_single_audio(self, orchestrator_factory):
        orch = orchestrator_factory()

        text = (
            "This is a completely plain text block with no visual elements. "
            "It should produce a single audio record at position 0, "
            "maintaining backward compatibility with existing behaviour."
        )

        events = _collect(orch.process_chunk(text))
        events += _collect(orch.finalize())

        summary = _summarize(events)

        audio_events = [s for s in summary if s[0] == "AUDIO"]
        visual_events = [s for s in summary if s[0] == "VISUAL"]

        # No visual markers
        assert len(visual_events) == 0

        # Single audio at position 0
        assert len(audio_events) == 1
        assert audio_events[0][1] == 0

    def test_markdown_text_only_no_visuals(self, orchestrator_factory):
        """Markdown text with bold/links but no visual elements."""
        orch = orchestrator_factory()

        text = (
            "# Introduction\n\n"
            "This is **bold** text with a [link](https://example.com).\n"
            "- Item one\n"
            "- Item two\n"
        )

        events = _collect(orch.process_chunk(text))
        events += _collect(orch.finalize())

        summary = _summarize(events)
        visual_events = [s for s in summary if s[0] == "VISUAL"]
        assert len(visual_events) == 0

    def test_empty_block(self, orchestrator_factory):
        """Empty block produces no events."""
        orch = orchestrator_factory()

        events = _collect(orch.process_chunk(""))
        events += _collect(orch.finalize())

        summary = _summarize(events)
        assert len(summary) == 0


# ---------------------------------------------------------------------------
# Additional integration scenarios
# ---------------------------------------------------------------------------


class TestMixedVisualTypes:
    """Integration test: block with multiple different visual types."""

    def test_code_then_image_then_math(self, orchestrator_factory):
        orch = orchestrator_factory()

        text = (
            "Consider this code:\n"
            "```python\ndef f(x): return x**2\n```\n"
            "The graph looks like:\n"
            "![graph](graph.png)\n"
            "Which follows the formula:\n"
            "$$y = x^2$$\n"
            "Simple, right?"
        )

        events = _collect(orch.process_chunk(text))
        events += _collect(orch.finalize())

        summary = _summarize(events)
        visual_events = [s for s in summary if s[0] == "VISUAL"]
        visual_types = [v[2] for v in visual_events]

        assert "code" in visual_types
        assert "image" in visual_types
        assert "math" in visual_types

        # Verify ordering: code < image < math
        code_pos = next(v[1] for v in visual_events if v[2] == "code")
        image_pos = next(v[1] for v in visual_events if v[2] == "image")
        math_pos = next(v[1] for v in visual_events if v[2] == "math")
        assert code_pos < image_pos < math_pos

    def test_mermaid_diagram(self, orchestrator_factory):
        orch = orchestrator_factory()

        text = (
            "The workflow is:\n"
            "```mermaid\n"
            "graph TD\n"
            "  A[Start] --> B[Process]\n"
            "  B --> C[End]\n"
            "```\n"
            "Follow these steps carefully."
        )

        events = _collect(orch.process_chunk(text))
        events += _collect(orch.finalize())

        summary = _summarize(events)
        visual_events = [s for s in summary if s[0] == "VISUAL"]
        assert len(visual_events) == 1
        assert visual_events[0][2] == "mermaid"
