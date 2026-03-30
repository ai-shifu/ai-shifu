from flaskr.service.learn.learn_dtos import (
    AudioCompleteDTO,
    AudioSegmentDTO,
    GeneratedType,
)
from flaskr.service.learn.learn_dtos import BlockType, LikeStatus
from flaskr.service.learn.legacy_record_builder import (
    LegacyGeneratedBlockRecord,
    LegacyLearnRecord,
)


def test_generated_type_excludes_new_slide():
    assert "new_slide" not in {item.value for item in GeneratedType}


def test_audio_segment_dto_payload_has_no_legacy_fields():
    dto = AudioSegmentDTO(
        segment_index=0,
        audio_data="ZmFrZS1hdWRpbw==",
        duration_ms=123,
        is_final=False,
        position=2,
    )
    payload = dto.__json__()

    assert payload["position"] == 2
    assert "slide_id" not in payload


def test_audio_complete_dto_payload_has_no_legacy_fields():
    dto = AudioCompleteDTO(
        audio_url="https://example.com/a.mp3",
        audio_bid="audio-1",
        duration_ms=1000,
        position=0,
    )
    payload = dto.__json__()

    assert "slide_id" not in payload


def test_audio_dto_payload_can_include_stream_binding_fields():
    segment = AudioSegmentDTO(
        segment_index=0,
        audio_data="ZmFrZS1hdWRpbw==",
        duration_ms=123,
        is_final=False,
        position=2,
        stream_element_number=7,
        stream_element_type="text",
    )
    complete = AudioCompleteDTO(
        audio_url="https://example.com/a.mp3",
        audio_bid="audio-1",
        duration_ms=1000,
        position=2,
        stream_element_number=7,
        stream_element_type="text",
    )

    segment_payload = segment.__json__()
    complete_payload = complete.__json__()

    assert segment_payload["stream_element_number"] == 7
    assert segment_payload["stream_element_type"] == "text"
    assert complete_payload["stream_element_number"] == 7
    assert complete_payload["stream_element_type"] == "text"


def test_legacy_learn_record_payload_has_no_legacy_fields():
    record = LegacyGeneratedBlockRecord(
        generated_block_bid="gen-1",
        content="hello",
        like_status=LikeStatus.NONE,
        block_type=BlockType.CONTENT,
        user_input="",
    )

    dto = LegacyLearnRecord(records=[record])
    payload = dto.__json__()

    assert "slides" not in payload
    assert payload["records"][0].generated_block_bid == "gen-1"
