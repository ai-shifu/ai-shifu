from flaskr.service.shifu.dtos import BlockDto, OutlineEditDto
from flaskr.service.shifu.adapter import (
    convert_dict_to_block_dto,
    update_block_model,
    generate_block_dto,
)
from flaskr.service.lesson.models import AILesson, AILessonScript
from flaskr.service.profile.profile_manage import save_profile_item_defination
from flaskr.service.profile.models import ProfileItem
from flaskr.service.common.models import raise_error
from flaskr.service.shifu.utils import get_existing_blocks, get_original_outline_tree
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
from .utils import change_block_status_to_history
import queue
from flaskr.dao import redis_client


def get_block_list(app, user_id: str, outline_id: str):
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

        profile_ids = [b.script_ui_profile_id for b in blocks]
        profile_items = ProfileItem.query.filter(
            ProfileItem.profile_id.in_(profile_ids),
            ProfileItem.status == 1,
        ).all()
        for sub_outline in sub_outlines:
            ret.append(
                OutlineEditDto(
                    outline_id=sub_outline.lesson_id,
                    outline_no=sub_outline.lesson_no,
                    outline_name=sub_outline.lesson_name,
                    outline_desc=sub_outline.lesson_desc,
                    outline_type=sub_outline.lesson_type,
                    # outline_level=len(sub_outline.lesson_no) // 2,
                )
            )
            lesson_blocks = sorted(
                [b for b in blocks if b.lesson_id == sub_outline.lesson_id],
                key=lambda x: x.script_index,
            )
            for block in lesson_blocks:
                ret.append(generate_block_dto(block, profile_items))
        return ret
    pass


def delete_block(app, user_id: str, outline_id: str, block_id: str):
    with app.app_context():
        block = AILessonScript.query.filter(
            AILessonScript.lesson_id == outline_id,
            AILessonScript.status.in_([STATUS_DRAFT]),
            AILessonScript.script_id == block_id,
        ).first()
        if not block:
            block = AILessonScript.query.filter(
                AILessonScript.lesson_id == outline_id,
                AILessonScript.status.in_([STATUS_PUBLISH]),
                AILessonScript.script_id == block_id,
            ).first()
        if not block:
            raise_error("SHIFU.BLOCK_NOT_FOUND")
        change_block_status_to_history(block, user_id, datetime.now())
        db.session.commit()
        return True
    pass


def get_block(app, user_id: str, outline_id: str, block_id: str):
    with app.app_context():
        block = AILessonScript.query.filter(
            AILessonScript.lesson_id == outline_id,
            AILessonScript.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
            AILessonScript.script_id == block_id,
        ).first()
        if not block:
            raise_error("SHIFU.BLOCK_NOT_FOUND")
        return generate_block_dto(block)


# save block list
def save_block_list_internal(
    app, user_id: str, outline_id: str, block_list: list[BlockDto]
):
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
            return []
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
        app.logger.info(f"new sub_outline_ids : {sub_outline_ids}")
        # get all blocks
        blocks = get_existing_blocks(app, sub_outline_ids)
        app.logger.info(f"new blocks : {len(blocks)}")
        block_index = 1
        current_outline_id = outline_id
        block_models = []
        save_block_ids = []
        profile_items = []
        for block in block_list:
            type = block.get("type")
            app.logger.info(f"block type : {type} , {block}")
            if type == "block":
                block_dto = convert_dict_to_block_dto(block)
                block_model = None
                block_id = generate_id(app)
                app.logger.info(f"block_dto id : {block_dto.block_id}")
                if block_dto.block_id is not None and block_dto.block_id != "":
                    block_id = block_dto.block_id
                    check_block = next(
                        (b for b in blocks if b.script_id == block_dto.block_id), None
                    )
                    if check_block:
                        block_model = check_block
                    else:
                        app.logger.warning(
                            f"block_dto id not found : {block_dto.block_id}"
                        )

                if block_model is None:
                    # add new block
                    block_model = AILessonScript(
                        script_id=block_id,
                        script_index=block_index,
                        script_name=block_dto.block_name,
                        script_desc=block_dto.block_desc,
                        script_type=block_dto.block_type,
                        lesson_id=current_outline_id,
                        created=time,
                        created_user_id=user_id,
                        updated=time,
                        updated_user_id=user_id,
                        status=STATUS_DRAFT,
                    )
                    app.logger.info(f"new block : {block_model.script_id}")
                    profile = update_block_model(block_model, block_dto)
                    if profile:
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
                    profile = update_block_model(new_block, block_dto)
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
                        app.logger.info(
                            f"update block : {new_block.id} {new_block.status}"
                        )
                        block_models.append(new_block)
                        new_check_str = new_block.get_str_to_check()
                        if old_check_str != new_check_str:
                            check_text_with_risk_control(
                                app, new_block.script_id, user_id, new_check_str
                            )
                    save_block_ids.append(new_block.script_id)
                block_index += 1
            elif type == "outline":
                # pass the top outline
                pass
        app.logger.info("save block ids : {}".format(save_block_ids))
        for block in blocks:
            if block.script_id not in save_block_ids:
                app.logger.info("delete block : {}".format(block.script_id))
                change_block_status_to_history(block, user_id, time)
        db.session.commit()
        return [
            generate_block_dto(block_model, profile_items)
            for block_model in block_models
        ]


def save_block_list(app, user_id: str, outline_id: str, block_list: list[BlockDto]):
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
            app.logger.error(e)
        finally:
            lock.release()
        return
    else:

        app.logger.error("lockfail")
        return []
    return


def add_block(app, user_id: str, outline_id: str, block: BlockDto, block_index: int):
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
        block_dto = convert_dict_to_block_dto({"type": "block", "properties": block})
        # add 1 to the block index / 1 is the index of the block in the outline
        block_index = block_index + 1
        block_model = AILessonScript(
            script_id=generate_id(app),
            script_index=block_index,
            script_name=block_dto.block_name,
            script_desc=block_dto.block_desc,
            script_type=block_dto.block_type,
            created=time,
            created_user_id=user_id,
            updated=time,
            updated_user_id=user_id,
            status=STATUS_DRAFT,
        )
        update_block_model(block_model, block_dto)
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
        return generate_block_dto(block_model, [])


# delete block list
def delete_block_list(app, user_id: str, outline_id: str, block_list: list[dict]):
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


def get_block_by_id(app, block_id: str):
    with app.app_context():
        block = (
            AILessonScript.query.filter(
                AILessonScript.script_id == block_id,
            )
            .order_by(AILessonScript.id.desc())
            .first()
        )
        return block


def get_system_block_by_outline_id(app, outline_id: str):
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
