"""
Visual-Aware TTS Orchestrator.

Wraps StreamingTTSProcessor to split audio at visual element boundaries
(SVG, images, tables, iframes, code blocks, mermaid diagrams, etc.).
Each text segment between visual elements becomes a separate positional
audio with its own AUDIO_COMPLETE event.  Visual elements emit
VISUAL_MARKER events so the frontend can synchronize playback.
"""

import logging
from typing import Generator

from flask import Flask

from flaskr.common.log import AppLoggerProxy
from flaskr.service.tts.streaming_tts import StreamingTTSProcessor
from flaskr.service.tts.visual_patterns import (
    find_earliest_complete_visual,
    has_incomplete_visual,
)
from flaskr.service.tts import preprocess_for_tts
from flaskr.service.learn.learn_dtos import (
    RunMarkdownFlowDTO,
    GeneratedType,
    VisualMarkerDTO,
)
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PROD


logger = AppLoggerProxy(logging.getLogger(__name__))


class VisualAwareTTSOrchestrator:
    """
    Orchestrates multiple StreamingTTSProcessor instances, splitting at
    visual element boundaries.

    Exposes the same ``process_chunk`` / ``finalize`` / ``finalize_preview``
    interface as StreamingTTSProcessor so it can be used as a drop-in
    replacement in context_v2.py.
    """

    def __init__(
        self,
        app: Flask,
        generated_block_bid: str,
        outline_bid: str,
        progress_record_bid: str,
        user_bid: str,
        shifu_bid: str,
        voice_id: str = "",
        speed: float = 1.0,
        pitch: int = 0,
        emotion: str = "",
        max_segment_chars: int = 300,
        tts_provider: str = "",
        tts_model: str = "",
        usage_scene: int = BILL_USAGE_SCENE_PROD,
    ):
        # Store all params for creating child processors
        self._app = app
        self._generated_block_bid = generated_block_bid
        self._outline_bid = outline_bid
        self._progress_record_bid = progress_record_bid
        self._user_bid = user_bid
        self._shifu_bid = shifu_bid
        self._voice_id = voice_id
        self._speed = speed
        self._pitch = pitch
        self._emotion = emotion
        self._max_segment_chars = max_segment_chars
        self._tts_provider = tts_provider
        self._tts_model = tts_model
        self._usage_scene = usage_scene

        # Position counter (incremented after each visual boundary)
        self._position = 0

        # Raw text buffer (NOT preprocessed — we need to detect visuals)
        self._raw_buffer = ""

        # How much of _raw_buffer has been fed to the current processor
        self._fed_offset = 0

        # Current child processor
        self._current_processor = self._create_processor()

        # Whether finalize has been called
        self._finalized = False

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    def _create_processor(self) -> StreamingTTSProcessor:
        """Create a new StreamingTTSProcessor for the current position."""
        return StreamingTTSProcessor(
            app=self._app,
            generated_block_bid=self._generated_block_bid,
            outline_bid=self._outline_bid,
            progress_record_bid=self._progress_record_bid,
            user_bid=self._user_bid,
            shifu_bid=self._shifu_bid,
            voice_id=self._voice_id,
            speed=self._speed,
            pitch=self._pitch,
            emotion=self._emotion,
            max_segment_chars=self._max_segment_chars,
            tts_provider=self._tts_provider,
            tts_model=self._tts_model,
            usage_scene=self._usage_scene,
            position=self._position,
        )

    # ------------------------------------------------------------------
    # Public interface (matches StreamingTTSProcessor)
    # ------------------------------------------------------------------

    def process_chunk(self, chunk: str) -> Generator[RunMarkdownFlowDTO, None, None]:
        """
        Process a chunk of streaming content.

        Accumulates raw text, detects complete visual elements, and splits
        audio processing at each visual boundary.
        """
        if not chunk:
            # Still yield any ready segments from current processor
            yield from self._current_processor.process_chunk("")
            return

        self._raw_buffer += chunk

        # Iteratively split at visual boundaries
        yield from self._split_at_visuals()

        # Feed remaining un-fed text to current processor
        remaining = self._raw_buffer[self._fed_offset :]
        if remaining:
            self._fed_offset = len(self._raw_buffer)
            yield from self._current_processor.process_chunk(remaining)

    def finalize(
        self, *, commit: bool = True
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        """Finalize TTS processing after content streaming is complete."""
        if self._finalized:
            return
        self._finalized = True

        # Process any remaining visual boundaries in the final buffer
        yield from self._split_at_visuals()

        # Feed any remaining un-fed text
        remaining = self._raw_buffer[self._fed_offset :]
        if remaining:
            self._fed_offset = len(self._raw_buffer)
            yield from self._current_processor.process_chunk(remaining)

        # Finalize the last processor
        yield from self._current_processor.finalize(commit=commit)

    def finalize_preview(self) -> Generator[RunMarkdownFlowDTO, None, None]:
        """Finalize for preview mode (no OSS upload, no DB write)."""
        if self._finalized:
            return
        self._finalized = True

        # Process any remaining visual boundaries
        yield from self._split_at_visuals()

        # Feed remaining text
        remaining = self._raw_buffer[self._fed_offset :]
        if remaining:
            self._fed_offset = len(self._raw_buffer)
            yield from self._current_processor.process_chunk(remaining)

        # Finalize preview
        yield from self._current_processor.finalize_preview()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _split_at_visuals(self) -> Generator[RunMarkdownFlowDTO, None, None]:
        """
        Scan the raw buffer for complete visual elements and split.

        For each visual found:
        1. Finalize the current processor (text before visual).
        2. Yield a VISUAL_MARKER event.
        3. Start a new processor for text after the visual.
        """
        while True:
            # Only search in the un-fed portion — we never re-scan text
            # that has already been processed.
            search_text = self._raw_buffer[self._fed_offset :]
            if not search_text:
                break

            # Don't split if the buffer ends with an incomplete element
            if has_incomplete_visual(search_text):
                break

            match = find_earliest_complete_visual(search_text)
            if match is None:
                break

            # Translate match offsets to raw_buffer coordinates
            abs_start = self._fed_offset + match.start
            abs_end = self._fed_offset + match.end

            # Text before the visual that hasn't been fed yet
            text_before = self._raw_buffer[self._fed_offset : abs_start]

            logger.info(
                f"Visual boundary found: type={match.visual_type}, "
                f"position={self._position}, "
                f"text_before_len={len(text_before.strip())}, "
                f"visual_len={len(match.content)}"
            )

            # Feed text-before to current processor
            if text_before:
                yield from self._current_processor.process_chunk(text_before)

            # Check if current processor has any meaningful content
            has_content = self._current_processor._segment_index > 0 or (
                preprocess_for_tts(self._current_processor._buffer or "").strip() != ""
            )

            if has_content:
                # Finalize current processor — produces AUDIO_COMPLETE
                yield from self._current_processor.finalize(commit=False)
                self._position += 1
            # else: no audio before this visual, skip finalize

            # Emit visual marker
            yield RunMarkdownFlowDTO(
                outline_bid=self._outline_bid,
                generated_block_bid=self._generated_block_bid,
                type=GeneratedType.VISUAL_MARKER,
                content=VisualMarkerDTO(
                    position=self._position,
                    visual_type=match.visual_type,
                    content=match.content,
                ),
            )
            self._position += 1

            # Start new processor for text after visual
            self._current_processor = self._create_processor()

            # Advance fed_offset past the visual
            self._fed_offset = abs_end
