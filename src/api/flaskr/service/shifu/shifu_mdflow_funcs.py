from markdown_flow import MarkdownFlow
from flask import Flask
from flaskr.service.shifu.models import DraftOutlineItem
from flaskr.service.common import raise_error
from flaskr.dao import db
from flaskr.service.shifu.dtos import MdflowDTOParseResult


def get_shifu_mdflow(app: Flask, shifu_bid: str, outline_bid: str) -> str:
    """
    Get shifu mdflow
    """
    with app.app_context():
        outline_item = DraftOutlineItem.query.filter(
            DraftOutlineItem.outline_item_bid == outline_bid
        ).first()
        if not outline_item:
            raise_error("SHIFU.OUTLINE_ITEM_NOT_FOUND")
        return outline_item.content


def save_shifu_mdflow(
    app: Flask, user_id: str, shifu_bid: str, outline_bid: str, content: str
) -> str:
    """
    Save shifu mdflow
    """
    with app.app_context():
        outline_item: DraftOutlineItem = (
            DraftOutlineItem.query.filter(
                DraftOutlineItem.outline_item_bid == outline_bid
            )
            .order_by(DraftOutlineItem.id.desc())
            .first()
        )
        if not outline_item:
            raise_error("SHIFU.OUTLINE_ITEM_NOT_FOUND")
        outline_item.content = content
        outline_item.updated_user_bid = user_id
        db.session.commit()


def parse_shifu_mdflow(
    app: Flask, shifu_bid: str, outline_bid: str, content: str
) -> MdflowDTOParseResult:
    """
    Parse shifu mdflow
    """
    with app.app_context():
        markdown_flow = MarkdownFlow(content)
        markdown_flow.parse()
        varibales = markdown_flow.extract_variables()
        blocks = markdown_flow.get_all_blocks()
        return MdflowDTOParseResult(variables=varibales, blocks_count=len(blocks))
