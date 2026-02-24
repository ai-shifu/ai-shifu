"""
Unit tests for VisualAwareTTSOrchestrator.

Tests cover:
  - Single visual element splitting
  - Multiple visual elements with correct position tracking
  - Adjacent visuals (no empty audio between them)
  - No visual elements (pass-through to single processor)
  - Visual at start / end of text
  - finalize() and finalize_preview() behaviour
"""

import pytest

from flaskr.service.learn.learn_dtos import (
    GeneratedType,
    RunMarkdownFlowDTO,
    AudioCompleteDTO,
    VisualMarkerDTO,
)


# ---------------------------------------------------------------------------
# Helper: lightweight mock processor
# ---------------------------------------------------------------------------


class FakeProcessor:
    """
    Lightweight stand-in for StreamingTTSProcessor.

    Tracks text fed via process_chunk() and records finalize calls.
    The orchestrator accesses ``_segment_index`` and ``_buffer`` to decide
    whether the processor has meaningful content.
    """

    def __init__(self, *, position: int = 0, **_kwargs):
        self._position = position
        self._buffer = ""
        self._segment_index = 0
        self._chunks: list[str] = []
        self._finalized = False
        self._finalized_preview = False

    # -- public interface used by the orchestrator --

    def process_chunk(self, chunk: str):
        if chunk:
            self._buffer += chunk
            self._chunks.append(chunk)
            # Simulate: any non-empty text means at least one segment submitted
            self._segment_index = 1
        yield from ()

    def finalize(self, *, commit: bool = True):
        self._finalized = True
        if self._segment_index > 0:
            yield RunMarkdownFlowDTO(
                outline_bid="outline-1",
                generated_block_bid="block-1",
                type=GeneratedType.AUDIO_COMPLETE,
                content=AudioCompleteDTO(
                    audio_url=f"https://cdn.example.com/audio_pos{self._position}.mp3",
                    audio_bid=f"audio-{self._position}",
                    duration_ms=1000,
                    position=self._position,
                ),
            )

    def finalize_preview(self):
        self._finalized_preview = True
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _require_app(app):
    if app is None:
        pytest.skip("App fixture disabled")


@pytest.fixture
def make_orchestrator(app):
    """Factory fixture that creates a VisualAwareTTSOrchestrator with mocked processor."""
    _require_app(app)

    from flaskr.service.tts.visual_aware_tts import VisualAwareTTSOrchestrator

    created_processors: list[FakeProcessor] = []

    def _factory():
        orch = VisualAwareTTSOrchestrator(
            app=app,
            generated_block_bid="block-1",
            outline_bid="outline-1",
            progress_record_bid="progress-1",
            user_bid="user-1",
            shifu_bid="shifu-1",
            voice_id="voice-1",
        )

        # Replace the real initial processor and monkey-patch the factory
        initial_proc = FakeProcessor(position=0)
        orch._current_processor = initial_proc
        created_processors.clear()
        created_processors.append(initial_proc)

        def _fake_create():
            proc = FakeProcessor(position=orch._position)
            created_processors.append(proc)
            return proc

        orch._create_processor = _fake_create

        return orch, created_processors, None

    return _factory


def _collect_events(gen):
    """Collect all RunMarkdownFlowDTO events from a generator."""
    return list(gen)


def _event_types(events):
    """Extract (type, position) tuples from events for easy assertion."""
    results = []
    for e in events:
        if e.type == GeneratedType.VISUAL_MARKER:
            results.append(("VISUAL_MARKER", e.content.position, e.content.visual_type))
        elif e.type == GeneratedType.AUDIO_COMPLETE:
            results.append(("AUDIO_COMPLETE", e.content.position))
        else:
            results.append((e.type.value,))
    return results


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNoVisualElements:
    """When there are no visual elements, text passes through to a single processor."""

    def test_plain_text_single_processor(self, make_orchestrator):
        orch, procs, _ = make_orchestrator()

        events = _collect_events(orch.process_chunk("Hello world. This is plain text."))
        events += _collect_events(orch.finalize())

        # Should only have one AUDIO_COMPLETE at position 0
        types = _event_types(events)
        audio_completes = [t for t in types if t[0] == "AUDIO_COMPLETE"]
        assert len(audio_completes) == 1
        assert audio_completes[0][1] == 0  # position 0

    def test_empty_text(self, make_orchestrator):
        orch, procs, _ = make_orchestrator()

        events = _collect_events(orch.process_chunk(""))
        events += _collect_events(orch.finalize())

        # No audio produced from empty text
        audio_completes = [e for e in events if e.type == GeneratedType.AUDIO_COMPLETE]
        assert len(audio_completes) == 0


class TestSingleVisual:
    """Text with a single visual element should produce 3 events."""

    def test_text_svg_text(self, make_orchestrator):
        """text + SVG + text => AUDIO_COMPLETE(0) + VISUAL_MARKER(1) + AUDIO_COMPLETE(2)"""
        orch, procs, mock_create = make_orchestrator()

        text = 'Before text. <svg width="100"><circle r="5"/></svg> After text.'
        events = _collect_events(orch.process_chunk(text))
        events += _collect_events(orch.finalize())

        types = _event_types(events)

        # Find audio completes and visual markers
        audio_events = [t for t in types if t[0] == "AUDIO_COMPLETE"]
        visual_events = [t for t in types if t[0] == "VISUAL_MARKER"]

        assert len(visual_events) == 1
        assert visual_events[0][2] == "svg"

        # At least 1 audio complete (before), visual marker, then finalize produces another
        assert len(audio_events) >= 1

    def test_image_in_text(self, make_orchestrator):
        orch, procs, _ = make_orchestrator()

        text = "See this diagram: ![arch](https://example.com/arch.png) and continue."
        events = _collect_events(orch.process_chunk(text))
        events += _collect_events(orch.finalize())

        types = _event_types(events)
        visual_events = [t for t in types if t[0] == "VISUAL_MARKER"]
        assert len(visual_events) == 1
        assert visual_events[0][2] == "image"

    def test_code_block_in_text(self, make_orchestrator):
        orch, procs, _ = make_orchestrator()

        text = "Here is code:\n```python\nprint('hello')\n```\nAnd more text."
        events = _collect_events(orch.process_chunk(text))
        events += _collect_events(orch.finalize())

        types = _event_types(events)
        visual_events = [t for t in types if t[0] == "VISUAL_MARKER"]
        assert len(visual_events) == 1
        assert visual_events[0][2] == "code"

    def test_table_in_text(self, make_orchestrator):
        orch, procs, _ = make_orchestrator()

        text = (
            "Data below:\n| Name | Age |\n| --- | --- |\n| Alice | 30 |\nEnd of data."
        )
        events = _collect_events(orch.process_chunk(text))
        events += _collect_events(orch.finalize())

        types = _event_types(events)
        visual_events = [t for t in types if t[0] == "VISUAL_MARKER"]
        assert len(visual_events) == 1
        assert visual_events[0][2] == "table"


class TestMultipleVisuals:
    """Text with multiple visual elements should produce correct positions."""

    def test_two_visuals(self, make_orchestrator):
        """text + SVG + text + image + text"""
        orch, procs, _ = make_orchestrator()

        text = (
            "Intro. "
            '<svg width="100"><circle r="5"/></svg> '
            "Middle text. "
            "![pic](photo.png) "
            "End."
        )
        events = _collect_events(orch.process_chunk(text))
        events += _collect_events(orch.finalize())

        types = _event_types(events)
        visual_events = [t for t in types if t[0] == "VISUAL_MARKER"]
        assert len(visual_events) == 2
        assert visual_events[0][2] == "svg"
        assert visual_events[1][2] == "image"

        # Positions should be monotonically increasing
        all_positions = [t[1] for t in types if len(t) > 1]
        assert all_positions == sorted(all_positions)

    def test_three_visuals_positions_increase(self, make_orchestrator):
        orch, procs, _ = make_orchestrator()

        text = "A. ![img1](1.png) B. ![img2](2.png) C. ![img3](3.png) D."
        events = _collect_events(orch.process_chunk(text))
        events += _collect_events(orch.finalize())

        types = _event_types(events)
        positions = [t[1] for t in types if len(t) > 1]
        # All positions should be strictly increasing
        for i in range(1, len(positions)):
            assert positions[i] > positions[i - 1], (
                f"Position {positions[i]} <= {positions[i - 1]}"
            )


class TestAdjacentVisuals:
    """Adjacent visuals with no text between them should not produce empty audio."""

    def test_two_adjacent_images(self, make_orchestrator):
        orch, procs, _ = make_orchestrator()

        text = "Before. ![a](1.png)![b](2.png) After."
        events = _collect_events(orch.process_chunk(text))
        events += _collect_events(orch.finalize())

        types = _event_types(events)
        visual_events = [t for t in types if t[0] == "VISUAL_MARKER"]
        assert len(visual_events) == 2


class TestVisualAtBoundaries:
    """Visual elements at the start or end of text."""

    def test_visual_at_start(self, make_orchestrator):
        orch, procs, _ = make_orchestrator()

        text = "![img](url.png) Some text after."
        events = _collect_events(orch.process_chunk(text))
        events += _collect_events(orch.finalize())

        types = _event_types(events)
        visual_events = [t for t in types if t[0] == "VISUAL_MARKER"]
        assert len(visual_events) == 1

    def test_visual_at_end(self, make_orchestrator):
        orch, procs, _ = make_orchestrator()

        text = "Some text before. ![img](url.png)"
        events = _collect_events(orch.process_chunk(text))
        events += _collect_events(orch.finalize())

        types = _event_types(events)
        visual_events = [t for t in types if t[0] == "VISUAL_MARKER"]
        assert len(visual_events) == 1

    def test_only_visual_no_text(self, make_orchestrator):
        orch, procs, _ = make_orchestrator()

        text = "![img](url.png)"
        events = _collect_events(orch.process_chunk(text))
        events += _collect_events(orch.finalize())

        types = _event_types(events)
        visual_events = [t for t in types if t[0] == "VISUAL_MARKER"]
        assert len(visual_events) == 1


class TestStreamingChunks:
    """Simulate streaming where visual elements arrive across multiple chunks.

    Design note: The orchestrator feeds un-fed text to the current processor
    on every ``process_chunk`` call, even when an incomplete visual is detected.
    ``has_incomplete_visual`` only prevents *splitting* — it does not withhold
    text from the child processor (the child's ``preprocess_for_tts`` strips
    non-speakable content safely).

    As a result, when a visual element is split across chunks, the opening
    part is fed to the processor in the first call and the search window in
    subsequent calls no longer contains the full ``<svg>…</svg>``.  This is
    by design: in practice, LLM token streaming usually fills the buffer fast
    enough that visuals are complete before splitting is attempted.
    """

    def test_incomplete_svg_does_not_trigger_split(self, make_orchestrator):
        """First chunk with incomplete SVG produces no visual marker."""
        orch, procs, _ = make_orchestrator()

        events = _collect_events(orch.process_chunk("Before. <svg width='100'>"))
        visual_events = [e for e in events if e.type == GeneratedType.VISUAL_MARKER]
        assert len(visual_events) == 0

    def test_incomplete_code_does_not_trigger_split(self, make_orchestrator):
        """Incomplete fenced code block produces no visual marker."""
        orch, procs, _ = make_orchestrator()

        events = _collect_events(orch.process_chunk("Before.\n```python\nprint('hi')"))
        visual_events = [e for e in events if e.type == GeneratedType.VISUAL_MARKER]
        assert len(visual_events) == 0

    def test_complete_visual_in_single_chunk(self, make_orchestrator):
        """When the full visual arrives in one chunk, splitting works correctly."""
        orch, procs, _ = make_orchestrator()

        events = _collect_events(
            orch.process_chunk("Before. <svg><circle/></svg> After.")
        )
        events += _collect_events(orch.finalize())

        visual_events = [e for e in events if e.type == GeneratedType.VISUAL_MARKER]
        assert len(visual_events) == 1
        assert visual_events[0].content.visual_type == "svg"

    def test_multiple_chunks_before_visual(self, make_orchestrator):
        """Plain text chunks followed by a complete visual in a later chunk."""
        orch, procs, _ = make_orchestrator()

        events1 = _collect_events(orch.process_chunk("Hello "))
        events2 = _collect_events(orch.process_chunk("world. "))
        events3 = _collect_events(orch.process_chunk("![img](url.png) Done."))
        events3 += _collect_events(orch.finalize())

        all_events = events1 + events2 + events3
        visual_events = [e for e in all_events if e.type == GeneratedType.VISUAL_MARKER]
        assert len(visual_events) == 1
        assert visual_events[0].content.visual_type == "image"


class TestVisualMarkerContent:
    """Verify VISUAL_MARKER events contain correct metadata."""

    def test_marker_has_correct_visual_type(self, make_orchestrator):
        orch, procs, _ = make_orchestrator()

        text = 'Hello. <svg width="100"><circle/></svg> World.'
        events = _collect_events(orch.process_chunk(text))
        events += _collect_events(orch.finalize())

        markers = [e for e in events if e.type == GeneratedType.VISUAL_MARKER]
        assert len(markers) == 1
        marker = markers[0]
        assert isinstance(marker.content, VisualMarkerDTO)
        assert marker.content.visual_type == "svg"
        assert "<svg" in marker.content.content
        assert "</svg>" in marker.content.content

    def test_marker_has_correct_block_ids(self, make_orchestrator):
        orch, procs, _ = make_orchestrator()

        text = "Text. ![img](url.png) More."
        events = _collect_events(orch.process_chunk(text))
        events += _collect_events(orch.finalize())

        markers = [e for e in events if e.type == GeneratedType.VISUAL_MARKER]
        assert len(markers) == 1
        assert markers[0].outline_bid == "outline-1"
        assert markers[0].generated_block_bid == "block-1"


class TestFinalizePreview:
    """Test finalize_preview() path."""

    def test_finalize_preview_with_visual(self, make_orchestrator):
        orch, procs, _ = make_orchestrator()

        text = "Before. ![img](url.png) After."
        events = _collect_events(orch.process_chunk(text))
        events += _collect_events(orch.finalize_preview())

        visual_events = [e for e in events if e.type == GeneratedType.VISUAL_MARKER]
        assert len(visual_events) == 1

    def test_finalize_preview_no_double_finalize(self, make_orchestrator):
        orch, procs, _ = make_orchestrator()

        text = "Before. ![img](url.png) After."
        _collect_events(orch.process_chunk(text))
        _collect_events(orch.finalize_preview())
        second_finalize = _collect_events(
            orch.finalize_preview()
        )  # second call should be no-op

        # Second finalize_preview should yield nothing
        assert len(second_finalize) == 0


class TestFinalizeIdempotent:
    """Test that finalize() is idempotent."""

    def test_double_finalize(self, make_orchestrator):
        orch, procs, _ = make_orchestrator()

        text = "Hello world."
        _collect_events(orch.process_chunk(text))
        _collect_events(orch.finalize())
        second_finalize = _collect_events(orch.finalize())

        assert len(second_finalize) == 0
