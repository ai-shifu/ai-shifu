"""Mint constrained Gemini Live ephemeral tokens for browser sessions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import requests
from flaskr.util.datetime import now_utc, to_utc_iso

from .live_follow_up_config import GEMINI_LIVE_MODEL_ID

if TYPE_CHECKING:
    from collections.abc import Callable

GEMINI_LIVE_AUTH_TOKEN_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/auth_tokens"  # noqa: S105 - public API endpoint, not a credential
)
GEMINI_LIVE_CONSTRAINED_ENDPOINT = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService."
    "BidiGenerateContentConstrained"
)
GEMINI_LIVE_INPUT_MIME_TYPE = "audio/pcm;rate=16000"
GEMINI_LIVE_MAX_INPUT_FRAME_BYTES = 8192
GEMINI_LIVE_TOKEN_CONNECT_SECONDS = 30
GEMINI_LIVE_TOKEN_LIFETIME_SECONDS = 15 * 60
GEMINI_LIVE_TOKEN_REQUEST_TIMEOUT_SECONDS = 10.0
_ERROR_INVALID_CONFIGURATION = "invalid_configuration"
_ERROR_INVALID_RESPONSE = "invalid_token_response"
_ERROR_PROVISION_FAILED = "token_provision_failed"
_LOCKED_BIDI_SETUP_FIELDS = (
    "model",
    "generationConfig",
    "systemInstruction",
    "tools",
    "inputAudioTranscription",
    "outputAudioTranscription",
    "realtimeInputConfig",
    "contextWindowCompression",
    "historyConfig",
)


class GeminiLiveTokenError(RuntimeError):
    """Signal a bounded ephemeral-token provisioning failure."""


@dataclass(frozen=True)
class GeminiLiveHistoryTurn:
    """One user or model turn used to seed a new Live session."""

    role: str
    text: str


@dataclass(frozen=True)
class GeminiLiveEphemeralToken:
    """Short-lived browser credential and its bounded validity window."""

    token: str
    expires_at: datetime
    new_session_expires_at: datetime


def _qualified_model(model: str) -> str:
    normalized = str(model or "").strip()
    return normalized if normalized.startswith("models/") else f"models/{normalized}"


def _token_endpoint(api_base_url: str | None) -> str:
    """Use the server's Gemini base URL, preserving any reverse-proxy prefix."""
    base_url = str(api_base_url or "").strip()
    if not base_url:
        return GEMINI_LIVE_AUTH_TOKEN_ENDPOINT
    base_url = base_url.rstrip("/")
    try:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.port == 0
            or parsed.username is not None
            or parsed.password is not None
            or "?" in base_url
            or "#" in base_url
        ):
            raise GeminiLiveTokenError(_ERROR_INVALID_CONFIGURATION)
    except ValueError:
        raise GeminiLiveTokenError(_ERROR_INVALID_CONFIGURATION) from None
    if parsed.path.endswith("/v1beta"):
        return f"{base_url}/auth_tokens"
    return f"{base_url}/v1beta/auth_tokens"


def _bidi_setup(
    *,
    model: str,
    voice_name: str,
    system_instruction: str,
    include_initial_history: bool,
) -> dict[str, Any]:
    return {
        "model": _qualified_model(model),
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": voice_name},
                }
            },
            "thinkingConfig": {"thinkingLevel": "MINIMAL"},
        },
        # Omit empty content while retaining systemInstruction in the token's
        # field mask, so the browser still cannot supply its own instruction.
        **(
            {"systemInstruction": {"parts": [{"text": system_instruction}]}}
            if system_instruction
            else {}
        ),
        "tools": [],
        "realtimeInputConfig": {
            "automaticActivityDetection": {
                "disabled": False,
                "startOfSpeechSensitivity": "START_SENSITIVITY_HIGH",
                "endOfSpeechSensitivity": "END_SENSITIVITY_LOW",
                "prefixPaddingMs": 100,
                "silenceDurationMs": 700,
            },
            "activityHandling": "START_OF_ACTIVITY_INTERRUPTS",
            "turnCoverage": "TURN_INCLUDES_ONLY_ACTIVITY",
        },
        "inputAudioTranscription": {},
        "outputAudioTranscription": {},
        "contextWindowCompression": {
            "triggerTokens": "25000",
            "slidingWindow": {"targetTokens": "8000"},
        },
        "historyConfig": {
            "initialHistoryInClientContent": include_initial_history,
        },
    }


def build_gemini_live_client_setup(
    *,
    model: str,
    voice_name: str,
    include_initial_history: bool,
    resumption_handle: str | None = None,
) -> dict[str, Any]:
    """Return the non-secret setup the browser sends on the constrained socket.

    The effective system instruction is locked into the ephemeral token and is
    deliberately absent from this browser-visible payload.
    """
    setup: dict[str, Any] = {
        "model": _qualified_model(model),
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": voice_name},
                }
            },
            "thinkingConfig": {"thinkingLevel": "MINIMAL"},
        },
        "realtimeInputConfig": {
            "automaticActivityDetection": {
                "disabled": False,
                "startOfSpeechSensitivity": "START_SENSITIVITY_HIGH",
                "endOfSpeechSensitivity": "END_SENSITIVITY_LOW",
                "prefixPaddingMs": 100,
                "silenceDurationMs": 700,
            },
            "activityHandling": "START_OF_ACTIVITY_INTERRUPTS",
            "turnCoverage": "TURN_INCLUDES_ONLY_ACTIVITY",
        },
        "inputAudioTranscription": {},
        "outputAudioTranscription": {},
        "contextWindowCompression": {
            "triggerTokens": "25000",
            "slidingWindow": {"targetTokens": "8000"},
        },
        "sessionResumption": (
            {"handle": resumption_handle} if resumption_handle else {}
        ),
    }
    if include_initial_history and not resumption_handle:
        setup["historyConfig"] = {"initialHistoryInClientContent": True}
    return {"setup": setup}


def build_gemini_live_history_message(
    history: tuple[GeminiLiveHistoryTurn, ...],
) -> dict[str, Any] | None:
    """Build the initial clientContent frame without triggering generation."""
    turns: list[dict[str, Any]] = []
    for item in history:
        role = (
            "model" if item.role.strip().lower() in {"assistant", "model"} else "user"
        )
        text = item.text.strip()
        if not text:
            continue
        turns.append({"role": role, "parts": [{"text": text}]})
    if not turns:
        return None
    return {"clientContent": {"turns": turns, "turnComplete": True}}


def mint_gemini_live_ephemeral_token(
    *,
    api_key: str,
    api_base_url: str | None = None,
    model: str = GEMINI_LIVE_MODEL_ID,
    voice_name: str,
    system_instruction: str,
    include_initial_history: bool,
    current_time: datetime | None = None,
    request_post: Callable[..., requests.Response] = requests.post,
) -> GeminiLiveEphemeralToken:
    """Provision one constrained, one-use credential without exposing the key."""
    normalized_key = str(api_key or "").strip()
    normalized_model = str(model or "").strip()
    normalized_voice = str(voice_name or "").strip()
    normalized_instruction = str(system_instruction or "").strip()
    if not all((normalized_key, normalized_model, normalized_voice)):
        raise GeminiLiveTokenError(_ERROR_INVALID_CONFIGURATION)
    endpoint = _token_endpoint(api_base_url)

    issued_at = current_time or now_utc()
    expires_at = issued_at + timedelta(seconds=GEMINI_LIVE_TOKEN_LIFETIME_SECONDS)
    new_session_expires_at = issued_at + timedelta(
        seconds=GEMINI_LIVE_TOKEN_CONNECT_SECONDS
    )
    payload = {
        "uses": 1,
        "expireTime": to_utc_iso(expires_at),
        "newSessionExpireTime": to_utc_iso(new_session_expires_at),
        # Keep every security-sensitive top-level setup field server-owned.
        # Exclude session resumption from both the constraints and their mask:
        # Gemini rejects setup fields outside the mask, and the browser must
        # remain free to add the latest server-issued handle after a GoAway.
        "fieldMask": ",".join(_LOCKED_BIDI_SETUP_FIELDS),
        "bidiGenerateContentSetup": _bidi_setup(
            model=normalized_model,
            voice_name=normalized_voice,
            system_instruction=normalized_instruction,
            include_initial_history=include_initial_history,
        ),
    }
    try:
        response = request_post(
            endpoint,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": normalized_key,
            },
            json=payload,
            timeout=GEMINI_LIVE_TOKEN_REQUEST_TIMEOUT_SECONDS,
            # A redirect must not forward the custom API-key header elsewhere.
            allow_redirects=False,
        )
        response.raise_for_status()
        body = response.json()
    except Exception:
        raise GeminiLiveTokenError(_ERROR_PROVISION_FAILED) from None

    token = body.get("name") if isinstance(body, dict) else None
    if not isinstance(token, str) or not token.startswith("auth_tokens/"):
        raise GeminiLiveTokenError(_ERROR_INVALID_RESPONSE)
    if len(token) > 1024:
        raise GeminiLiveTokenError(_ERROR_INVALID_RESPONSE)
    return GeminiLiveEphemeralToken(
        token=token,
        expires_at=expires_at,
        new_session_expires_at=new_session_expires_at,
    )
