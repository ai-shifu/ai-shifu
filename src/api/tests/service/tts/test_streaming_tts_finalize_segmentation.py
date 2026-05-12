"""
Tests for TTS streaming finalize segmentation improvements.

Verifies that the finalize() method properly segments remaining text
instead of submitting it all at once, preventing burst delivery of
final segments.
"""

import pytest
from unittest.mock import MagicMock, patch

from flaskr.api.tts import TTSResult
from flaskr.service.learn.learn_dtos import GeneratedType
from flaskr.service.tts.streaming_tts import StreamingTTSProcessor, TTSSegment


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


class TestStreamingSynthesisRetries:
    """Regression coverage for transient provider empty-audio responses."""

    @patch("flaskr.service.tts.streaming_tts.time.sleep")
    @patch("flaskr.service.tts.tts_usage_recorder.record_tts_segment_usage")
    @patch("flaskr.service.tts.streaming_tts.synthesize_text")
    @patch("flaskr.service.tts.streaming_tts.is_tts_configured")
    def test_volcengine_empty_audio_segment_retries_once(
        self,
        mock_is_configured,
        mock_synthesize_text,
        mock_record_usage,
        mock_sleep,
        mock_app,
    ):
        mock_is_configured.return_value = True
        mock_synthesize_text.side_effect = [
            ValueError("No audio data received"),
            TTSResult(
                audio_data=b"audio",
                duration_ms=321,
                sample_rate=24000,
                format="mp3",
                word_count=4,
            ),
        ]
        app_context = MagicMock()
        app_context.__enter__.return_value = None
        app_context.__exit__.return_value = False
        mock_app.app_context.return_value = app_context

        processor = create_test_processor(
            mock_app,
            tts_provider="volcengine",
            tts_model="seed-tts-2.0",
        )
        segment = TTSSegment(index=3, text="Please synthesize this sentence.")

        result = processor._synthesize_in_thread(
            segment,
            processor.voice_settings,
            processor.audio_settings,
            processor.tts_provider,
            processor.tts_model,
        )

        assert mock_synthesize_text.call_count == 2
        mock_sleep.assert_called_once()
        assert result.error is None
        assert result.audio_data == b"audio"
        assert result.duration_ms == 321
        assert result.word_count == 4
        mock_record_usage.assert_called_once()

    @patch("flaskr.service.tts.streaming_tts.save_audio_record")
    @patch("flaskr.service.tts.tts_usage_recorder.record_tts_aggregated_usage")
    @patch("flaskr.service.tts.tts_usage_recorder.record_tts_segment_usage")
    @patch("flaskr.service.tts.tts_handler.upload_audio_to_oss")
    @patch("flaskr.service.tts.streaming_tts.get_audio_duration_ms")
    @patch("flaskr.service.tts.streaming_tts.concat_audio_best_effort")
    @patch("flaskr.service.tts.streaming_tts.synthesize_text")
    @patch("flaskr.service.tts.streaming_tts.is_tts_configured")
    def test_volcengine_finalizes_whole_text_with_provider_subtitles(
        self,
        mock_is_configured,
        mock_synthesize_text,
        mock_concat_audio,
        mock_get_duration,
        mock_upload,
        mock_record_segment_usage,
        mock_record_aggregate_usage,
        mock_save_audio_record,
        mock_app,
    ):
        mock_is_configured.return_value = True
        mock_synthesize_text.return_value = TTSResult(
            audio_data=b"provider-audio",
            duration_ms=500,
            sample_rate=24000,
            format="mp3",
            word_count=19,
            subtitle_cues=[
                {
                    "text": "Provider subtitles.",
                    "start_ms": 0,
                    "end_ms": 500,
                    "segment_index": 0,
                }
            ],
        )
        mock_concat_audio.side_effect = lambda parts: b"".join(parts)
        mock_get_duration.return_value = 500
        mock_upload.return_value = ("https://example.com/audio.mp3", "bucket")

        processor = create_test_processor(
            mock_app,
            tts_provider="volcengine",
            tts_model="seed-tts-2.0",
            position=2,
        )

        chunk_events = list(processor.process_chunk("Provider subtitles."))
        assert chunk_events == []
        mock_synthesize_text.assert_not_called()

        events = list(processor.finalize(commit=True))

        audio_segments = [
            event for event in events if event.type == GeneratedType.AUDIO_SEGMENT
        ]
        audio_complete = [
            event for event in events if event.type == GeneratedType.AUDIO_COMPLETE
        ]

        assert len(audio_segments) == 1
        assert len(audio_complete) == 1
        mock_synthesize_text.assert_called_once()
        assert mock_synthesize_text.call_args.kwargs["text"] == "Provider subtitles."
        assert [cue.text for cue in audio_segments[0].content.subtitle_cues] == [
            "Provider subtitles."
        ]
        assert [
            (cue.start_ms, cue.end_ms, cue.position)
            for cue in audio_complete[0].content.subtitle_cues
        ] == [(0, 500, 2)]
        mock_record_segment_usage.assert_called_once()
        mock_record_aggregate_usage.assert_called_once()
        mock_save_audio_record.assert_called_once()

    @patch("flaskr.service.tts.streaming_tts.time.sleep")
    @patch("flaskr.service.tts.streaming_tts.save_audio_record")
    @patch("flaskr.service.tts.tts_usage_recorder.record_tts_aggregated_usage")
    @patch("flaskr.service.tts.tts_usage_recorder.record_tts_segment_usage")
    @patch("flaskr.service.tts.tts_handler.upload_audio_to_oss")
    @patch("flaskr.service.tts.streaming_tts.get_audio_duration_ms")
    @patch("flaskr.service.tts.streaming_tts.concat_audio_best_effort")
    @patch("flaskr.service.tts.streaming_tts.synthesize_text")
    @patch("flaskr.service.tts.streaming_tts.is_tts_configured")
    def test_volcengine_whole_text_empty_audio_retries_once(
        self,
        mock_is_configured,
        mock_synthesize_text,
        mock_concat_audio,
        mock_get_duration,
        mock_upload,
        mock_record_segment_usage,
        mock_record_aggregate_usage,
        mock_save_audio_record,
        mock_sleep,
        mock_app,
    ):
        mock_is_configured.return_value = True
        mock_synthesize_text.side_effect = [
            ValueError("No audio data received"),
            TTSResult(
                audio_data=b"retried-audio",
                duration_ms=400,
                sample_rate=24000,
                format="mp3",
                word_count=17,
                subtitle_cues=[
                    {
                        "text": "Retry subtitles.",
                        "start_ms": 0,
                        "end_ms": 400,
                        "segment_index": 0,
                    }
                ],
            ),
        ]
        mock_concat_audio.side_effect = lambda parts: b"".join(parts)
        mock_get_duration.return_value = 400
        mock_upload.return_value = ("https://example.com/retry.mp3", "bucket")

        processor = create_test_processor(
            mock_app,
            tts_provider="volcengine",
            tts_model="seed-tts-2.0",
        )
        list(processor.process_chunk("Retry subtitles."))

        events = list(processor.finalize(commit=True))

        assert mock_synthesize_text.call_count == 2
        mock_sleep.assert_called_once()
        assert [event for event in events if event.type == GeneratedType.AUDIO_SEGMENT]
        assert [event for event in events if event.type == GeneratedType.AUDIO_COMPLETE]
        mock_record_segment_usage.assert_called_once()
        mock_record_aggregate_usage.assert_called_once()
        mock_save_audio_record.assert_called_once()


class TestOffsetDriftRegression:
    """Regression tests for offset drift when markdown becomes complete across chunks."""

    @patch("flaskr.service.tts.streaming_tts._tts_executor")
    @patch("flaskr.service.tts.streaming_tts.is_tts_configured")
    def test_bold_spanning_chunks_no_text_loss(
        self, mock_is_configured, mock_executor, mock_app
    ):
        """Bold markers completing across chunks must not cause text loss.

        Regression: when **bold** spans the processed/unprocessed boundary,
        preprocess_for_tts output length changes for already-processed text,
        causing _processed_text_offset to misalign and skip text.
        """
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

        # Chunk 1: bold starts but doesn't close, first sentence submitted
        list(processor.process_chunk("First. **Second"))
        assert len(submitted_texts) == 1
        assert "First" in submitted_texts[0]

        # Chunk 2: bold closes, completing the markdown construct
        # This changes preprocessing output for already-processed text
        list(processor.process_chunk(" part**. Third."))

        # Verify "Second part" is NOT lost
        all_text = " ".join(submitted_texts)
        assert "Second" in all_text or "Second part" in all_text, (
            f"Text 'Second part' was lost due to offset drift. "
            f"Submitted: {submitted_texts}"
        )
        assert "Third" in all_text, (
            f"Text 'Third' was lost. Submitted: {submitted_texts}"
        )

    @patch("flaskr.service.tts.streaming_tts._tts_executor")
    @patch("flaskr.service.tts.streaming_tts.is_tts_configured")
    def test_link_spanning_chunks_no_text_loss(
        self, mock_is_configured, mock_executor, mock_app
    ):
        """Links completing across chunks must not lose surrounding text."""
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

        # Chunk 1: sentence + start of a link
        list(processor.process_chunk("Hello. See [docs](https://exam"))
        # Chunk 2: link completes
        list(processor.process_chunk("ple.com). World."))

        all_text = " ".join(submitted_texts)
        assert "Hello" in all_text
        assert "World" in all_text, (
            f"Text 'World' lost after link completion. Submitted: {submitted_texts}"
        )


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
