from flaskr.dao import db
from flaskr.service.shifu.models import DraftOutlineItem, DraftShifu, LogDraftStruct
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.service.shifu.shifu_struct_manager import get_shifu_outline_tree


def test_get_shifu_outline_tree_preview(app):
    with app.app_context():
        shifu = DraftShifu(shifu_bid="shifu-1", title="Shifu", created_user_bid="u1")
        db.session.add(shifu)
        db.session.commit()

        outline = DraftOutlineItem(
            shifu_bid="shifu-1",
            outline_item_bid="outline-1",
            title="Outline",
            position="1",
            type=401,
            hidden=0,
        )
        db.session.add(outline)
        db.session.commit()

        struct = HistoryItem(
            bid="shifu-1",
            id=shifu.id,
            type="shifu",
            children=[
                HistoryItem(bid="outline-1", id=outline.id, type="outline", children=[])
            ],
        ).to_json()
        log = LogDraftStruct(struct_bid="struct-1", shifu_bid="shifu-1", struct=struct)
        db.session.add(log)
        db.session.commit()

    dto = get_shifu_outline_tree(app, "shifu-1", is_preview=True)
    assert dto.outline_items
    assert dto.outline_items[0].title == "Outline"
