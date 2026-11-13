"""Volcengine (豆包声音复刻 2.0) cloned-voice verification helpers.

Unlike MiniMax, the cloning itself happens outside the platform: an operator
trains a pre-purchased console slot (``S_xxxxxxxxxx`` speaker id) with the standalone
toolkit, then registers the resulting id here. The platform only needs to
verify that a speaker id is trained and usable, which the free voice
status API answers — no paid test synthesis is required (Volcengine also has
no MiniMax-style 168h keep-alive expiry).

Synthesis with these voices goes through the ``volcengine`` WS provider with
``X-Api-Resource-Id`` set to ``seed-icl-2.0``.
"""

from __future__ import annotations

from uuid import uuid4

import requests
from flaskr.api.tts.volcengine_provider import (
    get_volcengine_tts_api_key_headers,
    is_volcengine_cloned_speaker_id,
)
from flaskr.service.common.models import raise_param_error

VOLCENGINE_VOICE_STATUS_URL = "https://openspeech.bytedance.com/api/v3/tts/get_voice"

# Voice training status enum. Synthesis is possible at Success or Active.
VOLCENGINE_VOICE_STATUS_NOT_FOUND = 0
VOLCENGINE_VOICE_STATUS_TRAINING = 1
VOLCENGINE_VOICE_STATUS_SUCCESS = 2
VOLCENGINE_VOICE_STATUS_FAILED = 3
VOLCENGINE_VOICE_STATUS_ACTIVE = 4
VOLCENGINE_VOICE_STATUS_OK = {
    VOLCENGINE_VOICE_STATUS_SUCCESS,
    VOLCENGINE_VOICE_STATUS_ACTIVE,
}

_STATUS_TIMEOUT = (10, 60)


def is_valid_volcengine_custom_voice_id(value: str) -> bool:
    """Return whether valid volcengine custom voice ID."""
    return is_volcengine_cloned_speaker_id(value)


def query_volcengine_voice_status(voice_id: str) -> int:
    """Return the voice training status for a speaker id (free API call)."""
    api_key_headers = get_volcengine_tts_api_key_headers()
    if not api_key_headers:
        raise_param_error("Set VOLCENGINE_TTS_API_KEY to verify Volcengine voices")

    try:
        response = requests.post(
            VOLCENGINE_VOICE_STATUS_URL,
            headers={
                **api_key_headers,
                "Content-Type": "application/json",
                "X-Api-Request-Id": str(uuid4()),
            },
            json={"speaker_id": (voice_id or "").strip()},
            timeout=_STATUS_TIMEOUT,
            # Requests can forward custom authentication headers on redirects.
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        # Provider unreachable / timed out: fail through the controlled
        # parameter-error path instead of surfacing a raw HTTP 500.
        raise_param_error(f"Volcengine voice status query failed: {exc}")
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if response.status_code >= 300:
        detail = (
            str(payload.get("message") or "")
            if isinstance(payload, dict)
            else (response.text or "")[:200]
        )
        raise_param_error(
            "Volcengine voice status query failed: "
            f"HTTP {response.status_code} - {detail}"
        )
    if not isinstance(payload, dict):
        raise_param_error("Volcengine voice status query returned invalid JSON")
    status_code = int(payload.get("code") or 0)
    if status_code != 0:
        raise_param_error(
            "Volcengine voice status query failed: "
            f"{status_code} - {payload.get('message') or ''}"
        )
    return int(payload.get("status") or 0)


def verify_volcengine_voice_id(voice_id: str) -> None:
    """Reject a speaker id that is not trained/usable on the platform account."""
    status = query_volcengine_voice_status(voice_id)
    if status not in VOLCENGINE_VOICE_STATUS_OK:
        raise_param_error(f"voice_id verification failed: status={status}")
