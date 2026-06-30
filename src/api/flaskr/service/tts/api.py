from __future__ import annotations

from flaskr.service.tts.pipeline import build_av_segmentation_contract
from flaskr.service.tts.subtitle_utils import (
    append_subtitle_cue,
    normalize_subtitle_cues,
)
from flaskr.service.tts.minimax_voice_clone import (
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


def create_streaming_tts_processor(**kwargs):
    from flaskr.service.tts.streaming_tts import StreamingTTSProcessor

    return StreamingTTSProcessor(**kwargs)


__all__ = [
    "append_subtitle_cue",
    "build_minimax_clone_cost",
    "build_av_segmentation_contract",
    "create_streaming_tts_processor",
    "delete_minimax_cloned_voice",
    "get_minimax_cloned_voice",
    "is_valid_minimax_custom_voice_id",
    "list_minimax_cloned_voices",
    "normalize_subtitle_cues",
    "retry_minimax_voice_clone",
    "run_minimax_voice_clone",
    "serialize_minimax_cloned_voice",
    "submit_minimax_voice_clone",
]
