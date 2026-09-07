"""Constrained ephemeral-token contracts for browser-direct Gemini Live."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import BoundedSemaphore, Event
from time import monotonic

import pytest
from flaskr.service.learn import gemini_live_token as token_provider
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


def test_private_mint_has_wall_clock_deadline_and_discards_late_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = Event()
    returned = Event()
    monkeypatch.setattr(
        token_provider, "GEMINI_LIVE_TOKEN_REQUEST_TIMEOUT_SECONDS", 0.02
    )
    monkeypatch.setattr(token_provider, "_TOKEN_REQUEST_SLOTS", BoundedSemaphore(1))

    def slow_post(*_args: object, **_kwargs: object) -> _Response:
        release.wait(1)
        returned.set()
        return _Response({"name": "auth_tokens/must-never-return"})

    started = monotonic()
    try:
        with pytest.raises(token_provider.GeminiLiveTokenTimeoutError):
            mint_gemini_live_ephemeral_token(
                api_key="private-key",
                voice_name="Kore",
                system_instruction="private-prompt",
                include_initial_history=False,
                request_post=slow_post,
            )
        assert monotonic() - started < 0.5
        assert not returned.is_set()
        # A hung private request continues occupying its worker slot; a timeout
        # cannot create an unbounded tail of background mint threads.
        with pytest.raises(GeminiLiveTokenError):
            mint_gemini_live_ephemeral_token(
                api_key="private-key",
                voice_name="Kore",
                system_instruction="private-prompt",
                include_initial_history=False,
                request_post=lambda *_a, **_k: pytest.fail("worker slot bypassed"),
            )
    finally:
        release.set()
        assert returned.wait(1)


def test_thread_start_failure_releases_private_worker_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slots = BoundedSemaphore(1)
    monkeypatch.setattr(token_provider, "_TOKEN_REQUEST_SLOTS", slots)
    monkeypatch.setattr(
        token_provider.Thread,
        "start",
        lambda _thread: (_ for _ in ()).throw(RuntimeError("no thread")),
    )
    with pytest.raises(GeminiLiveTokenError):
        mint_gemini_live_ephemeral_token(
            api_key="private-key",
            voice_name="Kore",
            system_instruction="private-prompt",
            include_initial_history=False,
            request_post=lambda *_a, **_k: pytest.fail("failed start reached provider"),
        )
    assert slots.acquire(blocking=False)
    slots.release()


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
    assert calls[0]["allow_redirects"] is False
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
    assert set(setup).issubset(locked_fields)
    assert "sessionResumption" not in setup
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


@pytest.mark.parametrize(
    ("api_base_url", "endpoint"),
    [
        (None, GEMINI_LIVE_AUTH_TOKEN_ENDPOINT),
        ("", GEMINI_LIVE_AUTH_TOKEN_ENDPOINT),
        ("  \n ", GEMINI_LIVE_AUTH_TOKEN_ENDPOINT),
        ("https://generativelanguage.googleapis.com/", GEMINI_LIVE_AUTH_TOKEN_ENDPOINT),
        (
            "https://generativelanguage.googleapis.com/v1beta/",
            GEMINI_LIVE_AUTH_TOKEN_ENDPOINT,
        ),
        ("https://proxy.example.com", "https://proxy.example.com/v1beta/auth_tokens"),
        (
            " https://proxy.example.com/google/ ",
            "https://proxy.example.com/google/v1beta/auth_tokens",
        ),
        (
            "https://proxy.example.com:8443/api/google",
            "https://proxy.example.com:8443/api/google/v1beta/auth_tokens",
        ),
        (
            "https://proxy.example.com/google/v1beta",
            "https://proxy.example.com/google/v1beta/auth_tokens",
        ),
        (
            " https://proxy.example.com:8443/google/v1beta/ ",
            "https://proxy.example.com:8443/google/v1beta/auth_tokens",
        ),
        (
            "https://proxy.example.com/v1beta/google",
            "https://proxy.example.com/v1beta/google/v1beta/auth_tokens",
        ),
        (
            "https://v1beta",
            "https://v1beta/v1beta/auth_tokens",
        ),
    ],
)
def test_token_uses_server_configured_api_base_without_changing_browser_endpoint(
    api_base_url: str | None, endpoint: str
) -> None:
    calls: list[dict[str, object]] = []

    def request_post(url: str, **kwargs: object) -> _Response:
        calls.append({"url": url, **kwargs})
        return _Response({"name": "auth_tokens/browser-only"})

    token = mint_gemini_live_ephemeral_token(
        api_key="server-api-key",
        api_base_url=api_base_url,
        voice_name="Kore",
        system_instruction="Private prompt",
        include_initial_history=False,
        request_post=request_post,
    )

    assert token.token == "auth_tokens/browser-only"
    assert len(calls) == 1
    assert calls[0]["url"] == endpoint
    assert calls[0]["headers"]["x-goog-api-key"] == "server-api-key"
    assert calls[0]["allow_redirects"] is False
    assert GEMINI_LIVE_CONSTRAINED_ENDPOINT == (
        "wss://generativelanguage.googleapis.com/ws/"
        "google.ai.generativelanguage.v1beta.GenerativeService."
        "BidiGenerateContentConstrained"
    )


@pytest.mark.parametrize(
    "api_base_url",
    [
        "/",
        "http://proxy.example.com/google",
        "wss://proxy.example.com/google",
        "https:///google",
        "https://user:password@proxy.example.com/google",
        "https://proxy.example.com/google?key=secret",
        "https://proxy.example.com/google?",
        "https://proxy.example.com/google#fragment",
        "https://proxy.example.com/google#",
        "https://[invalid",
        "https://proxy.example.com:invalid/google",
    ],
)
def test_token_rejects_unsafe_configured_url_before_sending_credentials(
    api_base_url: str,
) -> None:
    with pytest.raises(GeminiLiveTokenError, match=r"^invalid_configuration$"):
        mint_gemini_live_ephemeral_token(
            api_key="server-api-key",
            api_base_url=api_base_url,
            voice_name="Kore",
            system_instruction="Private prompt",
            include_initial_history=False,
            request_post=lambda *_args, **_kwargs: pytest.fail(
                "Unsafe configuration was sent"
            ),
        )


@pytest.mark.parametrize("instruction", ["", "  \n "])
def test_token_allows_blank_prompt_without_unlocking_browser_instruction(
    instruction: str,
) -> None:
    calls: list[dict[str, object]] = []

    def request_post(_url: str, **kwargs: object) -> _Response:
        calls.append(kwargs)
        return _Response({"name": "auth_tokens/browser-only"})

    token = mint_gemini_live_ephemeral_token(
        api_key="server-api-key",
        voice_name="Kore",
        system_instruction=instruction,
        include_initial_history=False,
        request_post=request_post,
    )

    assert token.token == "auth_tokens/browser-only"
    payload = calls[0]["json"]
    assert "systemInstruction" in payload["fieldMask"].split(",")
    assert "systemInstruction" not in payload["bidiGenerateContentSetup"]
    assert set(payload["bidiGenerateContentSetup"]).issubset(
        payload["fieldMask"].split(",")
    )


@pytest.mark.parametrize("missing", ["api_key", "model", "voice_name"])
def test_token_still_requires_credentials_model_and_voice(missing: str) -> None:
    options = {
        "api_key": "server-api-key",
        "model": "gemini-3.1-flash-live-preview",
        "voice_name": "Kore",
        "system_instruction": "",
    }
    options[missing] = "  "
    with pytest.raises(GeminiLiveTokenError, match="invalid_configuration"):
        mint_gemini_live_ephemeral_token(
            **options,
            include_initial_history=False,
            request_post=lambda *_args, **_kwargs: pytest.fail(
                "Invalid configuration was sent"
            ),
        )


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
    assert setup["setup"]["sessionResumption"] == {}
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


@pytest.mark.parametrize("api_base_url", [None, "https://proxy.example.com/google"])
def test_token_failure_does_not_expose_provider_details_or_try_another_host(
    api_base_url: str | None,
) -> None:
    calls: list[str] = []

    def request_post(url: str, **_kwargs: object) -> _Response:
        calls.append(url)
        return _Response({}, raises=True)

    with pytest.raises(GeminiLiveTokenError, match="token_provision_failed"):
        mint_gemini_live_ephemeral_token(
            api_key="server-api-key",
            api_base_url=api_base_url,
            voice_name="Kore",
            system_instruction="Prompt",
            include_initial_history=False,
            request_post=request_post,
        )
    assert calls == [
        f"{api_base_url}/v1beta/auth_tokens"
        if api_base_url
        else GEMINI_LIVE_AUTH_TOKEN_ENDPOINT
    ]
