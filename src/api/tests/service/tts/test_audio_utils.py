import io

from flaskr.service.tts import audio_utils


class _FakeSegment:
    append_crossfades: list[int] = []

    def __init__(self, duration_ms: int):
        self.duration_ms = duration_ms

    def __len__(self):
        return self.duration_ms

    def append(self, other, crossfade=0):
        _FakeSegment.append_crossfades.append(crossfade)
        if crossfade > len(self):
            raise ValueError(
                f"Crossfade is longer than original AudioSegment "
                f"({crossfade}ms > {len(self)}ms)"
            )
        if crossfade > len(other):
            raise ValueError(
                f"Crossfade is longer than the appended AudioSegment "
                f"({crossfade}ms > {len(other)}ms)"
            )
        return _FakeSegment(self.duration_ms + len(other) - crossfade)

    def export(self, output_io, format="mp3", bitrate="128k"):
        _ = (format, bitrate)
        output_io.write(f"duration={self.duration_ms}".encode("utf-8"))


class _FakeAudioSegment:
    @staticmethod
    def from_mp3(segment_io: io.BytesIO):
        duration = int(segment_io.getvalue().decode("utf-8"))
        return _FakeSegment(duration)


def test_concat_audio_mp3_caps_crossfade_for_short_segments(monkeypatch):
    _FakeSegment.append_crossfades.clear()
    monkeypatch.setattr(audio_utils, "AudioSegment", _FakeAudioSegment, raising=False)
    monkeypatch.setattr(audio_utils, "PYDUB_AVAILABLE", True)

    output = audio_utils.concat_audio_mp3([b"100", b"2", b"80"])

    assert _FakeSegment.append_crossfades == [2, 50]
    assert output == b"duration=130"
