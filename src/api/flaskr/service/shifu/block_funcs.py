from flaskr.service.shifu.dtos import (
    SaveBlockListResultDto,
    BlockDTO,
    OptionsDTO,
    InputDTO,
)
from flaskr.service.shifu.adapter import (
    convert_to_blockDTO,
    update_block_dto_to_model,
    generate_block_dto_from_model,
)
from flaskr.service.lesson.models import AILesson, AILessonScript
from flaskr.service.profile.profile_manage import (
    save_profile_item_defination,
    get_profile_item_definition_list,
)
from flaskr.service.profile.models import ProfileItem
from flaskr.service.common.models import raise_error
from flaskr.service.shifu.utils import (
    get_existing_blocks,
    get_original_outline_tree,
    change_block_status_to_history,
    mark_block_to_delete,
)
from flaskr.util import generate_id
from flaskr.dao import db
from datetime import datetime
from flaskr.service.lesson.const import (
    SCRIPT_TYPE_SYSTEM,
    STATUS_PUBLISH,
    STATUS_DRAFT,
    STATUS_DELETE,
)
from flaskr.service.check_risk.funcs import check_text_with_risk_control
import queue
from flaskr.dao import redis_client


def get_block_list(app, user_id: str, outline_id: str) -> list[BlockDTO]:
    with app.app_context():
        lesson = AILesson.query.filter(
            AILesson.lesson_id == outline_id,
            AILesson.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
        ).first()
        if not lesson:
            raise_error("SHIFU.OUTLINE_NOT_FOUND")
        tree = get_original_outline_tree(app, lesson.course_id)

        q = queue.Queue()
        for node in tree:
            q.put(node)
        sub_outline_ids = []
        find_outline = False
        sub_outlines = []
        while not q.empty():
            node = q.get()
            if node.outline_id == outline_id:
                find_outline = True
                q.queue.clear()
            if find_outline:
                sub_outline_ids.append(node.outline_id)
                sub_outlines.append(node.outline)
            if node.children and len(node.children) > 0:
                for child in node.children:
                    q.put(child)
        # get sub outline list
        app.logger.info(f"sub_outline_ids : {sub_outline_ids}")
        blocks = get_existing_blocks(app, sub_outline_ids)
        ret = []
        app.logger.info(f"blocks : {len(blocks)}")
        variable_definitions = get_profile_item_definition_list(app, lesson.course_id)
        for sub_outline in sub_outlines:

            lesson_blocks = sorted(
                [b for b in blocks if b.lesson_id == sub_outline.lesson_id],
                key=lambda x: x.script_index,
            )
            for block in lesson_blocks:
                ret.extend(
                    block_dto
                    for block_dto in generate_block_dto_from_model(
                        block, variable_definitions
                    )
                )
        return ret
    pass


def delete_block(app, user_id: str, outline_id: str, block_id: str):
    with app.app_context():
        block = (
            AILessonScript.query.filter(
                AILessonScript.lesson_id == outline_id,
                AILessonScript.status.in_([STATUS_DRAFT, STATUS_PUBLISH]),
                AILessonScript.script_id == block_id,
            )
            .order_by(AILessonScript.id.desc())
            .first()
        )
        if not block:
            raise_error("SHIFU.BLOCK_NOT_FOUND")
        mark_block_to_delete(block, user_id, datetime.now())
        db.session.commit()
        return True
    pass


def get_block(app, user_id: str, outline_id: str, block_id: str) -> BlockDTO:
    with app.app_context():
        block = AILessonScript.query.filter(
            AILessonScript.lesson_id == outline_id,
            AILessonScript.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
            AILessonScript.script_id == block_id,
        ).first()
        if not block:
            raise_error("SHIFU.BLOCK_NOT_FOUND")
        return generate_block_dto_from_model(block, [])[0]


# save block list
def save_block_list_internal(
    app, user_id: str, outline_id: str, block_list: list[BlockDTO]
) -> SaveBlockListResultDto:
    with app.app_context():
        time = datetime.now()
        app.logger.info(f"save_block_list: {outline_id}")
        outline = AILesson.query.filter(
            AILesson.lesson_id == outline_id,
        ).first()
        if not outline:
            raise_error("SHIFU.OUTLINE_NOT_FOUND")

        # pass the top outline
        if len(outline.lesson_no) == 2:
            return SaveBlockListResultDto([], {})
        outline_id = outline.lesson_id

        tree = get_original_outline_tree(app, outline.course_id)

        q = queue.Queue()
        for node in tree:
            q.put(node)
        sub_outline_ids = []
        find_outline = False
        sub_outlines = []
        while not q.empty():
            node = q.get()
            if node.outline_id == outline_id:
                find_outline = True
                q.queue.clear()
            if find_outline:
                sub_outline_ids.append(node.outline_id)
                sub_outlines.append(node.outline)
            if node.children and len(node.children) > 0:
                for child in node.children:
                    q.put(child)
        # get all blocks
        blocks = get_existing_blocks(app, sub_outline_ids)
        variable_definitions = get_profile_item_definition_list(app, outline.course_id)
        block_index = 1
        current_outline_id = outline_id
        block_models = []
        save_block_ids = []
        profile_items = []
        error_messages = {}
        for block in block_list:
            block_dto: BlockDTO = convert_to_blockDTO(block)
            block_model: AILessonScript = None
            block_id = generate_id(app)
            app.logger.info(f"block_dto id : {block_dto.bid}")
            if block_dto.bid is not None and block_dto.bid != "":
                block_id = block_dto.bid
                check_block = next(
                    (b for b in blocks if b.script_id == block_dto.bid), None
                )
                if check_block:
                    block_model = check_block
                else:
                    app.logger.warning(f"block_dto id not found : {block_dto.bid}")

            if block_model is None:
                # add new block
                block_model = AILessonScript(
                    script_id=block_id,
                    script_index=block_index,
                    script_name="",
                    script_desc="",
                    script_type=101,
                    lesson_id=current_outline_id,
                    created=time,
                    created_user_id=user_id,
                    updated=time,
                    updated_user_id=user_id,
                    status=STATUS_DRAFT,
                )
                app.logger.info(f"new block : {block_model.script_id}")
                _fetch_profile_info_for_block_dto(app, block_dto)
                update_block_result = update_block_dto_to_model(
                    block_dto, block_model, variable_definitions
                )
                profile = None
                if update_block_result.error_message:
                    error_messages[block_model.script_id] = (
                        update_block_result.error_message
                    )
                    # Read the original data from the database
                    original_block = (
                        AILessonScript.query.filter(
                            AILessonScript.script_id == block_model.script_id,
                            AILessonScript.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
                        )
                        .order_by(AILessonScript.id.desc())
                        .first()
                    )
                    if original_block:
                        block_model = original_block
                        block_model.script_index = block_index
                        block_model.updated = time
                        block_model.updated_user_id = user_id
                        block_model.status = STATUS_DRAFT
                        db.session.add(block_model)
                        block_models.append(block_model)
                        save_block_ids.append(block_model.script_id)
                        # Continue to execute the subsequent processes using the original data
                        profile = None
                        if original_block.script_ui_profile_id:
                            profile_item = ProfileItem.query.filter(
                                ProfileItem.profile_id
                                == original_block.script_ui_profile_id,
                                ProfileItem.status == 1,
                            ).first()
                            if profile_item:
                                profile_items.append(profile_item)
                if update_block_result.data:
                    profile = update_block_result.data
                    profile_item = save_profile_item_defination(
                        app, user_id, outline.course_id, profile
                    )
                    block_model.script_ui_profile_id = profile_item.profile_id
                    block_model.script_check_prompt = profile_item.profile_prompt
                    profile_items.append(profile_item)
                check_text_with_risk_control(
                    app,
                    block_model.script_id,
                    user_id,
                    block_model.get_str_to_check(),
                )
                block_model.lesson_id = current_outline_id
                block_model.script_index = block_index
                block_model.updated = time
                block_model.updated_user_id = user_id
                block_model.status = STATUS_DRAFT
                db.session.add(block_model)
                app.logger.info(f"new block : {block_model.id}")
                block_models.append(block_model)
                save_block_ids.append(block_model.script_id)

            else:
                # update origin block
                new_block = block_model.clone()
                old_check_str = block_model.get_str_to_check()
                _fetch_profile_info_for_block_dto(app, block_dto)
                update_block_result = update_block_dto_to_model(
                    block_dto, new_block, variable_definitions
                )
                profile = None
                if update_block_result.error_message:
                    error_messages[new_block.script_id] = (
                        update_block_result.error_message
                    )
                    # Read the original data from the database
                    original_block = (
                        AILessonScript.query.filter(
                            AILessonScript.script_id == new_block.script_id,
                            AILessonScript.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
                        )
                        .order_by(AILessonScript.id.desc())
                        .first()
                    )
                    if original_block:
                        new_block = original_block
                        new_block.script_index = block_index
                        new_block.updated = time
                        new_block.updated_user_id = user_id
                        new_block.status = STATUS_DRAFT
                        db.session.add(new_block)
                        block_models.append(new_block)
                        save_block_ids.append(new_block.script_id)
                        # Continue to execute the subsequent processes using the original data
                        profile = None
                        if original_block.script_ui_profile_id:
                            profile_item = ProfileItem.query.filter(
                                ProfileItem.profile_id
                                == original_block.script_ui_profile_id,
                                ProfileItem.status == 1,
                            ).first()
                            if profile_item:
                                profile_items.append(profile_item)
                else:
                    profile = update_block_result.data
                new_block.script_index = block_index
                if profile:
                    profile_item = save_profile_item_defination(
                        app, user_id, outline.course_id, profile
                    )
                    new_block.script_ui_profile_id = profile_item.profile_id
                    new_block.script_check_prompt = profile_item.profile_prompt
                    if profile_item.profile_prompt_model:
                        new_block.script_model = profile_item.profile_prompt_model
                    profile_items.append(profile_item)
                if new_block and not new_block.eq(block_model):
                    # update origin block and save to history
                    new_block.status = STATUS_DRAFT
                    new_block.updated = time
                    new_block.updated_user_id = user_id
                    new_block.script_index = block_index
                    new_block.lesson_id = current_outline_id
                    change_block_status_to_history(block_model, user_id, time)
                    db.session.add(new_block)
                    app.logger.info(f"update block : {new_block.id} {new_block.status}")
                    block_models.append(new_block)
                    new_check_str = new_block.get_str_to_check()
                    if old_check_str != new_check_str:
                        check_text_with_risk_control(
                            app, new_block.script_id, user_id, new_check_str
                        )
                save_block_ids.append(new_block.script_id)
            block_index += 1

        app.logger.info("save block ids : {}".format(save_block_ids))
        for block in blocks:
            if block.script_id not in save_block_ids:
                app.logger.info("delete block : {}".format(block.script_id))
                mark_block_to_delete(block, user_id, time)

        db.session.commit()
        app.logger.info(f"block_models : {block_models}")
        variable_definitions = get_profile_item_definition_list(app, outline.course_id)
        return SaveBlockListResultDto(
            [
                generate_block_dto_from_model(block_model, variable_definitions)[0]
                for block_model in block_models
            ],
            error_messages,
        )


def save_block_list(app, user_id: str, outline_id: str, block_list: list[BlockDTO]):
    timeout = 5 * 60
    blocking_timeout = 1
    lock_key = app.config.get("REDIS_KEY_PREFIX") + ":save_block_list:" + outline_id
    lock = redis_client.lock(
        lock_key, timeout=timeout, blocking_timeout=blocking_timeout
    )
    if lock.acquire(blocking=True):
        try:
            return save_block_list_internal(app, user_id, outline_id, block_list)
        except Exception as e:
            import traceback

            app.logger.error(traceback.format_exc())
            app.logger.error(e)
        finally:
            lock.release()
        return
    else:

        app.logger.error("lockfail")
        return SaveBlockListResultDto([], {})
    return


def add_block(
    app, user_id: str, outline_id: str, block: dict, block_index: int
) -> BlockDTO:
    with app.app_context():
        time = datetime.now()
        outline = (
            AILesson.query.filter(
                AILesson.lesson_id == outline_id,
                AILesson.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
            )
            .order_by(AILesson.lesson_no.asc())
            .first()
        )
        if not outline:
            raise_error("SHIFU.OUTLINE_NOT_FOUND")
        block_dto = convert_to_blockDTO(block)
        # add 1 to the block index / 1 is the index of the block in the outline
        block_index = block_index + 1
        block_model = AILessonScript(
            script_id=generate_id(app),
            script_index=block_index,
            script_name="",
            script_desc="",
            created=time,
            created_user_id=user_id,
            updated=time,
            updated_user_id=user_id,
            status=STATUS_DRAFT,
        )
        variable_definitions = get_profile_item_definition_list(app, outline.course_id)
        update_block_result = update_block_dto_to_model(
            block_dto, block_model, variable_definitions, new_block=True
        )
        if update_block_result.error_message:
            raise_error(update_block_result.error_message)
        check_str = block_model.get_str_to_check()
        check_text_with_risk_control(app, block_model.script_id, user_id, check_str)
        block_model.lesson_id = outline_id
        block_model.script_index = block_index
        block_model.updated = time
        block_model.updated_user_id = user_id
        block_model.status = STATUS_DRAFT
        existing_blocks = get_existing_blocks(app, [outline_id])
        for block in existing_blocks:
            if block.script_index >= block_index:
                new_block = block.clone()
                new_block.script_index = block.script_index + 1
                new_block.updated = time
                new_block.updated_user_id = user_id
                new_block.status = STATUS_DRAFT
                change_block_status_to_history(block, user_id, time)
                db.session.add(new_block)
        db.session.add(block_model)
        db.session.commit()
        return generate_block_dto_from_model(block_model, [])[0]


# delete block list
def delete_block_list(
    app, user_id: str, outline_id: str, block_list: list[dict]
) -> bool:
    with app.app_context():
        lesson = AILesson.query.filter(
            AILesson.lesson_id == outline_id,
            AILesson.status == 1,
        ).first()
        if not lesson:
            raise_error("SHIFU.LESSON_NOT_FOUND")
        for block in block_list:
            block_model = AILessonScript.query.filter(
                AILessonScript.lesson_id == outline_id,
                AILessonScript.status == 1,
                AILessonScript.script_id == block.get("block_id"),
            ).first()
            if block_model:
                block_model.status = STATUS_DELETE
            db.session.commit()
        return True


def get_block_by_id(app, block_id: str) -> AILessonScript:
    with app.app_context():
        block = (
            AILessonScript.query.filter(
                AILessonScript.script_id == block_id,
            )
            .order_by(AILessonScript.id.desc())
            .first()
        )
        return block


def get_system_block_by_outline_id(app, outline_id: str) -> AILessonScript:
    with app.app_context():
        block = (
            AILessonScript.query.filter(
                AILessonScript.lesson_id == outline_id,
                AILessonScript.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
                AILessonScript.script_type == SCRIPT_TYPE_SYSTEM,
            )
            .order_by(AILessonScript.id.desc())
            .first()
        )
        if not block:
            outline = (
                AILesson.query.filter(
                    AILesson.lesson_id == outline_id,
                    AILesson.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
                )
                .order_by(AILesson.id.desc())
                .first()
            )
            if not outline:
                raise_error("SHIFU.OUTLINE_NOT_FOUND")
        return block


def _fetch_profile_info_for_block_dto(app, block_dto: BlockDTO) -> None:
    if (
        isinstance(block_dto.block_content, OptionsDTO)
        and block_dto.block_content.result_variable_bid
    ):
        # block_dto = get_profile_info(app, block_dto.block_content.profile_id)
        pass
    elif (
        isinstance(block_dto.block_content, InputDTO)
        and block_dto.block_content.result_variable_bids
    ):
        if len(block_dto.block_content.result_variable_bids) == 1:
            # block_dto.profile_info = get_profile_info(
            #     app, block_dto.block_content.profile_ids[0]
            # )
            pass
