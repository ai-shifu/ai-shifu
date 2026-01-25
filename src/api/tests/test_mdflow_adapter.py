from flaskr.dao import db
from flaskr.service.shifu.models import DraftOutlineItem
from flaskr.service.shifu.shifu_mdflow_funcs import (
    get_shifu_mdflow,
    parse_shifu_mdflow,
)


def test_parse_shifu_mdflow_returns_variables(app):
    with app.app_context():
        outline = DraftOutlineItem(
            outline_item_bid="outline-mdflow-1",
            shifu_bid="shifu-mdflow-1",
            title="Outline Title",
            content="Hello {{name}}",
        )
        db.session.add(outline)
        db.session.commit()

    result = parse_shifu_mdflow(app, "shifu-mdflow-1", "outline-mdflow-1")
    assert "name" in result.variables
    assert result.blocks_count >= 1

    content = get_shifu_mdflow(app, "shifu-mdflow-1", "outline-mdflow-1")
    assert content == "Hello {{name}}"
