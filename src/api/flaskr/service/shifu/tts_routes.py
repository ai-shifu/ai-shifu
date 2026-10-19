"""Register shifu TTS voice, config, and preview routes.

Route bodies resolve service functions through ``flaskr.service.shifu.route``
so patching a name on that module keeps affecting the registered views.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import Response, request
from flaskr.common.http import bypass_token_validation, make_common_response

if TYPE_CHECKING:
    from collections.abc import Callable

    from flask import Flask


def register_shifu_tts_routes(
    app: Flask, path_prefix: str, *, _admit_creator_debug_usage: Callable[[object], str]
) -> None:
    """Register TTS voice, config, and preview routes."""
    from flaskr.service.shifu.route import ShifuPermission, ShifuTokenValidation

    @app.route(path_prefix + "/tts/minimax/voices", methods=["GET"])
    @ShifuTokenValidation(ShifuPermission.VIEW, is_creator=True)
    def list_minimax_tts_voices_api() -> str:
        from flaskr.service.tts.api import list_minimax_cloned_voices

        user_id = request.user.user_id
        shifu_bid = (request.args.get("shifu_bid") or "").strip()
        # Historical route name notwithstanding, the table now holds cloned
        # voices of multiple providers; an empty provider returns all of them
        # so older clients keep working.
        provider = (request.args.get("provider") or "").strip()
        return make_common_response(
            {
                "voices": list_minimax_cloned_voices(
                    app,
                    owner_user_bid=user_id,
                    shifu_bid=shifu_bid,
                    provider=provider,
                )
            }
        )

    @app.route(path_prefix + "/tts/minimax/voices/validate-id", methods=["POST"])
    @ShifuTokenValidation(ShifuPermission.VIEW, is_creator=True)
    def validate_minimax_tts_voice_id_api() -> str:
        from flaskr.service.tts.api import (
            is_valid_minimax_custom_voice_id,
        )

        payload = request.get_json(silent=True) or {}
        voice_id = (payload.get("voice_id") or "").strip()
        return make_common_response(
            {
                "voice_id": voice_id,
                "valid": is_valid_minimax_custom_voice_id(voice_id),
            }
        )

    @app.route(path_prefix + "/tts/config", methods=["GET"])
    @bypass_token_validation
    def tts_config_api() -> str:
        """Get TTS provider configuration.

        ---
        tags:
            - tts
        responses:
            200:
                description: TTS provider configuration
                content:
                    application/json:
                        schema:
                            type: object
                            properties:
                                providers:
                                    type: array
                                    description: List of available providers with configs
        """
        from flaskr.api.tts import get_all_provider_configs

        config = get_all_provider_configs()
        return make_common_response(config)

    @app.route(path_prefix + "/tts/preview", methods=["POST"])
    def tts_preview_api() -> Response:
        """Preview TTS with specified settings.

        ---
        tags:
            - tts
        requestBody:
            required: true
            content:
                application/json:
                    schema:
                        type: object
                        required: [shifu_bid]
                        properties:
                            shifu_bid:
                                type: string
                                description: Course to preview; requires edit permission
                            voice_id:
                                type: string
                                description: Voice ID for synthesis
                            speed:
                                type: number
                                description: Speech speed (provider-specific range)
                            pitch:
                                type: integer
                                description: Pitch adjustment (provider-specific range)
                            emotion:
                                type: string
                                description: Emotion setting
                            text:
                                type: string
                                description: Optional custom text to preview
        responses:
            200:
                description: stream TTS preview audio
                content:
                    text/event-stream:
                        schema:
                            type: string
                            example: 'data: {"type":"audio_segment","content":{"segment_index":0,"audio_data":"...","duration_ms":123,"is_final":false}}'
        """
        from flaskr.service.shifu.tts_preview import build_tts_preview_response

        json_data = request.get_json() or {}
        preview_shifu_bid = _admit_creator_debug_usage(json_data.get("shifu_bid"))
        request_user = getattr(request, "user", None)
        return build_tts_preview_response(
            json_data,
            shifu_bid=preview_shifu_bid,
            request_user_id=str(getattr(request_user, "user_id", "") or "").strip(),
        )
