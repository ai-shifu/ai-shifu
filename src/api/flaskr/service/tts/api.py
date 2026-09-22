"""Expose the TTS service API."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.service.tts.cloned_voice_registry import (
    find_ready_cloned_voice,
    find_tracked_cloned_voice,
    get_clone_provider_spec,
    supports_cloned_voices,
)
from flaskr.service.tts.minimax_voice_clone import (
    MINIMAX_CLONE_PROMPT_MAX_BYTES,
    MINIMAX_CLONE_REQUEST_MAX_BYTES,
    MINIMAX_CLONE_SOURCE_MAX_BYTES,
    build_minimax_clone_cost,
    delete_minimax_cloned_voice,
    get_minimax_cloned_voice,
    is_valid_minimax_custom_voice_id,
    list_minimax_cloned_voices,
    retry_minimax_voice_clone,
    run_minimax_voice_clone,
    serialize_minimax_cloned_voice,
    submit_minimax_voice_clone,
)
from flaskr.service.tts.pipeline import build_av_segmentation_contract
from flaskr.service.tts.rpm_gate import TTSRpmQueueTimeoutError
from flaskr.service.tts.subtitle_utils import (
    append_subtitle_cue,
    normalize_subtitle_cues,
)
from flaskr.service.tts.volcengine_voice_clone import (
    is_valid_volcengine_custom_voice_id,
    verify_volcengine_voice_id,
)
from flaskr.util.deprecation import deprecated_alias_getattr

if TYPE_CHECKING:
    from flaskr.service.tts.streaming_tts import StreamingTTSProcessor


def create_av_streaming_tts_processor(**kwargs: object) -> object:
    """Build the processor that derives visual boundaries from the text as it streams.

    Unlike the plain one, this recomputes the AV contract on every chunk and attaches it to the
    audio events, which is what lets the element adapter rebuild slides for a block whose text
    arrived without MarkdownFlow stream parts.
    """
    from flaskr.service.tts.streaming_tts import AVStreamingTTSProcessor

    return AVStreamingTTSProcessor(**kwargs)


def create_streaming_tts_processor(**kwargs: object) -> StreamingTTSProcessor:
    """Create streaming TTS processor."""
    from flaskr.service.tts.streaming_tts import StreamingTTSProcessor

    return StreamingTTSProcessor(**kwargs)


__all__ = [
    "MINIMAX_CLONE_PROMPT_MAX_BYTES",
    "MINIMAX_CLONE_REQUEST_MAX_BYTES",
    "MINIMAX_CLONE_SOURCE_MAX_BYTES",
    "TTSRpmQueueTimeoutError",
    "append_subtitle_cue",
    "build_av_segmentation_contract",
    "build_minimax_clone_cost",
    "create_av_streaming_tts_processor",
    "create_streaming_tts_processor",
    "delete_minimax_cloned_voice",
    "find_ready_cloned_voice",
    "find_tracked_cloned_voice",
    "get_clone_provider_spec",
    "get_minimax_cloned_voice",
    "is_valid_minimax_custom_voice_id",
    "is_valid_volcengine_custom_voice_id",
    "list_minimax_cloned_voices",
    "normalize_subtitle_cues",
    "retry_minimax_voice_clone",
    "run_minimax_voice_clone",
    "serialize_minimax_cloned_voice",
    "submit_minimax_voice_clone",
    "supports_cloned_voices",
    "verify_volcengine_voice_id",
]


__getattr__ = deprecated_alias_getattr(
    __name__, {"TTSRpmQueueTimeout": "TTSRpmQueueTimeoutError"}, globals()
)
