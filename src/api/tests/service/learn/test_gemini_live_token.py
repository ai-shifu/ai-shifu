"""Constrained ephemeral-token contracts for browser-direct Gemini Live."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from flaskr.service.learn.gemini_live_token import (
    GEMINI_LIVE_AUTH_TOKEN_ENDPOINT,
    GEMINI_LIVE_CONSTRAINED_ENDPOINT,
    GeminiLiveHistoryTurn,
    GeminiLiveTokenError,
    build_gemini_live_client_setup,
    build_gemini_live_history_message,
    mint_gemini_live_ephemeral_token,
)


class _Response:
    def __init__(self, body: object, *, raises: bool = False) -> None:
        self.body = body
        self.raises = raises

    def raise_for_status(self) -> None:
        if self.raises:
            message = "provider failure"
            raise RuntimeError(message)

    def json(self) -> object:
        return self.body


def test_token_is_one_use_short_lived_and_locks_server_configuration() -> None:
    issued_at = datetime(2026, 9, 3, 4, 5, 6, tzinfo=UTC)
    calls: list[dict[str, object]] = []

    def request_post(url: str, **kwargs: object) -> _Response:
        calls.append({"url": url, **kwargs})
        return _Response({"name": "auth_tokens/browser-only"})

    token = mint_gemini_live_ephemeral_token(
        api_key="server-api-key",
        model="gemini-3.1-flash-live-preview",
        voice_name="Kore",
        system_instruction="Private course prompt",
        include_initial_history=True,
        current_time=issued_at,
        request_post=request_post,
    )

    assert token.token == "auth_tokens/browser-only"
    assert token.expires_at == issued_at + timedelta(minutes=15)
    assert token.new_session_expires_at == issued_at + timedelta(seconds=30)
    assert calls[0]["url"] == GEMINI_LIVE_AUTH_TOKEN_ENDPOINT
    assert calls[0]["headers"] == {
        "Content-Type": "application/json",
        "x-goog-api-key": "server-api-key",
    }
    payload = calls[0]["json"]
    assert payload["uses"] == 1
    assert payload["expireTime"] == "2026-09-03T04:20:06Z"
    assert payload["newSessionExpireTime"] == "2026-09-03T04:05:36Z"
    locked_fields = set(payload["fieldMask"].split(","))
    assert locked_fields == {
        "model",
        "generationConfig",
        "systemInstruction",
        "tools",
        "inputAudioTranscription",
        "outputAudioTranscription",
        "realtimeInputConfig",
        "contextWindowCompression",
        "historyConfig",
    }
    assert "sessionResumption" not in locked_fields
    assert not any("_" in field for field in locked_fields)
    setup = payload["bidiGenerateContentSetup"]
    assert setup["model"] == "models/gemini-3.1-flash-live-preview"
    generation_config = setup["generationConfig"]
    assert generation_config["responseModalities"] == ["AUDIO"]
    assert generation_config["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"] == {
        "voiceName": "Kore"
    }
    assert setup["systemInstruction"] == {"parts": [{"text": "Private course prompt"}]}
    assert generation_config["thinkingConfig"] == {"thinkingLevel": "MINIMAL"}
    assert setup["inputAudioTranscription"] == {}
    assert setup["outputAudioTranscription"] == {}
    assert setup["historyConfig"] == {"initialHistoryInClientContent": True}
    assert setup["tools"] == []
    assert "proactivity" not in setup
    assert "safetySettings" not in setup


def test_browser_setup_omits_private_prompt_and_uses_constrained_endpoint() -> None:
    setup = build_gemini_live_client_setup(
        model="gemini-3.1-flash-live-preview",
        voice_name="Kore",
        include_initial_history=True,
    )

    assert GEMINI_LIVE_CONSTRAINED_ENDPOINT.startswith(
        "wss://generativelanguage.googleapis.com/ws/"
    )
    assert setup["setup"]["model"] == "models/gemini-3.1-flash-live-preview"
    assert "systemInstruction" not in setup["setup"]
    assert setup["setup"]["historyConfig"] == {"initialHistoryInClientContent": True}

    resumed = build_gemini_live_client_setup(
        model="gemini-3.1-flash-live-preview",
        voice_name="Kore",
        include_initial_history=True,
        resumption_handle="resume-1",
    )
    assert resumed["setup"]["sessionResumption"] == {"handle": "resume-1"}
    assert "historyConfig" not in resumed["setup"]


def test_history_maps_assistant_to_model_and_does_not_include_blank_turns() -> None:
    history = build_gemini_live_history_message(
        (
            GeminiLiveHistoryTurn(role="user", text=" Question "),
            GeminiLiveHistoryTurn(role="assistant", text=" Answer "),
            GeminiLiveHistoryTurn(role="user", text="  "),
        )
    )

    assert history == {
        "clientContent": {
            "turns": [
                {"role": "user", "parts": [{"text": "Question"}]},
                {"role": "model", "parts": [{"text": "Answer"}]},
            ],
            "turnComplete": True,
        }
    }


@pytest.mark.parametrize("body", [{}, {"name": "not-an-auth-token"}, []])
def test_token_rejects_malformed_provider_responses(body: object) -> None:
    with pytest.raises(GeminiLiveTokenError):
        mint_gemini_live_ephemeral_token(
            api_key="server-api-key",
            voice_name="Kore",
            system_instruction="Prompt",
            include_initial_history=False,
            request_post=lambda *_args, **_kwargs: _Response(body),
        )


def test_token_failure_does_not_expose_provider_details() -> None:
    with pytest.raises(GeminiLiveTokenError, match="token_provision_failed"):
        mint_gemini_live_ephemeral_token(
            api_key="server-api-key",
            voice_name="Kore",
            system_instruction="Prompt",
            include_initial_history=False,
            request_post=lambda *_args, **_kwargs: _Response({}, raises=True),
        )
