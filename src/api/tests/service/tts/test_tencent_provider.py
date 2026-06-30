import base64
import hashlib
import hmac
import json

import pytest


class _FakeSSEStreamingResponse:
    def __init__(self, lines, *, headers=None):
        self._lines = list(lines)
        self.headers = headers or {"content-type": "text/event-stream"}
        self.closed = False

    def raise_for_status(self):
        return None

    def iter_lines(self, decode_unicode=True):
        _ = decode_unicode
        for line in self._lines:
            yield line

    def close(self):
        self.closed = True


def _expected_tc3_authorization(*, payload_json: str, timestamp: int) -> str:
    host = "trtc.ai.tencentcloudapi.com"
    service = "trtc"
    secret_id = "secret-id"
    secret_key = "secret-key"
    date = "2023-07-06"
    algorithm = "TC3-HMAC-SHA256"
    canonical_headers = (
        f"content-type:application/json\nhost:{host}\nx-tc-action:texttospeechsse\n"
    )
    signed_headers = "content-type;host;x-tc-action"
    hashed_payload = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    canonical_request = "\n".join(
        [
            "POST",
            "/",
            "",
            canonical_headers,
            signed_headers,
            hashed_payload,
        ]
    )
    credential_scope = f"{date}/{service}/tc3_request"
    string_to_sign = "\n".join(
        [
            algorithm,
            str(timestamp),
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )

    def sign(key, msg):
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    secret_date = sign(("TC3" + secret_key).encode("utf-8"), date)
    secret_service = sign(secret_date, service)
    secret_signing = sign(secret_service, "tc3_request")
    signature = hmac.new(
        secret_signing,
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return (
        f"{algorithm} Credential={secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )


def _patch_tencent_config(monkeypatch, tencent_provider):
    config = {
        "TENCENT_TTS_APP_ID": "1400000000",
        "TENCENT_TTS_SECRET_ID": "secret-id",
        "TENCENT_TTS_SECRET_KEY": "secret-key",
    }
    monkeypatch.setattr(
        tencent_provider,
        "get_config",
        lambda key, default=None: config.get(key, default),
    )


def test_tencent_sse_tc3_headers_sign_exact_request_payload():
    from flaskr.api.tts.tencent_provider import (
        build_tencent_tc3_headers,
        encode_tencent_sse_payload,
    )

    payload = {
        "AlignmentMode": 1,
        "AudioFormat": {"Bitrate": 128, "Format": "pcm", "SampleRate": 16000},
        "Model": "flow_01_turbo",
        "SdkAppId": 1400000000,
        "Text": "你好呀",
        "Voice": {"Pitch": 0, "Speed": 1.0, "VoiceId": "v-female-R2s4N9qJ"},
    }
    payload_json = encode_tencent_sse_payload(payload)

    headers = build_tencent_tc3_headers(
        payload_json=payload_json,
        secret_id="secret-id",
        secret_key="secret-key",
        timestamp=1688610905,
    )

    assert payload_json == (
        '{"AlignmentMode":1,"AudioFormat":{"Bitrate":128,"Format":"pcm",'
        '"SampleRate":16000},"Model":"flow_01_turbo","SdkAppId":1400000000,'
        '"Text":"你好呀","Voice":{"Pitch":0,"Speed":1.0,'
        '"VoiceId":"v-female-R2s4N9qJ"}}'
    )
    assert headers["Host"] == "trtc.ai.tencentcloudapi.com"
    assert headers["Accept"] == "text/event-stream"
    assert headers["Content-Type"] == "application/json"
    assert headers["X-TC-Action"] == "TextToSpeechSSE"
    assert headers["X-TC-Version"] == "2019-07-22"
    assert headers["X-TC-Region"] == "ap-guangzhou"
    assert headers["X-TC-Timestamp"] == "1688610905"
    assert headers["Authorization"] == _expected_tc3_authorization(
        payload_json=payload_json,
        timestamp=1688610905,
    )


def test_tencent_provider_config_validation_and_explicit_only(monkeypatch):
    import flaskr.api.tts as tts_api
    import flaskr.api.tts.tencent_provider as tencent_provider
    from flaskr.common.config import ENV_VARS
    from flaskr.service.tts.validation import validate_tts_settings_strict

    expected_config_keys = {
        "TENCENT_TTS_APP_ID",
        "TENCENT_TTS_SECRET_ID",
        "TENCENT_TTS_SECRET_KEY",
    }
    assert {key for key in ENV_VARS if key.startswith("TENCENT_TTS_")} == (
        expected_config_keys
    )

    _patch_tencent_config(monkeypatch, tencent_provider)
    monkeypatch.setattr(tts_api, "get_config", lambda key, default=None: "")
    tts_api._provider_instances.clear()

    provider = tencent_provider.TencentTTSProvider()
    provider_config = provider.get_provider_config()

    assert provider.is_configured() is True
    assert provider.provider_name == "tencent"
    assert provider_config.name == "tencent"
    assert provider_config.label == "腾讯云语音合成"
    assert provider_config.speed.default == 0
    assert provider_config.pitch.min == provider_config.pitch.max == 0
    assert provider_config.voices == tencent_provider.TENCENT_PREMIUM_VOICES
    assert all("精品音色" in voice["label"] for voice in provider_config.voices)
    assert "101001" not in {voice["value"] for voice in provider_config.voices}
    assert "happy" in {emotion["value"] for emotion in provider_config.emotions}

    assert tts_api.get_tts_provider("tencent").provider_name == "tencent"
    assert tts_api._auto_detect_provider_name() != "tencent"
    assert tts_api.is_tts_configured("tencent") is True
    assert tts_api.is_tts_configured() is False

    validated = validate_tts_settings_strict(
        provider="tencent",
        model="",
        voice_id="v-female-R2s4N9qJ",
        speed=0,
        pitch=0,
        emotion="happy",
    )
    assert validated.provider == "tencent"
    assert validated.model == ""

    with pytest.raises(Exception):
        validate_tts_settings_strict(
            provider="tencent",
            model="",
            voice_id="101001",
            speed=0,
            pitch=0,
            emotion="",
        )


def test_tencent_provider_stream_synthesize_parses_sse_audio_and_alignments(
    monkeypatch,
):
    import flaskr.api.tts.tencent_provider as tencent_provider
    from flaskr.api.tts.base import AudioSettings, VoiceSettings

    _patch_tencent_config(monkeypatch, tencent_provider)
    post_calls = []

    def fake_post(url, data, headers, stream, timeout):
        post_calls.append(
            {
                "url": url,
                "data": data,
                "headers": headers,
                "stream": stream,
                "timeout": timeout,
            }
        )
        return _FakeSSEStreamingResponse(
            [
                "event: message",
                "data: "
                + json.dumps(
                    {
                        "Response": {
                            "RequestId": "request-1",
                            "Audio": base64.b64encode(b"audio-bytes").decode("ascii"),
                            "Final": 1,
                            "Result": {
                                "Subtitles": [
                                    {
                                        "Text": "你",
                                        "BeginTime": 0,
                                        "EndTime": 120,
                                        "BeginIndex": 0,
                                        "EndIndex": 1,
                                    },
                                    {
                                        "Text": "好",
                                        "BeginTime": 120,
                                        "EndTime": 240,
                                        "BeginIndex": 1,
                                        "EndIndex": 2,
                                    },
                                ]
                            },
                        }
                    }
                ),
            ]
        )

    monkeypatch.setattr(tencent_provider.requests, "post", fake_post)

    chunks = list(
        tencent_provider.TencentTTSProvider().stream_synthesize(
            "你好",
            voice_settings=VoiceSettings(
                voice_id="v-female-R2s4N9qJ",
                speed=0,
                pitch=0,
            ),
            audio_settings=AudioSettings(format="mp3", sample_rate=16000),
        )
    )

    assert len(chunks) == 1
    assert chunks[0].audio_data == b"audio-bytes"
    assert chunks[0].is_final is True
    assert chunks[0].request_id == "request-1"
    assert chunks[0].subtitles[0]["Text"] == "你"
    assert post_calls[0]["url"] == "https://trtc.ai.tencentcloudapi.com"
    assert post_calls[0]["stream"] is True
    assert post_calls[0]["headers"]["X-TC-Action"] == "TextToSpeechSSE"
    payload = json.loads(post_calls[0]["data"])
    assert payload["Text"] == "你好"
    assert payload["SdkAppId"] == 1400000000
    assert payload["Voice"]["VoiceId"] == "v-female-R2s4N9qJ"
    assert payload["AudioFormat"]["Format"] == "pcm"
    assert payload["Model"] == "flow_01_turbo"
    assert payload["AlignmentMode"] == 1


def test_tencent_provider_synthesize_collects_audio_and_sentence_subtitles(
    monkeypatch,
):
    import flaskr.api.tts.tencent_provider as tencent_provider
    from flaskr.api.tts.base import AudioSettings, VoiceSettings

    _patch_tencent_config(monkeypatch, tencent_provider)

    def fake_post(url, data, headers, stream, timeout):
        _ = url, data, headers, stream, timeout
        return _FakeSSEStreamingResponse(
            [
                "data: "
                + json.dumps(
                    {
                        "Type": "chunk",
                        "RequestId": "request-1",
                        "Audio": base64.b64encode(b"audio-").decode("ascii"),
                        "Seq": 0,
                        "Alignments": [
                            {
                                "TimeBeginMs": 0,
                                "TimeEndMs": 300,
                                "TextBegin": 0,
                                "TextEnd": 2,
                            }
                        ],
                        "IsEnd": False,
                    }
                ),
                "data: "
                + json.dumps(
                    {
                        "Type": "chunk",
                        "RequestId": "request-1",
                        "Audio": base64.b64encode(b"bytes").decode("ascii"),
                        "Seq": 1,
                        "Alignments": [
                            {
                                "TimeBeginMs": 300,
                                "TimeEndMs": 600,
                                "TextBegin": 3,
                                "TextEnd": 5,
                            }
                        ],
                        "IsEnd": True,
                    }
                ),
            ]
        )

    monkeypatch.setattr(tencent_provider.requests, "post", fake_post)
    monkeypatch.setattr(
        tencent_provider,
        "concat_audio_best_effort",
        lambda segments, output_format="mp3": b"".join(segments),
    )
    monkeypatch.setattr(
        tencent_provider,
        "_export_tencent_pcm_to_mp3",
        lambda audio_data, sample_rate: audio_data,
    )
    monkeypatch.setattr(
        tencent_provider,
        "try_get_audio_duration_ms",
        lambda audio_data, format="mp3": 600 if audio_data else 0,
    )

    result = tencent_provider.TencentTTSProvider().synthesize(
        "你好。世界！",
        voice_settings=VoiceSettings(
            voice_id="v-female-R2s4N9qJ",
            speed=0,
            pitch=0,
        ),
        audio_settings=AudioSettings(format="mp3", sample_rate=16000),
    )

    assert result.audio_data == b"audio-bytes"
    assert result.duration_ms == 600
    assert result.sample_rate == 16000
    assert result.format == "mp3"
    assert result.word_count == 6
    assert result.usage_characters == 6
    assert [cue["text"] for cue in result.subtitle_cues] == ["你好。", "世界！"]


def test_tencent_provider_raises_sanitized_error_on_sse_error(monkeypatch):
    import flaskr.api.tts.tencent_provider as tencent_provider

    _patch_tencent_config(monkeypatch, tencent_provider)

    def fake_post(url, data, headers, stream, timeout):
        _ = url, data, headers, stream, timeout
        return _FakeSSEStreamingResponse(
            [
                "data: "
                + json.dumps(
                    {
                        "Response": {
                            "RequestId": "request-1",
                            "Error": {
                                "Code": "InvalidParameter.Voice",
                                "Message": "voice is not available",
                            },
                        }
                    }
                )
            ]
        )

    monkeypatch.setattr(tencent_provider.requests, "post", fake_post)

    with pytest.raises(
        ValueError,
        match="Tencent TTS error InvalidParameter.Voice",
    ):
        list(
            tencent_provider.TencentTTSProvider().stream_synthesize(
                "hello",
                voice_settings=tencent_provider.TencentTTSProvider().get_default_voice_settings(),
                audio_settings=tencent_provider.TencentTTSProvider().get_default_audio_settings(),
            )
        )
