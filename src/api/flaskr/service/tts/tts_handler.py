"""
TTS Handler for Content Generation.

This module provides OSS upload utility for TTS audio files.
"""

import logging
from typing import Tuple

from flask import Flask

from flaskr.service.common.oss_utils import OSS_PROFILE_COURSES, upload_to_oss

logger = logging.getLogger(__name__)


def upload_audio_to_oss(
    app: Flask, audio_content: bytes, audio_bid: str
) -> Tuple[str, str]:
    """
    Upload audio to OSS.

    Args:
        app: Flask application instance
        audio_content: Audio data bytes
        audio_bid: Audio business identifier

    Returns:
        Tuple of (oss_url, bucket_name)
    """
    file_id = f"tts-audio/{audio_bid}.mp3"
    content_type = "audio/mpeg"

    return upload_to_oss(
        app,
        file_content=audio_content,
        file_id=file_id,
        content_type=content_type,
        profile=OSS_PROFILE_COURSES,
    )
