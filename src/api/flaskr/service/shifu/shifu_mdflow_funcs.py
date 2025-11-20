from markdown_flow import MarkdownFlow
from flask import Flask
from flaskr.common.i18n_utils import get_markdownflow_output_language
from flaskr.service.shifu.models import DraftOutlineItem
from flaskr.service.common import raise_error
from flaskr.dao import db
from flaskr.service.shifu.dtos import MdflowDTOParseResult
from flaskr.service.check_risk.funcs import check_text_with_risk_control
from flaskr.service.shifu.shifu_history_manager import save_outline_history
from flaskr.service.profile.profile_manage import (
    get_profile_item_definition_list,
    add_profile_item_quick,
)
from datetime import datetime


def get_shifu_mdflow(app: Flask, shifu_bid: str, outline_bid: str) -> str:
    """
    Get shifu mdflow
    """
    with app.app_context():
        outline_item = (
            DraftOutlineItem.query.filter(
                DraftOutlineItem.outline_item_bid == outline_bid
            )
            .order_by(DraftOutlineItem.id.desc())
            .first()
        )
        if not outline_item:
            raise_error("server.shifu.outlineItemNotFound")
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
            raise_error("server.shifu.outlineItemNotFound")
        # create new version
        new_outline: DraftOutlineItem = outline_item.clone()
        new_outline.content = content

        # risk check
        # save to database
        if not outline_item.content == new_outline.content:
            check_text_with_risk_control(
                app, outline_item.outline_item_bid, user_id, content
            )
            new_outline.updated_user_bid = user_id
            new_outline.updated_at = datetime.now()
            db.session.add(new_outline)
            db.session.flush()
            markdown_flow = MarkdownFlow(content).set_output_language(
                get_markdownflow_output_language()
            )
            blocks = markdown_flow.get_all_blocks()
            variable_definitions = get_profile_item_definition_list(
                app, outline_item.shifu_bid
            )

            variables = markdown_flow.extract_variables()
            for variable in variables:
                exist_variable = next(
                    (v for v in variable_definitions if v.profile_key == variable), None
                )
                if not exist_variable:
                    add_profile_item_quick(
                        app, outline_item.shifu_bid, variable, user_id
                    )
            save_outline_history(
                app,
                user_id,
                outline_item.shifu_bid,
                outline_item.outline_item_bid,
                new_outline.id,
                len(blocks),
            )
            db.session.commit()


def parse_shifu_mdflow(
    app: Flask, shifu_bid: str, outline_bid: str, data: str = None
) -> MdflowDTOParseResult:
    """
    Parse shifu mdflow
    """
    with app.app_context():
        outline_item = (
            DraftOutlineItem.query.filter(
                DraftOutlineItem.outline_item_bid == outline_bid
            )
            .order_by(DraftOutlineItem.id.desc())
            .first()
        )
        if not outline_item:
            raise_error("server.shifu.outlineItemNotFound")
        mdflow = outline_item.content
        if data:
            mdflow = data
        markdown_flow = MarkdownFlow(mdflow).set_output_language(
            get_markdownflow_output_language()
        )
        blocks = markdown_flow.get_all_blocks()

        raw_variables = markdown_flow.extract_variables() or []
        profile_definitions = get_profile_item_definition_list(
            app, outline_item.shifu_bid
        )
        definition_keys = [
            item.profile_key for item in profile_definitions if item.profile_key
        ]

        dedup_vars: list[str] = []
        seen = set()
        for key in raw_variables + definition_keys:
            if not key or key in seen:
                continue
            dedup_vars.append(key)
            seen.add(key)

        return MdflowDTOParseResult(variables=dedup_vars, blocks_count=len(blocks))
