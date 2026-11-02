"""Verify listen elements built from legacy learn records."""

import json

import pytest
from flask import Flask
from flaskr import dao
from flaskr.service.learn.elements.legacy_record_builder import (
    LegacyGeneratedBlockRecord,
    LegacyLearnRecord,
)
from flaskr.service.learn.elements.run_adapter import (
    build_listen_elements_from_legacy_record,
)
from flaskr.service.learn.learn_dtos import (
    AudioCompleteDTO,
    BlockType,
    ElementType,
    LikeStatus,
)
from flaskr.service.learn.models import LearnGeneratedElement

from tests.service.learn.listen_element_helpers import ListenScope


@pytest.fixture(scope="module")
def legacy_app() -> Flask:
    app = Flask("listen-elements-legacy-record")
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    dao.db.init_app(app)
    with app.app_context():
        dao.db.create_all()
    return app


def _block(
    generated_block_bid: str,
    content: str,
    block_type: BlockType = BlockType.CONTENT,
    user_input: str = "",
    audios: list[AudioCompleteDTO] | None = None,
) -> LegacyGeneratedBlockRecord:
    return LegacyGeneratedBlockRecord(
        generated_block_bid=generated_block_bid,
        content=content,
        like_status=LikeStatus.NONE,
        block_type=block_type,
        user_input=user_input,
        audios=audios or [],
    )


def _audios(slug: str, durations: tuple[int, ...]) -> list[AudioCompleteDTO]:
    return [
        AudioCompleteDTO(
            position=position,
            audio_url=f"https://example.com/{slug}-{position}.mp3",
            audio_bid=f"audio-{slug}-{position}",
            duration_ms=duration_ms,
        )
        for position, duration_ms in enumerate(durations)
    ]


def _build(app: Flask, *blocks: LegacyGeneratedBlockRecord) -> object:
    return build_listen_elements_from_legacy_record(
        app, LegacyLearnRecord(records=list(blocks))
    )


def _replace_persisted_rows(app: Flask, rows: list[object]) -> None:
    with app.app_context():
        dao.db.session.query(LearnGeneratedElement).delete()
        dao.db.session.add_all(rows)
        dao.db.session.commit()


def _persisted_texts(slug: str, texts: list[tuple[str, int]]) -> list[object]:
    """Build final text rows for ``(content_text, is_speakable)`` in element order."""
    scope = ListenScope(
        f"legacy-{slug}", generated_block_bid=f"generated-legacy-{slug}"
    )
    return [
        scope.render(
            element_bid=f"el-legacy-{slug}-{index + 1}",
            run_event_seq=index + 1,
            element_index=index,
            element_type="text",
            element_type_code=213,
            is_renderable=0,
            sequence_number=index + 1,
            is_speakable=is_speakable,
            is_final=1,
            content_text=text,
        )
        for index, (text, is_speakable) in enumerate(texts)
    ]


def test_interleaves_visuals_and_text(legacy_app: Flask) -> None:
    generated_block_bid = "generated-legacy-elements"
    _replace_persisted_rows(legacy_app, [])

    result = _build(
        legacy_app,
        _block(
            generated_block_bid,
            "Before intro.\n\n<svg><text>Chart</text></svg>\n\nAfter chart.",
            audios=_audios("legacy", (800, 900)),
        ),
    )

    assert len(result.elements) == 3
    first, second, third = result.elements

    for index, (text_element, text) in enumerate(
        ((first, "Before intro."), (third, "After chart."))
    ):
        assert text_element.generated_block_bid == generated_block_bid
        assert text_element.element_type == ElementType.TEXT
        assert text_element.content_text == text
        assert text_element.payload is not None
        assert text_element.payload.audio is not None
        assert text_element.payload.audio.audio_bid == f"audio-legacy-{index}"
        assert text_element.payload.previous_visuals == []
        assert text_element.is_renderable is False
        assert text_element.is_speakable is True
        assert text_element.is_marker is False
        assert text_element.audio_url == f"https://example.com/legacy-{index}.mp3"
        assert text_element.audio_segments == []
    assert [element.element_index for element in result.elements] == [0, 1, 2]

    assert second.generated_block_bid == generated_block_bid
    assert second.element_type == ElementType.SVG
    assert second.is_renderable is True
    assert second.is_marker is True
    assert second.content_text == ""
    assert second.payload is not None
    assert second.payload.audio is None
    assert len(second.payload.previous_visuals) == 1
    assert second.payload.previous_visuals[0].visual_type == "svg"
    assert second.payload.previous_visuals[0].content.startswith("<svg")


@pytest.mark.parametrize(
    ("slug", "content", "texts", "expected_audio_bids"),
    [
        pytest.param(
            "persisted",
            "Alpha Beta",
            [("Alpha", 1), ("Beta", 1)],
            ["audio-persisted-0", "audio-persisted-1"],
            id="every_text_row_speakable",
        ),
        pytest.param(
            "skip-blank",
            "Hello\n\nWorld",
            [("Hello", 1), ("   ", 0), ("World", 1)],
            ["audio-skip-blank-0", None, "audio-skip-blank-1"],
            id="blank_text_row_skipped",
        ),
    ],
)
def test_binds_audio_positions_to_persisted_speakable_text_rows(
    legacy_app: Flask,
    slug: str,
    content: str,
    texts: list[tuple[str, int]],
    expected_audio_bids: list[str | None],
) -> None:
    _replace_persisted_rows(legacy_app, _persisted_texts(slug, texts))

    result = _build(
        legacy_app,
        _block(
            f"generated-legacy-{slug}",
            content,
            audios=_audios(slug, (320, 410)),
        ),
    )

    assert [element.element_type for element in result.elements] == [
        ElementType.TEXT
    ] * len(texts)
    assert [element.content_text for element in result.elements] == [
        text for text, _ in texts
    ]
    assert [element.element_index for element in result.elements] == list(
        range(len(texts))
    )
    assert [element.audio_url for element in result.elements] == [
        "" if bid is None else f"https://example.com/{bid.removeprefix('audio-')}.mp3"
        for bid in expected_audio_bids
    ]
    assert [
        None if element.payload.audio is None else element.payload.audio.audio_bid
        for element in result.elements
    ] == expected_audio_bids


def test_prefers_persisted_visual_elements(legacy_app: Flask) -> None:
    scope = ListenScope("legacy-visual", generated_block_bid="generated-legacy-visual")
    visual_markdown = "![img](https://example.com/visual.png)"
    visual_payload = json.dumps(
        {
            "audio": None,
            "previous_visuals": [{"visual_type": "img", "content": visual_markdown}],
        }
    )

    def text_row(seq: int, index: int, text: str) -> object:
        return scope.render(
            element_bid=f"el-legacy-visual-text-{index // 2 + 1}",
            run_event_seq=seq,
            element_index=index,
            element_type="text",
            element_type_code=213,
            is_renderable=0,
            sequence_number=seq,
            is_speakable=1,
            is_final=1,
            content_text=text,
        )

    def marker_row(seq: int, **overrides: object) -> object:
        return scope.element(
            element_bid="el-legacy-visual-marker",
            run_event_seq=seq,
            element_index=1,
            element_type="img",
            element_type_code=204,
            change_type="render",
            is_marker=1,
            sequence_number=seq,
            is_final=1,
            payload=visual_payload,
            **overrides,
        )

    _replace_persisted_rows(
        legacy_app,
        [
            text_row(1, 0, "Before image."),
            # A retired snapshot and its active patch for the same visual.
            marker_row(2, status=0),
            marker_row(
                3,
                target_element_bid="el-legacy-visual-marker",
                is_new=0,
            ),
            text_row(4, 2, "After image."),
        ],
    )

    result = _build(
        legacy_app,
        _block(
            scope.generated_block_bid,
            f"Before image.\n\n{visual_markdown}\n\nAfter image.",
            audios=_audios("legacy-visual", (320, 410)),
        ),
    )

    assert len(result.elements) == 3
    assert [element.element_type for element in result.elements] == [
        ElementType.TEXT,
        ElementType.IMG,
        ElementType.TEXT,
    ]
    assert [element.content_text for element in result.elements] == [
        "Before image.",
        "![img](https://example.com/visual.png)",
        "After image.",
    ]
    assert [element.is_new for element in result.elements] == [True, True, True]
    assert [element.element_index for element in result.elements] == [0, 1, 2]
    assert result.elements[1].target_element_bid in ("", None)
    assert result.elements[1].payload is not None
    assert result.elements[1].payload.previous_visuals[0].visual_type == "img"
    assert result.elements[1].payload.previous_visuals[0].content == ""
    assert [element.audio_url for element in result.elements] == [
        "https://example.com/legacy-visual-0.mp3",
        "",
        "https://example.com/legacy-visual-1.mp3",
    ]


def test_keeps_interaction_user_input(legacy_app: Flask) -> None:
    _replace_persisted_rows(legacy_app, [])

    result = _build(
        legacy_app,
        _block(
            "generated-interaction-legacy",
            "?[Agree//agree][Disagree//disagree]",
            block_type=BlockType.INTERACTION,
            user_input="agree",
        ),
    )

    assert len(result.elements) == 1
    element = result.elements[0]
    assert element.is_renderable is False
    assert element.payload is not None
    assert element.payload.user_input == "agree"


def test_emits_ask_and_answer_with_anchor_for_follow_up_blocks(
    legacy_app: Flask,
) -> None:
    _replace_persisted_rows(legacy_app, [])

    result = _build(
        legacy_app,
        _block("generated-content-anchor", "Teacher intro"),
        _block("generated-ask-1", "你好", block_type=BlockType.ASK),
        _block("generated-answer-1", "Hi there", block_type=BlockType.ANSWER),
    )

    assert [element.element_type for element in result.elements] == [
        ElementType.TEXT,
        ElementType.ASK,
        ElementType.ANSWER,
    ]
    assert [element.role for element in result.elements] == [
        "teacher",
        "student",
        "teacher",
    ]
    assert [element.content_text for element in result.elements] == [
        "Teacher intro",
        "你好",
        "Hi there",
    ]
    anchor_bid = result.elements[0].element_bid
    assert result.elements[1].payload.anchor_element_bid == anchor_bid
    assert result.elements[2].payload.anchor_element_bid == anchor_bid


def test_drops_follow_up_blocks_without_any_prior_anchor(legacy_app: Flask) -> None:
    _replace_persisted_rows(legacy_app, [])

    result = _build(
        legacy_app,
        _block("orphan-ask", "你好", block_type=BlockType.ASK),
        _block("orphan-answer", "Hi", block_type=BlockType.ANSWER),
    )

    assert result.elements == []
