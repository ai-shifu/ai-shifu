import io

import pytest

from flaskr.service.tts import audio_utils


class _FakeSegment:
    append_crossfades: list[int] = []

    def __init__(self, duration_ms: int):
        self.duration_ms = duration_ms

    def __len__(self):
        return self.duration_ms

    def append(self, other, crossfade=100):
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

    def __getitem__(self, key):
        if isinstance(key, slice):
            start = int(key.start or 0)
            stop = int(key.stop if key.stop is not None else self.duration_ms)
            return _FakeSegment(max(stop - start, 0))
        return self

    def export(self, output_io, format="mp3", bitrate="128k"):
        _ = (format, bitrate)
        output_io.write(f"duration={self.duration_ms}".encode("utf-8"))


class _FakeAudioSegment:
    @staticmethod
    def from_mp3(segment_io: io.BytesIO):
        duration = int(segment_io.getvalue().decode("utf-8"))
        return _FakeSegment(duration)


class _PartiallyBrokenAudioSegment:
    @staticmethod
    def from_mp3(segment_io: io.BytesIO):
        payload = segment_io.getvalue()
        if payload == b"BAD":
            raise ValueError("Decoding failed")
        return _FakeSegment(int(payload.decode("utf-8")))


def test_concat_audio_mp3_does_not_crossfade_by_default(monkeypatch):
    _FakeSegment.append_crossfades.clear()
    monkeypatch.setattr(audio_utils, "AudioSegment", _FakeAudioSegment, raising=False)
    monkeypatch.setattr(audio_utils, "PYDUB_AVAILABLE", True)

    output = audio_utils.concat_audio_mp3([b"100", b"2", b"80"])

    assert _FakeSegment.append_crossfades == [0, 0]
    assert output == b"duration=182"


def test_concat_audio_mp3_caps_explicit_crossfade_for_short_segments(monkeypatch):
    _FakeSegment.append_crossfades.clear()
    monkeypatch.setattr(audio_utils, "AudioSegment", _FakeAudioSegment, raising=False)
    monkeypatch.setattr(audio_utils, "PYDUB_AVAILABLE", True)

    output = audio_utils.concat_audio_mp3([b"100", b"2", b"80"], crossfade_ms=50)

    assert _FakeSegment.append_crossfades == [2, 50]
    assert output == b"duration=130"


def test_concat_audio_mp3_raises_on_partial_decode_failure(monkeypatch):
    monkeypatch.setattr(
        audio_utils, "AudioSegment", _PartiallyBrokenAudioSegment, raising=False
    )
    monkeypatch.setattr(audio_utils, "PYDUB_AVAILABLE", True)

    with pytest.raises(ValueError, match="Failed to decode audio segments: 1"):
        audio_utils.concat_audio_mp3([b"100", b"BAD", b"80"])


def test_concat_audio_best_effort_reexports_decodable_segments_on_partial_failure(
    monkeypatch,
):
    monkeypatch.setattr(
        audio_utils, "AudioSegment", _PartiallyBrokenAudioSegment, raising=False
    )
    monkeypatch.setattr(audio_utils, "PYDUB_AVAILABLE", True)

    output = audio_utils.concat_audio_best_effort([b"100", b"BAD", b"80"])

    assert output == b"duration=180"


def test_concat_audio_best_effort_drops_undecodable_single_segment(monkeypatch):
    monkeypatch.setattr(
        audio_utils, "AudioSegment", _PartiallyBrokenAudioSegment, raising=False
    )
    monkeypatch.setattr(audio_utils, "PYDUB_AVAILABLE", True)

    output = audio_utils.concat_audio_best_effort([b"BAD"])

    assert output == b""


def test_concat_audio_best_effort_drops_undecodable_multiple_segments(monkeypatch):
    monkeypatch.setattr(
        audio_utils, "AudioSegment", _PartiallyBrokenAudioSegment, raising=False
    )
    monkeypatch.setattr(audio_utils, "PYDUB_AVAILABLE", True)

    output = audio_utils.concat_audio_best_effort([b"BAD", b"BAD"])

    assert output == b""


def test_export_audio_range_does_not_return_invalid_bytes_after_decode_failure(
    monkeypatch,
):
    monkeypatch.setattr(
        audio_utils, "AudioSegment", _PartiallyBrokenAudioSegment, raising=False
    )
    monkeypatch.setattr(audio_utils, "PYDUB_AVAILABLE", True)

    output, duration_ms = audio_utils.export_audio_range_best_effort(
        b"BAD",
        start_ms=0,
        end_ms=None,
    )

    assert output == b""
    assert duration_ms == 0
