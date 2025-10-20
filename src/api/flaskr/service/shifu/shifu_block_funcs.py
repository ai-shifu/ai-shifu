"""
Shifu block functions

This module contains functions for managing shifu blocks.

Author: yfge
Date: 2025-08-07
"""

from flaskr.dao import db
from flaskr.service.shifu.dtos import (
    SaveBlockListResultDto,
    BlockDTO,
)
from flaskr.service.shifu.adapter import (
    update_block_dto_to_model_internal,
    convert_to_blockDTO,
    generate_block_dto_from_model_internal,
)
from flaskr.service.common import raise_error

from .models import DraftOutlineItem, DraftBlock
from flaskr.service.check_risk.funcs import check_text_with_risk_control
from flaskr.util import generate_id
from flaskr.service.profile.profile_manage import (
    get_profile_item_definition_list,
)
from .shifu_history_manager import (
    save_blocks_history,
    HistoryInfo,
)
from datetime import datetime
from flaskr.service.shifu.block_to_mdflow_adapter import convert_block_to_mdflow


def __get_block_list_internal(outline_id: str) -> list[DraftBlock]:
    sub_query = (
        db.session.query(db.func.max(DraftBlock.id))
        .filter(
            DraftBlock.outline_item_bid == outline_id,
        )
        .group_by(DraftBlock.block_bid)
    )
    blocks = (
        DraftBlock.query.filter(
            DraftBlock.id.in_(sub_query),
            DraftBlock.deleted == 0,
        )
        .order_by(DraftBlock.position.asc())
        .all()
    )
    return blocks


def get_block_list(app, user_id: str, outline_id: str) -> list[BlockDTO]:
    """
    Get block list
    Args:
        app: Flask application instance
        user_id: User ID
        outline_id: Outline ID
    Returns:
        list[BlockDTO]: Block list
    """
    with app.app_context():
        app.logger.info(f"get block list: {outline_id}")
        blocks = __get_block_list_internal(outline_id)

        block_dtos = []
        for block in blocks:
            block_dtos.append(
                generate_block_dto_from_model_internal(block, convert_html=True)
            )
        return block_dtos


def delete_block(app, user_id: str, outline_id: str, block_id: str):
    """
    Delete a block
    Args:
        app: Flask application instance
        user_id: User ID
        outline_id: Outline ID
        block_id: Block ID
    """
    with app.app_context():
        app.logger.info(f"delete block: {outline_id}, {block_id}")
        blocks = __get_block_list_internal(outline_id)
        now_time = datetime.now()
        block_model = next((b for b in blocks if b.block_bid == block_id), None)
        if block_model is None:
            raise_error("SHIFU.BLOCK_NOT_FOUND")
        block_model.deleted = 1
        block_model.updated_at = now_time
        block_model.updated_user_bid = user_id
        blocks_history = []
        shifu_bid = block_model.shifu_bid

        for block in blocks:
            if block.position > block_model.position:
                update_block = block.clone()
                update_block.position = block.position - 1
                update_block.updated_at = now_time
                update_block.updated_user_bid = user_id
                db.session.add(update_block)
                db.session.flush()
                blocks_history.append(
                    HistoryInfo(bid=block.block_bid, id=update_block.id)
                )
        save_blocks_history(app, user_id, shifu_bid, outline_id, blocks_history)
        db.session.commit()
        return True


def get_block(app, user_id: str, outline_id: str, block_id: str) -> BlockDTO:
    """
    Get a block
    Args:
        app: Flask application instance
        user_id: User ID
        outline_id: Outline ID
        block_id: Block ID
    """
    with app.app_context():
        app.logger.info(f"get block: {outline_id}, {block_id}")

        return None


def save_shifu_block_list(
    app, user_id: str, outline_id: str, block_list: list[BlockDTO]
) -> SaveBlockListResultDto:
    """
    Save a block list
    Args:
        app: Flask application instance
        user_id: User ID
        outline_id: Outline ID
        block_list: Block list
    """
    with app.app_context():
        app.logger.info(f"save block list: {outline_id}, {block_list}")
        now_time = datetime.now()
        outline: DraftOutlineItem = (
            DraftOutlineItem.query.filter(
                DraftOutlineItem.outline_item_bid == outline_id,
            )
            .order_by(DraftOutlineItem.id.desc())
            .first()
        )
        if outline is None:
            raise_error("SHIFU.OUTLINE_NOT_FOUND")
        if outline.deleted == 1:
            raise_error("SHIFU.OUTLINE_NOT_FOUND")
        blocks = __get_block_list_internal(outline_id)
        variable_definitions = get_profile_item_definition_list(app, outline.shifu_bid)
        variable_map = {
            variable_definition.profile_id: variable_definition.profile_key
            for variable_definition in variable_definitions
        }
        position = 1
        error_messages = {}
        save_block_ids = []
        save_block_models = []
        blocks_history = []
        is_changed = False
        markdown_flow_content = ""
        for block in block_list:
            block_dto = convert_to_blockDTO(block)
            try:
                markdown_flow_content += "\n" + convert_block_to_mdflow(
                    block_dto, variable_map
                )
            except Exception as e:
                app.logger.error(f"Failed to convert block to mdflow: {e}")
            block_model = next(
                (b for b in blocks if b.block_bid == block_dto.bid), None
            )
            if block_model is None:
                block_model = DraftBlock()
                block_model.block_bid = generate_id(app)
                result = update_block_dto_to_model_internal(
                    block_dto,
                    block_model,
                    variable_definitions,
                    new_block=True,
                )
                if result.error_message:
                    error_messages[block_model.block_bid] = result.error_message

                    continue
                block_model.outline_item_bid = outline_id
                block_model.shifu_bid = outline.shifu_bid
                block_model.position = position
                block_model.deleted = 0
                block_model.created_at = now_time
                block_model.created_user_bid = user_id
                block_model.updated_at = now_time
                block_model.updated_user_bid = user_id

                check_str = block_model.get_str_to_check()
                check_text_with_risk_control(
                    app, block_model.block_bid, user_id, check_str
                )
                save_block_ids.append(block_model.block_bid)
                save_block_models.append(block_model)
                db.session.add(block_model)
                is_changed = True
                db.session.flush()
                blocks_history.append(
                    HistoryInfo(bid=block_model.block_bid, id=block_model.id)
                )
            else:
                save_block_ids.append(block_model.block_bid)
                new_block = block_model.clone()
                new_block.position = position
                new_block.updated_at = now_time
                new_block.updated_user_bid = user_id
                new_block.deleted = 0
                result = update_block_dto_to_model_internal(
                    block_dto, new_block, variable_definitions, new_block=False
                )
                if result.error_message:
                    error_messages[new_block.block_bid] = result.error_message
                    blocks_history.append(
                        HistoryInfo(bid=new_block.block_bid, id=block_model.id)
                    )
                    continue
                if not new_block.eq(block_model):
                    check_str = new_block.get_str_to_check()
                    check_text_with_risk_control(
                        app, new_block.block_bid, user_id, check_str
                    )
                    db.session.add(new_block)
                    db.session.flush()
                    is_changed = True
                    blocks_history.append(
                        HistoryInfo(bid=new_block.block_bid, id=new_block.id)
                    )
                else:
                    blocks_history.append(
                        HistoryInfo(bid=block_model.block_bid, id=block_model.id)
                    )
                save_block_models.append(new_block)

            position = position + 1
        app.logger.info(f"save block ids: {save_block_ids}")
        for block in blocks:
            if block.block_bid not in save_block_ids:
                app.logger.info(f"delete block: {block.block_bid} ,{block.id}")
                block.deleted = 1
                block.updated_at = now_time
                block.updated_user_bid = user_id
                is_changed = True
        if is_changed:
            save_blocks_history(
                app, user_id, outline.shifu_bid, outline_id, blocks_history
            )
        # outline.content = markdown_flow_content
        db.session.commit()
        return SaveBlockListResultDto(
            [
                generate_block_dto_from_model_internal(block_model, True)
                for block_model in save_block_models
            ],
            error_messages,
        )


def add_block(
    app, user_id: str, outline_id: str, block: dict, block_index: int
) -> BlockDTO:
    """
    Add a block
    Args:
        app: Flask application instance
        user_id: User ID
        outline_id: Outline ID
        block: Block
        block_index: Block index
    """
    with app.app_context():
        now_time = datetime.now()
        outline: DraftOutlineItem = (
            DraftOutlineItem.query.filter(
                DraftOutlineItem.outline_item_bid == outline_id,
            )
            .order_by(DraftOutlineItem.id.desc())
            .first()
        )
        if outline is None:
            raise_error("SHIFU.OUTLINE_NOT_FOUND")
        if outline.deleted == 1:
            raise_error("SHIFU.OUTLINE_NOT_FOUND")
        block_bid = generate_id(app)
        block_dto = convert_to_blockDTO(block)
        block_index = block_index + 1
        variable_definitions = get_profile_item_definition_list(app, outline.shifu_bid)
        existing_blocks = __get_block_list_internal(outline_id)
        block_model: DraftBlock = DraftBlock()
        block_model.outline_item_bid = outline_id
        block_model.position = block_index
        block_model.block_bid = block_bid
        block_model.created_at = now_time
        block_model.created_user_bid = user_id
        block_model.updated_at = now_time
        block_model.updated_user_bid = user_id
        block_model.shifu_bid = outline.shifu_bid
        result = update_block_dto_to_model_internal(
            block_dto, block_model, variable_definitions, new_block=True
        )
        if result.error_message:
            raise_error(result.error_message)
        check_str = block_model.get_str_to_check()
        check_text_with_risk_control(app, block_model.block_bid, user_id, check_str)
        blocks_history = []
        db.session.add(block_model)
        db.session.flush()
        markdown_flow_content = ""
        is_add_to_content = False
        for block in existing_blocks:
            if block.position < block_index:
                markdown_flow_content += "\n" + convert_block_to_mdflow(
                    generate_block_dto_from_model_internal(block, False), {}
                )
                blocks_history.append(HistoryInfo(bid=block.block_bid, id=block.id))
                continue

            if block.position == block_index:
                blocks_history.append(
                    HistoryInfo(bid=block_model.block_bid, id=block_model.id)
                )
                markdown_flow_content += "\n" + convert_block_to_mdflow(
                    generate_block_dto_from_model_internal(block_model, False), {}
                )
                is_add_to_content = True
                continue

            if block.position >= block_index:
                markdown_flow_content += "\n" + convert_block_to_mdflow(
                    generate_block_dto_from_model_internal(block, False), {}
                )
                new_block = block.clone()
                new_block.position = block.position + 1
                new_block.updated_at = now_time
                new_block.updated_user_bid = user_id
                new_block.deleted = 0
                db.session.add(new_block)
                db.session.flush()
                blocks_history.append(
                    HistoryInfo(bid=new_block.block_bid, id=new_block.id)
                )
        if not is_add_to_content:
            markdown_flow_content += "\n" + convert_block_to_mdflow(
                generate_block_dto_from_model_internal(block_model, False), {}
            )
        outline.content = markdown_flow_content
        save_blocks_history(app, user_id, outline.shifu_bid, outline_id, blocks_history)
        db.session.commit()
        return generate_block_dto_from_model_internal(block_model)
