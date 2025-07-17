from datetime import datetime
from flaskr.framework.plugin.plugin_manager import extension
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

from .models import ShifuDraftOutlineItem, ShifuDraftBlock
from flaskr.service.shifu.block_funcs import (
    get_profile_item_definition_list,
    check_text_with_risk_control,
)
from flaskr.util import generate_id
from .shifu_history_manager import (
    save_blocks_history,
    HistoryInfo,
)


def _get_block_list_internal(
    app, user_id: str, outline_id: str
) -> list[ShifuDraftBlock]:
    with app.app_context():
        sub_query = (
            db.session.query(db.func.max(ShifuDraftBlock.id))
            .filter(
                ShifuDraftBlock.outline_item_bid == outline_id,
            )
            .group_by(ShifuDraftBlock.block_bid)
        )
        blocks = (
            ShifuDraftBlock.query.filter(
                ShifuDraftBlock.id.in_(sub_query),
                ShifuDraftBlock.deleted == 0,
            )
            .order_by(ShifuDraftBlock.position.asc())
            .all()
        )
        return blocks


@extension("get_block_list")
def get_block_list(result, app, user_id: str, outline_id: str) -> list[BlockDTO]:
    with app.app_context():
        app.logger.info(f"get block list: {outline_id}")
        blocks = _get_block_list_internal(app, user_id, outline_id)

        block_dtos = []
        for block in blocks:
            block_dtos.append(generate_block_dto_from_model_internal(block))
        return block_dtos


@extension("delete_block")
def delete_block(result, app, user_id: str, outline_id: str, block_id: str):
    with app.app_context():
        app.logger.info(f"delete block: {outline_id}, {block_id}")
        blocks = _get_block_list_internal(app, user_id, outline_id)
        block_model = next((b for b in blocks if b.block_bid == block_id), None)
        if block_model is None:
            raise_error("SHIFU.BLOCK_NOT_FOUND")
        block_model.deleted = 1
        block_model.updated_at = datetime.now()
        block_model.updated_user_bid = user_id
        blocks_history = []
        for block in blocks:
            if block.position > block_model.position:
                update_block = block.clone()
                update_block.position = block.position - 1
                update_block.updated_at = datetime.now()
                update_block.updated_user_bid = user_id
                db.session.add(update_block)
                db.session.flush()
                blocks_history.append(
                    HistoryInfo(bid=block.block_bid, id=update_block.id)
                )
        save_blocks_history(app, user_id, outline_id, block_id, blocks_history)
        db.session.commit()
        return True


@extension("get_block")
def get_block(result, app, user_id: str, outline_id: str, block_id: str) -> BlockDTO:
    with app.app_context():
        app.logger.info(f"get block: {outline_id}, {block_id}")

        return None


@extension("save_block_list")
def save_block_list(
    result, app, user_id: str, outline_id: str, block_list: list[BlockDTO]
) -> SaveBlockListResultDto:
    with app.app_context():
        app.logger.info(f"save block list: {outline_id}, {block_list}")
        time = datetime.now()
        outline: ShifuDraftOutlineItem = (
            ShifuDraftOutlineItem.query.filter(
                ShifuDraftOutlineItem.outline_item_bid == outline_id,
            )
            .order_by(ShifuDraftOutlineItem.id.desc())
            .first()
        )
        if outline is None:
            raise_error("SHIFU.OUTLINE_NOT_FOUND")
        if outline.deleted == 1:
            raise_error("SHIFU.OUTLINE_NOT_FOUND")
        blocks = _get_block_list_internal(app, user_id, outline_id)
        variable_definitions = get_profile_item_definition_list(app, outline.shifu_bid)
        position = 1
        error_messages = {}
        save_block_ids = []
        save_block_models = []
        blocks_history = []
        is_changed = False
        for block in block_list:
            block_dto = convert_to_blockDTO(block)
            block_model = next(
                (b for b in blocks if b.block_bid == block_dto.bid), None
            )
            if block_model is None:
                block_model = ShifuDraftBlock()
                block_model.block_bid = generate_id(app)
                result = update_block_dto_to_model_internal(
                    block_dto, block_model, variable_definitions, new_block=True
                )
                if result.error_message:
                    error_messages[block_model.block_bid] = result.error_message
                    continue
                block_model = ShifuDraftBlock()
                block_model.outline_item_bid = outline_id
                block_model.position = position
                block_model.deleted = 0
                block_model.created_at = time
                block_model.created_user_bid = user_id
                block_model.updated_at = time
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
                new_block = block_model.clone()
                new_block.position = position
                new_block.updated_at = time
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
                save_block_ids.append(new_block.block_bid)
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

        for block in blocks:
            if block.block_bid not in save_block_ids:
                block.deleted = 1
                block.updated_at = time
                block.updated_user_bid = user_id
        if is_changed:
            save_blocks_history(
                app, user_id, outline.shifu_bid, outline_id, blocks_history
            )
        db.session.commit()
        return SaveBlockListResultDto(
            [
                generate_block_dto_from_model_internal(block_model)
                for block_model in save_block_models
            ],
            error_messages,
        )


@extension("add_block")
def add_block(
    result: BlockDTO, app, user_id: str, outline_id: str, block: dict, block_index: int
) -> BlockDTO:
    with app.app_context():
        time = datetime.now()
        outline: ShifuDraftOutlineItem = (
            ShifuDraftOutlineItem.query.filter(
                ShifuDraftOutlineItem.outline_item_bid == outline_id,
            )
            .order_by(ShifuDraftOutlineItem.id.desc())
            .first()
        )
        if outline is None:
            raise_error("SHIFU.OUTLINE_NOT_FOUND")
        if outline.deleted == 1:
            raise_error("SHIFU.OUTLINE_NOT_FOUND")
        if result is not None:
            block_bid = result.bid
        else:
            block_bid = generate_id(app)
        block_dto = convert_to_blockDTO(block)
        block_index = block_index + 1
        variable_definitions = get_profile_item_definition_list(app, outline.shifu_bid)
        existing_blocks = _get_block_list_internal(app, user_id, outline_id)
        block_model: ShifuDraftBlock = ShifuDraftBlock()
        block_model.outline_item_bid = outline_id
        block_model.position = block_index
        block_model.block_bid = block_bid
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
        for block in existing_blocks:
            if block.position < block_index:
                blocks_history.append(HistoryInfo(bid=block.block_bid, id=block.id))
                continue

            if block.position == block_index:
                blocks_history.append(
                    HistoryInfo(bid=block_model.block_bid, id=block_model.id)
                )
                continue

            if block.position >= block_index:
                new_block = block.clone()
                new_block.position = block.position + 1
                new_block.updated_at = time
                new_block.updated_user_bid = user_id
                new_block.deleted = 0
                db.session.add(new_block)
                db.session.flush()
                blocks_history.append(
                    HistoryInfo(bid=new_block.block_bid, id=new_block.id)
                )

        save_blocks_history(app, user_id, outline.shifu_bid, outline_id, blocks_history)
        db.session.commit()
        return generate_block_dto_from_model_internal(block_model)


@extension("delete_block_list")
def delete_block_list(
    result, app, user_id: str, outline_id: str, block_list: list[dict]
) -> bool:
    with app.app_context():
        app.logger.info(f"delete block list: {outline_id}, {block_list}")
