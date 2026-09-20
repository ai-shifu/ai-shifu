"""Verify audio slicing and safe fallbacks without a codec subprocess."""

import io

import pytest
from flaskr.service.tts import audio_utils
from pydub import AudioSegment


def _wave(duration_ms: int = 1000) -> bytes:
    output = io.BytesIO()
    AudioSegment.silent(duration=duration_ms, frame_rate=16000).export(
        output, format="wav"
    )
    return output.getvalue()


@pytest.mark.parametrize(
    ("start", "end", "duration"),
    [
        (0, None, 1000),
        (100, 400, 300),
        (-10, 5000, 1000),
        (500, 100, 0),
        (2000, None, 0),
        (0, 0, 0),
    ],
)
def test_exported_range_is_standalone_audio_with_clamped_time_bounds(
    start: int,
    end: int | None,
    duration: int,
) -> None:
    data, actual_duration = audio_utils.export_audio_range_best_effort(
        _wave(),
        start_ms=start,
        end_ms=end,
        input_format="wav",
        output_format="wav",
    )
    assert actual_duration == duration
    if duration:
        decoded = AudioSegment.from_file(io.BytesIO(data), format="wav")
        assert len(decoded) == duration
        assert decoded.frame_rate == 16000
    else:
        assert data == b""


def test_empty_audio_has_zero_duration_and_no_range() -> None:
    assert audio_utils.try_get_audio_duration_ms(b"") == 0
    assert audio_utils.export_audio_range_best_effort(b"") == (b"", 0)
    assert audio_utils.concat_audio_best_effort([]) == b""
    assert audio_utils.concat_audio_best_effort([b""]) == b""


@pytest.mark.parametrize(
    "segments", [[b"first", b"second"], [b"", b"first", b"second"], [b"", b""]]
)
def test_missing_audio_processor_never_raw_concatenates_encoded_files(
    monkeypatch: pytest.MonkeyPatch,
    segments: list[bytes],
) -> None:
    monkeypatch.setattr(audio_utils, "PYDUB_AVAILABLE", False)
    assert audio_utils.concat_audio_best_effort(segments) == next(
        (item for item in segments if item), b""
    )
    assert audio_utils._concat_decodable_audio_segments(segments) == b""
    with pytest.raises(ImportError, match="pydub is required"):
        audio_utils.concat_audio_mp3(segments)


def test_missing_audio_processor_allows_full_blob_but_cannot_fabricate_a_slice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(audio_utils, "PYDUB_AVAILABLE", False)
    data = b"audio" * 3200
    assert audio_utils.try_get_audio_duration_ms(data) == 1000
    assert audio_utils.export_audio_range_best_effort(data) == (data, 1000)
    assert audio_utils.export_audio_range_best_effort(data, start_ms=100) == (b"", 0)
    assert audio_utils.export_audio_range_best_effort(data, end_ms=100) == (b"", 0)
    assert audio_utils.concat_audio_best_effort([data]) == data


def test_concat_rejects_empty_collection_but_preserves_single_file() -> None:
    with pytest.raises(ValueError, match="No audio segments"):
        audio_utils.concat_audio_mp3([])
    assert audio_utils.concat_audio_mp3([b"single-file"]) == b"single-file"


def test_best_effort_reexports_nonempty_decodable_subset_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, second = _wave(120), _wave(180)
    original_load = audio_utils._load_audio_segment

    def load_wave(data: bytes, *, input_format: str = "mp3") -> AudioSegment:
        assert input_format in {"mp3", "wav"}
        if not data:
            message = "empty audio"
            raise ValueError(message)
        return original_load(data, input_format="wav")

    monkeypatch.setattr(audio_utils, "_load_audio_segment", load_wave)
    result = audio_utils.concat_audio_best_effort(
        [first, b"", second], output_format="wav"
    )
    assert len(AudioSegment.from_file(io.BytesIO(result), format="wav")) == 300
    assert result != first + second
