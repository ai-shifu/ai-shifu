"""Cover when a streaming element is written, which is the difference between 35MB and 21KB.

1.0 writes every update as a new row holding the whole text so far and retires the previous one.
Nothing reads those back -- every read path filters on `status == 1` -- but it is affordable when a
script block is small. A 2.0 turn is a whole lesson segment: one measured turn produced 6394 rows
and 35MB of retired snapshots against 4 rows the learner could see.
"""

from __future__ import annotations

import pytest
from flaskr.service.learn.listen_elements import ListenElementRunAdapter


def _adapter(**kwargs: object) -> ListenElementRunAdapter:
    return ListenElementRunAdapter(
        None,
        shifu_bid="shifu-bid",
        outline_bid="outline-bid",
        user_bid="user-bid",
        **kwargs,
    )


def test_the_script_engine_keeps_writing_every_update() -> None:
    """1.0's behaviour is unchanged: this is the default, and it is what production runs."""
    assert _adapter().persist_only_final is False


def test_the_agent_engine_writes_only_the_final_element() -> None:
    assert _adapter(persist_only_final=True).persist_only_final is True


@pytest.mark.parametrize(
    ("persist_only_final", "is_final", "expected"),
    [
        pytest.param(False, False, "_element_message", id="1.0-mid-stream-writes"),
        pytest.param(False, True, "_element_message", id="1.0-final-writes"),
        pytest.param(
            True, False, "_stream_only_element_message", id="2.0-mid-stream-defers"
        ),
        pytest.param(True, True, "_element_message", id="2.0-final-writes"),
    ],
)
def test_which_path_a_streaming_update_takes(
    monkeypatch: pytest.MonkeyPatch,
    persist_only_final: bool,
    is_final: bool,
    expected: str,
) -> None:
    """The final update is always written, whichever engine produced it: every read returns it."""
    adapter = _adapter(persist_only_final=persist_only_final)
    taken: list[str] = []

    for name in ("_element_message", "_stream_only_element_message"):
        monkeypatch.setattr(
            adapter,
            name,
            lambda _element, _name=name: taken.append(_name),
            raising=True,
        )
    monkeypatch.setattr(
        adapter, "_build_stream_element", lambda **_kwargs: object(), raising=False
    )

    adapter._build_stream_element_message(
        state=object(),
        role="teacher",
        stream_state=object(),
        is_new=True,
        is_final=is_final,
    )

    assert taken == [expected]


@pytest.mark.parametrize(
    ("persist_only_final", "expected"),
    [
        pytest.param(False, "_element_message", id="1.0-writes-every-audio-patch"),
        pytest.param(True, "_stream_only_element_message", id="2.0-defers-audio-patch"),
    ],
)
def test_which_path_an_audio_patch_takes(
    monkeypatch: pytest.MonkeyPatch, persist_only_final: bool, expected: str
) -> None:
    """A segment of audio for an element still being written is not a row of its own.

    The block's finalisation resolves every segment for the element and writes it once with all
    of them, so a per-segment write is a full copy of the element's text that nothing reads back.
    1.0 keeps writing them: a learner refreshing mid-stream reads the latest row.
    """
    adapter = _adapter(persist_only_final=persist_only_final)
    taken: list[str] = []
    for name in ("_element_message", "_stream_only_element_message"):
        monkeypatch.setattr(
            adapter,
            name,
            lambda _element, _name=name: taken.append(_name),
            raising=True,
        )
    monkeypatch.setattr(
        adapter, "_build_audio_patch_element", lambda *_a, **_k: object(), raising=False
    )

    adapter._build_audio_segment_patch_message("element-bid", audio_segments=[{}])

    assert taken == [expected]
