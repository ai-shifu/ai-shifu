from flaskr.service.scenario.dtos import BlockDto, OutlineEditDto
from flaskr.service.scenario.adapter import (
    convert_dict_to_block_dto,
    update_block_model,
    generate_block_dto,
)
from flaskr.service.lesson.models import AILesson, AILessonScript
from flaskr.service.profile.profile_manage import save_profile_item_defination
from flaskr.service.profile.models import ProfileItem
from flaskr.service.common.models import raise_error
from flaskr.service.scenario.utils import get_existing_blocks
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


def get_block_list(app, user_id: str, outline_id: str):
    with app.app_context():
        lesson = AILesson.query.filter(
            AILesson.lesson_id == outline_id,
            AILesson.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
        ).first()
        if not lesson:
            raise_error("SCENARIO.OUTLINE_NOT_FOUND")
        # get sub outline list
        sub_outlines = (
            AILesson.query.filter(
                AILesson.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
                AILesson.course_id == lesson.course_id,
                AILesson.lesson_no.like(lesson.lesson_no + "%"),
            )
            .order_by(AILesson.lesson_no.asc())
            .all()
        )
        sub_outline_ids = [outline.lesson_id for outline in sub_outlines]
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
            raise_error("SCENARIO.BLOCK_NOT_FOUND")
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
            raise_error("SCENARIO.BLOCK_NOT_FOUND")
        return generate_block_dto(block)


# save block list
def save_block_list(app, user_id: str, outline_id: str, block_list: list[BlockDto]):
    with app.app_context():
        time = datetime.now()
        app.logger.info(f"save_block_list: {outline_id}")
        outline = AILesson.query.filter(
            AILesson.lesson_id == outline_id,
        ).first()
        if not outline:
            raise_error("SCENARIO.OUTLINE_NOT_FOUND")

        # pass the top outline
        if len(outline.lesson_no) == 2:
            return []
        outline_id = outline.lesson_id

        sub_outlines = (
            AILesson.query.filter(
                AILesson.status.in_([STATUS_PUBLISH, STATUS_DRAFT]),
                AILesson.course_id == outline.course_id,
                AILesson.lesson_no.like(outline.lesson_no + "%"),
            )
            .order_by(AILesson.lesson_no.asc())
            .all()
        )
        sub_outline_ids = [outline.lesson_id for outline in sub_outlines]
        app.logger.info(f"sub_outline_ids : {sub_outline_ids}")
        # get all blocks
        blocks = get_existing_blocks(app, sub_outline_ids)
        app.logger.info(f"blocks : {len(blocks)}")
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
                app.logger.info(f"block_dto id : {block_dto.block_id}")
                if block_dto.block_id is not None and block_dto.block_id != "":
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
                    block_models.append(block_model)
                    save_block_ids.append(block_model.script_id)
                else:
                    # update origin block
                    new_block = block_model.clone()
                    old_check_str = block_model.get_str_to_check()
                    profile = update_block_model(new_block, block_dto)
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
    pass


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
            raise_error("SCENARIO.OUTLINE_NOT_FOUND")
        block_dto = convert_dict_to_block_dto({"type": "block", "properties": block})
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
                change_block_status_to_history(new_block, user_id, time)
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
            raise_error("SCENARIO.LESSON_NOT_FOUND")
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
        block = AILessonScript.query.filter(
            AILessonScript.script_id == block_id,
            AILessonScript.status == 1,
        ).first()
        return block


def get_system_block_by_outline_id(app, outline_id: str):
    with app.app_context():
        block = AILessonScript.query.filter(
            AILessonScript.lesson_id == outline_id,
            AILessonScript.status == 1,
            AILessonScript.script_type == SCRIPT_TYPE_SYSTEM,
        ).first()
        if not block:
            outline = AILesson.query.filter(
                AILesson.lesson_id == outline_id,
                AILesson.status == 1,
            ).first()
            if not outline:
                raise_error("SCENARIO.OUTLINE_NOT_FOUND")
        return block
