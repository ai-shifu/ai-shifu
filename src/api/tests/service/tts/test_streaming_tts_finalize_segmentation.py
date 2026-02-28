"""
Tests for TTS streaming finalize segmentation improvements.

Verifies that the finalize() method properly segments remaining text
instead of submitting it all at once, preventing burst delivery of
final segments.
"""

import pytest
from unittest.mock import MagicMock, patch

from flaskr.service.tts.streaming_tts import StreamingTTSProcessor


@pytest.fixture
def mock_app():
    """Create a mock Flask app."""
    app = MagicMock()
    app.config = {}
    return app


def create_test_processor(mock_app, **kwargs):
    """Helper to create a StreamingTTSProcessor with test defaults."""
    defaults = {
        "app": mock_app,
        "generated_block_bid": "test-block",
        "outline_bid": "test-outline",
        "progress_record_bid": "test-progress",
        "user_bid": "test-user",
        "shifu_bid": "test-shifu",
        "position": 0,
    }
    defaults.update(kwargs)
    return StreamingTTSProcessor(**defaults)


class TestFinalizeSegmentation:
    """Tests for finalize segmentation improvements."""

    @patch("flaskr.service.tts.streaming_tts._tts_executor")
    @patch("flaskr.service.tts.streaming_tts.is_tts_configured")
    def test_process_chunk_submits_only_after_sentence_boundary(
        self, mock_is_configured, mock_executor, mock_app
    ):
        """Test stream-time submission waits for a full sentence ending."""
        mock_is_configured.return_value = True

        processor = create_test_processor(mock_app)
        submitted_texts = []

        def mock_submit(*args, **kwargs):
            if len(args) > 1:
                segment = args[1]
                if hasattr(segment, "text"):
                    submitted_texts.append(segment.text)
            future = MagicMock()
            future.result.return_value = None
            return future

        mock_executor.submit.side_effect = mock_submit

        list(processor.process_chunk("Hello without ending"))
        assert submitted_texts == []

        list(processor.process_chunk(" still no ending"))
        assert submitted_texts == []

        list(processor.process_chunk("!"))
        assert submitted_texts == ["Hello without ending still no ending!"]

    @patch("flaskr.service.tts.streaming_tts._tts_executor")
    @patch("flaskr.service.tts.streaming_tts.is_tts_configured")
    def test_submit_remaining_text_in_segments_splits_at_sentence_boundaries(
        self, mock_is_configured, mock_executor, mock_app
    ):
        """Test that remaining text is split at sentence boundaries."""
        mock_is_configured.return_value = True

        processor = create_test_processor(mock_app)

        # Simulate remaining text with multiple sentences
        remaining_text = (
            "This is the first sentence. "
            "This is the second sentence. "
            "This is the third sentence."
        )

        # Track submitted tasks
        submitted_texts = []

        def mock_submit(*args, **kwargs):
            # Args: (_synthesize_in_thread, segment, voice_settings, audio_settings, provider, model)
            # Capture the segment text from args[1]
            if len(args) > 1:
                segment = args[1]
                if hasattr(segment, "text"):
                    submitted_texts.append(segment.text)
            future = MagicMock()
            future.result.return_value = None
            return future

        mock_executor.submit.side_effect = mock_submit

        # Call the method
        processor._submit_remaining_text_in_segments(remaining_text)

        # Verify multiple segments were submitted
        assert len(submitted_texts) > 0
        # Each segment should end at a sentence boundary (except possibly the last)
        for i, text in enumerate(submitted_texts[:-1]):
            assert text.rstrip().endswith((".", "!", "?", "。", "！", "？"))

    @patch("flaskr.service.tts.streaming_tts._tts_executor")
    @patch("flaskr.service.tts.streaming_tts.is_tts_configured")
    def test_submit_remaining_text_does_not_split_by_char_count_without_sentence(
        self, mock_is_configured, mock_executor, mock_app
    ):
        """Test that text without sentence boundaries is submitted as one segment."""
        mock_is_configured.return_value = True

        processor = create_test_processor(
            mock_app,
            max_segment_chars=50,  # Small limit for testing
        )

        # Long text without sentence boundaries
        remaining_text = "a" * 200

        submitted_texts = []

        def mock_submit(*args, **kwargs):
            # Args: (_synthesize_in_thread, segment, voice_settings, audio_settings, provider, model)
            if len(args) > 1:
                segment = args[1]
                if hasattr(segment, "text"):
                    submitted_texts.append(segment.text)
            future = MagicMock()
            future.result.return_value = None
            return future

        mock_executor.submit.side_effect = mock_submit

        processor._submit_remaining_text_in_segments(remaining_text)

        assert submitted_texts == [remaining_text]

    @patch("flaskr.service.tts.streaming_tts._tts_executor")
    @patch("flaskr.service.tts.streaming_tts.is_tts_configured")
    def test_submit_remaining_text_handles_short_text(
        self, mock_is_configured, mock_executor, mock_app
    ):
        """Test handling of very short remaining text."""
        mock_is_configured.return_value = True

        processor = create_test_processor(mock_app)

        # Very short text
        remaining_text = "Hi"

        submitted_texts = []

        def mock_submit(*args, **kwargs):
            # Args: (_synthesize_in_thread, segment, voice_settings, audio_settings, provider, model)
            if len(args) > 1:
                segment = args[1]
                if hasattr(segment, "text"):
                    submitted_texts.append(segment.text)
            future = MagicMock()
            future.result.return_value = None
            return future

        mock_executor.submit.side_effect = mock_submit

        processor._submit_remaining_text_in_segments(remaining_text)

        # Should submit the short text as a single segment
        assert len(submitted_texts) == 1
        assert submitted_texts[0] == "Hi"

    @patch("flaskr.service.tts.streaming_tts._tts_executor")
    @patch("flaskr.service.tts.streaming_tts.is_tts_configured")
    def test_submit_remaining_text_handles_empty_string(
        self, mock_is_configured, mock_executor, mock_app
    ):
        """Test handling of empty remaining text."""
        mock_is_configured.return_value = True

        processor = create_test_processor(mock_app)

        # Empty text
        processor._submit_remaining_text_in_segments("")

        # Should not submit anything
        assert mock_executor.submit.call_count == 0

    @patch("flaskr.service.tts.streaming_tts._tts_executor")
    @patch("flaskr.service.tts.streaming_tts.is_tts_configured")
    def test_submit_remaining_text_handles_whitespace_only(
        self, mock_is_configured, mock_executor, mock_app
    ):
        """Test handling of whitespace-only remaining text."""
        mock_is_configured.return_value = True

        processor = create_test_processor(mock_app)

        # Whitespace only
        processor._submit_remaining_text_in_segments("   \n\t  ")

        # Should not submit anything
        assert mock_executor.submit.call_count == 0

    @patch("flaskr.service.tts.streaming_tts._tts_executor")
    @patch("flaskr.service.tts.streaming_tts.is_tts_configured")
    def test_submit_remaining_text_logs_segment_info(
        self, mock_is_configured, mock_executor, mock_app, caplog
    ):
        """Test that segment submission is properly logged."""
        mock_is_configured.return_value = True

        processor = create_test_processor(mock_app)

        remaining_text = "First sentence. Second sentence."

        def mock_submit(*args, **kwargs):
            future = MagicMock()
            future.result.return_value = None
            return future

        mock_executor.submit.side_effect = mock_submit

        with caplog.at_level("DEBUG"):
            processor._submit_remaining_text_in_segments(remaining_text)

        # Verify logging
        assert "Submitting remaining text in segments" in caplog.text
        assert "Submitted finalize segment" in caplog.text


class TestFinalizeDelayManagement:
    """Tests for finalize delay management improvements."""

    @patch("flaskr.service.tts.streaming_tts._tts_executor")
    @patch("flaskr.service.tts.streaming_tts.is_tts_configured")
    @patch("flaskr.service.tts.streaming_tts.time.sleep")
    def test_yield_ready_segments_adds_delay_between_segments(
        self, mock_sleep, mock_is_configured, mock_executor, mock_app
    ):
        """Test that _yield_ready_segments adds delay between segment yields."""
        mock_is_configured.return_value = True

        processor = create_test_processor(mock_app)
        processor._enabled = True

        # Create mock completed segments
        num_segments = 4
        for i in range(num_segments):
            segment = MagicMock()
            segment.index = i
            segment.audio_data = b"fake_audio_data"
            segment.duration_ms = 1000
            segment.error = None
            processor._completed_segments[i] = segment

        # Yield ready segments
        list(processor._yield_ready_segments())

        # Verify sleep was called between segments (not before first segment)
        # For 4 segments, should have 3 delays (between 0-1, 1-2, 2-3)
        assert mock_sleep.call_count == num_segments - 1
        mock_sleep.assert_called_with(0.1)  # 100ms delay
