from __future__ import annotations

from flaskr.service.tts.pipeline import build_av_segmentation_contract
from flaskr.service.tts.subtitle_utils import (
    append_subtitle_cue,
    normalize_subtitle_cues,
)


def create_streaming_tts_processor(**kwargs):
    from flaskr.service.tts.streaming_tts import StreamingTTSProcessor

    return StreamingTTSProcessor(**kwargs)


__all__ = [
    "append_subtitle_cue",
    "build_av_segmentation_contract",
    "create_streaming_tts_processor",
    "normalize_subtitle_cues",
]
