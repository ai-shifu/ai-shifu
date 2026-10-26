"""Keep recovered narration aligned with durable audio and stream retirement."""

from unittest.mock import Mock

import pytest
from flaskr.api.tts import AudioSettings, VoiceSettings
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn import learn_funcs as learn
from flaskr.service.learn import listen_element_history as history
from flaskr.service.learn.learn_dtos import (
    ElementAudioDTO,
    ElementDTO,
    ElementPayloadDTO,
    ElementType,
    GeneratedType,
    RunMarkdownFlowDTO,
)
from flaskr.service.learn.listen_element_run_state import BlockState
from flaskr.service.learn.listen_elements import ListenElementRunAdapter
from flaskr.service.learn.models import LearnGeneratedElement
from flaskr.service.tts.models import AUDIO_STATUS_COMPLETED, LearnGeneratedAudio

from tests.service.learn import test_element_protocol as protocol

adapter_app = protocol.adapter_app


def _audio(block: str, position: int, suffix: str, **overrides: object) -> None:
    db.session.add(
        LearnGeneratedAudio(
            generated_block_bid=block,
            position=position,
            audio_bid=suffix,
            oss_url=overrides.pop("oss_url", f"https://example.test/{suffix}.mp3"),
            duration_ms=120,
            subtitle_cues=[
                {"text": suffix, "start_ms": 0, "end_ms": 120, "segment_index": 0}
            ],
            status=overrides.pop("status", AUDIO_STATUS_COMPLETED),
            deleted=overrides.pop("deleted", 0),
            **overrides,
        )
    )
    db.session.flush()


def _element(bid: str, block: str = "block", **overrides: object) -> ElementDTO:
    return ElementDTO(
        element_bid=bid,
        generated_block_bid=block,
        element_index=0,
        role="teacher",
        element_type=ElementType.TEXT,
        element_type_code=213,
        content_text="Narration",
        is_speakable=overrides.pop("is_speakable", True),
        **overrides,
    )


@pytest.mark.usefixtures("adapter_app")
def test_history_assigns_sparse_audio_without_reusing_an_explicitly_bound_position() -> (
    None
):
    with unit_of_work():
        _audio("block", 2, "superseded")
        _audio("block", 2, "current")
        _audio("block", 2, "empty", oss_url="")
        _audio("block", 2, "deleted", deleted=1)
        _audio("block", 2, "unfinished", status=0)
        _audio("block", 5, "second")
        _audio("block", 8, "third")
    explicit = _element(
        "explicit",
        payload=ElementPayloadDTO(audio=ElementAudioDTO("", "", 0, position=2)),
    )
    implicit = [_element(f"implicit-{index}") for index in range(3)]
    missing = _element("missing", "another-block")
    results = history._enrich_elements_with_persisted_audio(
        [explicit, *implicit, missing]
    )
    assert results[0].payload.audio.audio_bid == "current"
    assert [item.payload.audio.position for item in results[:3]] == [2, 5, 8]
    assert [item.payload.audio.subtitle_cues[0].text for item in results[:3]] == [
        "current",
        "second",
        "third",
    ]
    assert results[3].audio_url == results[4].audio_url == ""
    assert results[3].payload is results[4].payload is None
    db.session.expire_all()
    assert LearnGeneratedAudio.query.count() == 7
    assert LearnGeneratedAudio.query.filter_by(audio_bid="empty").one().oss_url == ""


@pytest.mark.usefixtures("adapter_app")
def test_legacy_audio_links_recover_only_when_position_can_be_resolved() -> None:
    with unit_of_work():
        _audio("one", 4, "single")
        _audio("many", 0, "zero")
        _audio("many", 9, "nine")
    single = _element("single", "one", is_speakable=False, audio_url="old")
    zero = _element("zero", "many", is_speakable=False, audio_url="old")
    visual = _element("visual", "many", is_speakable=False)
    unbound = _element("unbound", "")
    stale = _element(
        "stale",
        "many",
        payload=ElementPayloadDTO(audio=ElementAudioDTO("old", "", 0, position=7)),
    )
    history._enrich_elements_with_persisted_audio(
        [single, zero, visual, unbound, stale]
    )
    assert (single.payload.audio.position, zero.payload.audio.position) == (4, 0)
    assert single.audio_url.endswith("single.mp3")
    assert zero.audio_url.endswith("zero.mp3")
    assert visual.payload is unbound.payload is None
    assert stale.payload.audio.audio_url == "old"


@pytest.mark.parametrize("emit", [True, False])
def test_stream_retirement_removes_replay_rows_and_cached_audio_targets(
    adapter_app: object,
    emit: bool,
) -> None:
    adapter = ListenElementRunAdapter(
        adapter_app, shifu_bid="course", outline_bid="lesson", user_bid="learner"
    )
    event = RunMarkdownFlowDTO(
        outline_bid="lesson",
        generated_block_bid="block",
        type=GeneratedType.CONTENT,
        content="",
    )
    streamed = list(
        adapter._handle_formatted_content(
            event,
            [("", "text", 0), ("First", "future-format", 1), ("Second", "text", 2)],
        )
    )
    elements = [message.content for message in streamed if message.type == "element"]
    assert [element.content_text for element in elements] == ["First", "Second"]
    assert all(element.element_type == ElementType.TEXT for element in elements)
    state = adapter._block_states["block"]
    assert len(LearnGeneratedElement.query.filter_by(status=1).all()) == 2
    assert list(adapter._finalize_stream_elements(state, emit=False)) == []
    db.session.expire_all()
    assert all(row.is_final for row in LearnGeneratedElement.query.filter_by(status=1))
    retired = list(adapter._retire_stream_elements(state, emit_notification=emit))
    assert len(retired) == (2 if emit else 0)
    assert adapter._latest_element_snapshots == {}
    db.session.expire_all()
    assert LearnGeneratedElement.query.filter_by(status=1).count() == 0
    assert (
        history.get_final_elements_for_generated_block(generated_block_bid="block")
        == []
    )
    if emit:
        assert {message.content.element_bid for message in retired} == {
            element.element_bid for element in elements
        }
        assert all(not message.content.is_navigable for message in retired)


def test_audio_snapshots_survive_producer_eviction_without_sharing_mutable_cues(
    adapter_app: object,
) -> None:
    adapter = ListenElementRunAdapter(
        adapter_app, shifu_bid="course", outline_bid="lesson", user_bid="learner"
    )
    state = BlockState(
        "block",
        audio_by_position={
            2: ElementAudioDTO(
                "url",
                "audio",
                120,
                2,
                [{"text": "hello", "start_ms": 0, "end_ms": 120, "segment_index": 0}],
            )
        },
    )
    first = adapter._freeze_live_audio_map(state)
    state.audio_by_position.clear()
    restored = adapter._freeze_live_audio_map(state, prefer_positions=["invalid", 2, 2])
    assert restored == first
    restored[2].subtitle_cues[0].text = "client mutation"
    assert state.live_audio_by_position[2].subtitle_cues[0].text == "hello"
    assert (
        adapter._resolve_or_buffer_audio_target_element_bid(
            state, position=2, stream_element_number="corrupt"
        )
        is None
    )
    assert state.pending_stream_audio_target_by_position == {}


@pytest.mark.parametrize("upload_fails", [False, True])
def test_completed_audio_is_durable_only_after_upload_succeeds(
    adapter_app: object,
    monkeypatch: pytest.MonkeyPatch,
    upload_fails: bool,
) -> None:
    monkeypatch.setattr(learn, "concat_audio_best_effort", b"".join)
    monkeypatch.setattr(learn, "get_audio_duration_ms", Mock(return_value=240))
    upload = Mock(return_value=("https://example.test/completed.mp3", "bucket"))
    if upload_fails:
        upload.side_effect = RuntimeError("upload unavailable")
    monkeypatch.setattr(learn, "upload_audio_to_oss", upload)
    arguments = {
        "audio_parts": [b"first", b"second"],
        "subtitle_cues": [
            {"text": "Hello", "start_ms": 0, "end_ms": 240, "segment_index": 0}
        ],
        "audio_bid": "completed",
        "audio_settings": AudioSettings(format="mp3", sample_rate=24000),
        "voice_settings": VoiceSettings(voice_id="voice"),
        "tts_model": "model",
        "cleaned_text": "Hello",
        "segment_count": 2,
        "persist_audio": True,
        "generated_block_bid": "block",
        "progress_record_bid": "progress",
        "user_bid": "learner",
        "shifu_bid": "course",
        "position": 3,
    }
    if upload_fails:
        with pytest.raises(RuntimeError, match="upload unavailable"):
            learn._finalize_tts_stream_audio(adapter_app, **arguments)
        assert LearnGeneratedAudio.query.count() == 0
    else:
        assert learn._finalize_tts_stream_audio(adapter_app, **arguments) == (
            "https://example.test/completed.mp3",
            240,
        )
        db.session.remove()
        row = LearnGeneratedAudio.query.one()
        assert (
            row.generated_block_bid,
            row.progress_record_bid,
            row.user_bid,
            row.shifu_bid,
        ) == ("block", "progress", "learner", "course")
        assert (row.audio_bid, row.position, row.duration_ms, row.file_size) == (
            "completed",
            3,
            240,
            11,
        )
        assert row.oss_object_key == "tts-audio/completed.mp3"
        assert (row.voice_id, row.model, row.segment_count, row.text_length) == (
            "voice",
            "model",
            2,
            5,
        )
        assert row.status == AUDIO_STATUS_COMPLETED
        assert row.subtitle_cues[0]["text"] == "Hello"
