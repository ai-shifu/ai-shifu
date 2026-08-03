import pytest

from flaskr.service.tts.streaming_tts import _is_retryable_empty_audio_error


@pytest.mark.parametrize(
    "provider",
    ["", "tencent", "tencent_texttovoice", "volcengine"],
)
def test_empty_audio_is_retryable_for_all_tts_providers(provider):
    error = ValueError(f"No audio data received from provider {provider or 'auto'}")
    assert _is_retryable_empty_audio_error(error, provider) is True


def test_empty_audio_retry_matches_tencent_texttovoice_error_message():
    # The exact message raised by tencent_texttovoice_provider must keep
    # matching the retry detector's substring.
    error = ValueError("No audio data received from Tencent TextToVoice")
    assert _is_retryable_empty_audio_error(error, "tencent_texttovoice") is True


def test_non_empty_audio_errors_are_not_retryable():
    error = ValueError("Tencent TextToVoice error AuthFailure: bad secret")
    assert _is_retryable_empty_audio_error(error, "tencent_texttovoice") is False


def test_unknown_provider_is_not_retryable():
    error = ValueError("No audio data received")
    assert _is_retryable_empty_audio_error(error, "some_future_provider") is False
