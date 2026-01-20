from decimal import Decimal

from flaskr.dao import db
from flaskr.service.learn.learn_funcs import get_outline_item_tree, get_shifu_info
from flaskr.service.shifu.models import DraftOutlineItem, LogDraftStruct, PublishedShifu
from flaskr.service.shifu.shifu_history_manager import HistoryItem


def test_get_shifu_info_returns_dto(app):
    with app.app_context():
        shifu = PublishedShifu(
            shifu_bid="shifu-1",
            title="Test Shifu",
            description="Desc",
            price=Decimal("9.99"),
            keywords="a,b",
        )
        db.session.add(shifu)
        db.session.commit()

    dto = get_shifu_info(app, "shifu-1", preview_mode=False)
    assert dto.bid == "shifu-1"
    assert dto.title == "Test Shifu"
    assert dto.price == "9.99"
    assert dto.keywords == ["a", "b"]


def test_get_outline_item_tree_preview_mode(app):
    with app.app_context():
        outline = DraftOutlineItem(
            id=1,
            outline_item_bid="outline-1",
            shifu_bid="shifu-1",
            title="Outline",
            position="1",
            type=401,
            hidden=0,
        )
        db.session.add(outline)

        struct = HistoryItem(
            bid="shifu-1",
            id=0,
            type="shifu",
            children=[HistoryItem(bid="outline-1", id=1, type="outline", children=[])],
        ).to_json()
        log = LogDraftStruct(struct_bid="struct-1", shifu_bid="shifu-1", struct=struct)
        db.session.add(log)
        db.session.commit()

    result = get_outline_item_tree(app, "shifu-1", "user-1", preview_mode=True)
    assert result.outline_items
    assert result.outline_items[0].bid == "outline-1"
    assert result.outline_items[0].is_paid is True
