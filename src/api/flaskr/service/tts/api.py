from __future__ import annotations

from flaskr.service.tts.cloned_voice_registry import (
    find_ready_cloned_voice,
    find_tracked_cloned_voice,
    get_clone_provider_spec,
    supports_cloned_voices,
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


def create_streaming_tts_processor(**kwargs):
    from flaskr.service.tts.streaming_tts import StreamingTTSProcessor

    return StreamingTTSProcessor(**kwargs)


__all__ = [
    "TTSRpmQueueTimeoutError",
    "append_subtitle_cue",
    "build_av_segmentation_contract",
    "build_minimax_clone_cost",
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
