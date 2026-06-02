from decimal import Decimal

from flaskr.dao import db
from flaskr.service.learn.learn_dtos import GeneratedType
from flaskr.service.learn.learn_funcs import (
    get_outline_item_tree,
    get_shifu_info,
    stream_generated_block_audio,
)
from flaskr.service.learn.models import LearnGeneratedBlock
from flaskr.service.shifu.models import DraftOutlineItem, LogDraftStruct, PublishedShifu
from flaskr.service.shifu.shifu_history_manager import HistoryItem


def test_get_shifu_info_returns_dto(app):
    with app.app_context():
        shifu = PublishedShifu(
            shifu_bid="shifu-learn-1",
            title="Test Shifu",
            description="Desc",
            price=Decimal("9.99"),
            keywords="a,b",
        )
        db.session.add(shifu)
        db.session.commit()

    dto = get_shifu_info(app, "shifu-learn-1", preview_mode=False)
    assert dto.bid == "shifu-learn-1"
    assert dto.title == "Test Shifu"
    assert dto.price == "9.99"
    assert dto.keywords == ["a", "b"]


def test_stream_generated_block_audio_listen_skips_blocks_without_speakable_elements(
    app, monkeypatch
):
    with app.app_context():
        block = LearnGeneratedBlock(
            generated_block_bid="generated-block-empty-tts",
            progress_record_bid="progress-1",
            user_bid="user-1",
            block_bid="block-1",
            outline_item_bid="outline-1",
            shifu_bid="shifu-learn-1",
            generated_content="",
            status=1,
            deleted=0,
        )
        db.session.add(block)
        db.session.commit()

    from flaskr.service.learn import listen_element_history

    monkeypatch.setattr(
        listen_element_history,
        "get_final_elements_for_generated_block",
        lambda **_kwargs: [],
    )

    events = list(
        stream_generated_block_audio(
            app,
            shifu_bid="shifu-learn-1",
            generated_block_bid="generated-block-empty-tts",
            user_bid="user-1",
            preview_mode=False,
            listen=True,
        )
    )

    assert len(events) == 1
    assert events[0].type == GeneratedType.DONE
    assert events[0].generated_block_bid == "generated-block-empty-tts"


def test_get_outline_item_tree_preview_mode(app):
    with app.app_context():
        outline = DraftOutlineItem(
            outline_item_bid="outline-learn-1",
            shifu_bid="shifu-learn-1",
            title="Outline",
            position="1",
            type=401,
            hidden=0,
        )
        db.session.add(outline)
        db.session.commit()

        struct = HistoryItem(
            bid="shifu-learn-1",
            id=0,
            type="shifu",
            children=[
                HistoryItem(
                    bid="outline-learn-1",
                    id=outline.id,
                    type="outline",
                    children=[],
                )
            ],
        ).to_json()
        log = LogDraftStruct(
            struct_bid="struct-learn-1",
            shifu_bid="shifu-learn-1",
            struct=struct,
        )
        db.session.add(log)
        db.session.commit()

    result = get_outline_item_tree(app, "shifu-learn-1", "user-1", preview_mode=True)
    assert result.outline_items
    assert result.outline_items[0].bid == "outline-learn-1"
    assert result.outline_items[0].is_paid is True
