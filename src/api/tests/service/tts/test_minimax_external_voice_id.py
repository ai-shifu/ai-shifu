"""Verify external MiniMax custom voice IDs remain usable."""

from __future__ import annotations

import pytest
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.tts.cloned_voice_records import is_valid_minimax_custom_voice_id
from flaskr.service.tts.validation import validate_tts_settings_strict


def test_validate_minimax_custom_voice_id_rules() -> None:
    assert is_valid_minimax_custom_voice_id("AiShifu_voice_123")
    assert not is_valid_minimax_custom_voice_id("1starts-with-digit")
    assert not is_valid_minimax_custom_voice_id("AiShifu_voice_")

    settings = validate_tts_settings_strict(
        provider="minimax",
        model="speech-2.8-turbo",
        voice_id="AiShifu_voice_123",
        speed=1.0,
        pitch=0,
        emotion="neutral",
    )

    assert settings.voice_id == "AiShifu_voice_123"

    with pytest.raises(AppError) as exc_info:
        validate_tts_settings_strict(
            provider="baidu",
            model="",
            voice_id="AiShifu_voice_123",
            speed=5.0,
            pitch=5,
            emotion="",
        )
    assert exc_info.value.code == ERROR_CODE["server.common.paramsError"]
