"""Volcengine (豆包声音复刻 2.0) cloned-voice verification helpers.

Unlike MiniMax, the cloning itself happens outside the platform: an operator
trains a pre-purchased console slot (``S_xxx`` speaker id) with the standalone
toolkit, then registers the resulting id here. The platform only needs to
verify that a speaker id is trained and usable, which the free ``mega_tts``
status API answers — no paid test synthesis is required (Volcengine also has
no MiniMax-style 168h keep-alive expiry).

Synthesis with these voices goes through the ``volcengine`` WS provider with
``X-Api-Resource-Id`` = :data:`VOLCENGINE_ICL_RESOURCE_ID` (the provider
treats its ``model`` parameter as the resource id).
"""

from __future__ import annotations

import requests

from flaskr.api.tts.volcengine_provider import (
    VOLCENGINE_ICL_RESOURCE_ID,
    is_volcengine_cloned_speaker_id,
)
from flaskr.common.config import get_config
from flaskr.service.common.models import raise_param_error

VOLCENGINE_MEGA_TTS_STATUS_URL = (
    "https://openspeech.bytedance.com/api/v1/mega_tts/status"
)

# mega_tts training status enum. Synthesis is possible at Success or Active.
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
    return is_volcengine_cloned_speaker_id(value)


def query_volcengine_voice_status(voice_id: str) -> int:
    """Return the mega_tts training status for a speaker id (free API call)."""
    appid = str(get_config("VOLCENGINE_TTS_APP_KEY") or "").strip()
    token = str(get_config("VOLCENGINE_TTS_ACCESS_KEY") or "").strip()
    if not appid or not token:
        raise_param_error("Volcengine TTS credentials are not configured")

    response = requests.post(
        VOLCENGINE_MEGA_TTS_STATUS_URL,
        headers={
            "Authorization": f"Bearer;{token}",
            "Resource-Id": VOLCENGINE_ICL_RESOURCE_ID,
            "Content-Type": "application/json",
        },
        json={"appid": appid, "speaker_id": (voice_id or "").strip()},
        timeout=_STATUS_TIMEOUT,
    )
    # Volcengine answers 4xx with a JSON body for bad speaker ids / missing
    # grants; surface that as a parameter error instead of an opaque HTTPError.
    if response.status_code >= 400:
        try:
            detail = str((response.json() or {}).get("message") or "")
        except ValueError:
            detail = (response.text or "")[:200]
        raise_param_error(
            "Volcengine voice status query failed: "
            f"HTTP {response.status_code} - {detail}"
        )
    message = response.json()
    base_resp = message.get("BaseResp") or {}
    status_code = int(base_resp.get("StatusCode") or 0)
    if status_code != 0:
        raise_param_error(
            "Volcengine voice status query failed: "
            f"{status_code} - {base_resp.get('StatusMessage') or ''}"
        )
    return int(message.get("status") or 0)


def verify_volcengine_voice_id(voice_id: str) -> None:
    """Reject a speaker id that is not trained/usable on the platform account."""
    status = query_volcengine_voice_status(voice_id)
    if status not in VOLCENGINE_VOICE_STATUS_OK:
        raise_param_error(f"voice_id verification failed: status={status}")
