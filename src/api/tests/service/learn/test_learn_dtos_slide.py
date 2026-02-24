from flaskr.service.learn.learn_dtos import (
    AudioCompleteDTO,
    AudioSegmentDTO,
    BlockType,
    GeneratedBlockDTO,
    GeneratedType,
    LearnRecordDTO,
    LikeStatus,
    NewSlideDTO,
)


def test_generated_type_includes_new_slide():
    assert GeneratedType.NEW_SLIDE.value == "new_slide"


def test_audio_segment_dto_serializes_optional_slide_id():
    without_slide = AudioSegmentDTO(
        segment_index=0,
        audio_data="ZmFrZS1hdWRpbw==",
        duration_ms=123,
        is_final=False,
        position=2,
    )
    with_slide = AudioSegmentDTO(
        segment_index=1,
        audio_data="ZmFrZS1hdWRpbw==",
        duration_ms=456,
        is_final=True,
        position=3,
        slide_id="slide-123",
    )

    payload_without_slide = without_slide.__json__()
    payload_with_slide = with_slide.__json__()

    assert payload_without_slide["position"] == 2
    assert "slide_id" not in payload_without_slide

    assert payload_with_slide["position"] == 3
    assert payload_with_slide["slide_id"] == "slide-123"


def test_audio_complete_dto_serializes_optional_slide_id():
    without_slide = AudioCompleteDTO(
        audio_url="https://example.com/a.mp3",
        audio_bid="audio-1",
        duration_ms=1000,
        position=0,
    )
    with_slide = AudioCompleteDTO(
        audio_url="https://example.com/b.mp3",
        audio_bid="audio-2",
        duration_ms=2000,
        position=1,
        slide_id="slide-abc",
    )

    payload_without_slide = without_slide.__json__()
    payload_with_slide = with_slide.__json__()

    assert "slide_id" not in payload_without_slide
    assert payload_with_slide["slide_id"] == "slide-abc"


def test_new_slide_dto_json_payload():
    dto = NewSlideDTO(
        slide_id="slide-1",
        generated_block_bid="block-1",
        slide_index=5,
        audio_position=2,
        visual_kind="svg",
        segment_type="markdown",
        segment_content="<svg><text>x</text></svg>",
        source_span=[10, 30],
        is_placeholder=False,
    )

    payload = dto.__json__()
    assert payload["slide_id"] == "slide-1"
    assert payload["generated_block_bid"] == "block-1"
    assert payload["slide_index"] == 5
    assert payload["audio_position"] == 2
    assert payload["visual_kind"] == "svg"
    assert payload["segment_type"] == "markdown"
    assert payload["source_span"] == [10, 30]
    assert payload["is_placeholder"] is False


def test_learn_record_dto_includes_slides_when_provided():
    record = GeneratedBlockDTO(
        generated_block_bid="gen-1",
        content="hello",
        like_status=LikeStatus.NONE,
        block_type=BlockType.CONTENT,
        user_input="",
    )
    slide = NewSlideDTO(
        slide_id="slide-1",
        generated_block_bid="gen-1",
        slide_index=0,
        audio_position=0,
        visual_kind="placeholder",
        segment_type="placeholder",
        segment_content="",
        source_span=[],
        is_placeholder=True,
    )

    dto = LearnRecordDTO(records=[record], interaction="", slides=[slide])
    payload = dto.__json__()

    assert "slides" in payload
    assert len(payload["slides"]) == 1
    assert payload["slides"][0].slide_id == "slide-1"
