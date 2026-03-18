from flaskr.service.learn.learn_dtos import (
    AudioCompleteDTO,
    AudioSegmentDTO,
    BlockType,
    GeneratedBlockDTO,
    GeneratedType,
    LearnRecordDTO,
    LikeStatus,
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


def test_learn_record_dto_payload_has_no_legacy_fields():
    record = GeneratedBlockDTO(
        generated_block_bid="gen-1",
        content="hello",
        like_status=LikeStatus.NONE,
        block_type=BlockType.CONTENT,
        user_input="",
    )

    dto = LearnRecordDTO(records=[record])
    payload = dto.__json__()

    assert "slides" not in payload
    assert payload["records"][0].generated_block_bid == "gen-1"
