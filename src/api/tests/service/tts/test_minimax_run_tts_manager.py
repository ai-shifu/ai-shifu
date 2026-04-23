import pytest

from flaskr.api.tts import AudioSettings, TTSResult, VoiceSettings
from flaskr.service.tts.minimax_run_tts import (
    MinimaxRunTTSDisabled,
    MinimaxRunTTSManager,
)
from flaskr.service.tts.rpm_gate import TTSRpmQueueTimeout


class _FakeSession:
    def __init__(self, *, fail_once=False, queue_timeout=False):
        self.fail_once = fail_once
        self.queue_timeout = queue_timeout
        self.open_count = 0
        self.close_count = 0
        self.texts = []

    def open(self):
        self.open_count += 1

    def synthesize_segment(self, text):
        self.texts.append(text)
        if self.queue_timeout:
            raise TTSRpmQueueTimeout("queue timeout")
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("network down")
        return TTSResult(
            audio_data=f"audio:{text}".encode("utf-8"),
            duration_ms=100,
            sample_rate=24000,
            format="mp3",
            word_count=len(text),
        )

    def close(self):
        self.close_count += 1


def _manager(session_factory):
    return MinimaxRunTTSManager(
        voice_settings=VoiceSettings(voice_id="voice-a"),
        audio_settings=AudioSettings(format="mp3"),
        model="speech-2.8-turbo",
        session_factory=session_factory,
    )


def test_minimax_run_tts_manager_reconnects_once_and_resends_current_text():
    sessions = [_FakeSession(fail_once=True), _FakeSession()]
    created = []

    def session_factory():
        session = sessions.pop(0)
        created.append(session)
        return session

    manager = _manager(session_factory)

    result = manager.synthesize("hello")

    assert result.audio_data == b"audio:hello"
    assert sessions == []
    assert [session.texts for session in created] == [["hello"], ["hello"]]
    assert created[0].close_count == 1


def test_minimax_run_tts_manager_disables_run_after_queue_timeout():
    session = _FakeSession(queue_timeout=True)
    manager = _manager(lambda: session)

    with pytest.raises(TTSRpmQueueTimeout):
        manager.synthesize("hello")

    assert manager.is_disabled is True
    with pytest.raises(MinimaxRunTTSDisabled):
        manager.synthesize("later")
    assert session.texts == ["hello"]
