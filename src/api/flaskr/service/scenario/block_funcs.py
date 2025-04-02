import re
import json
from flaskr.service.scenario.dtos import (
    BlockDto,
    SolidContentDto,
    AIDto,
    ButtonDto,
    TextInputDto,
    CodeDto,
    PhoneDto,
    LoginDto,
    GotoDto,
    PaymentDto,
    OptionDto,
    GotoSettings,
    GotoDtoItem,
    OutlineEditDto,
    SystemPromptDto,
)
from flaskr.service.scenario.adapter import (
    convert_dict_to_block_dto,
    update_block_model,
)
from flaskr.service.lesson.models import AILesson, AILessonScript
from flaskr.service.lesson.const import (
    SCRIPT_TYPE_FIX,
    SCRIPT_TYPE_PORMPT,
    SCRIPT_TYPE_SYSTEM,
    UI_TYPE_BUTTON,
    UI_TYPE_INPUT,
    UI_TYPE_CONTINUED,
    UI_TYPE_TO_PAY,
    UI_TYPE_SELECTION,
    UI_TYPE_PHONE,
    UI_TYPE_CHECKCODE,
    UI_TYPE_LOGIN,
    UI_TYPE_BRANCH,
)
from flaskr.service.common.models import raise_error
from flaskr.util import generate_id
from flaskr.dao import db
from datetime import datetime


def get_profiles(profiles: str):

    profiles = re.findall(r"\[(.*?)\]", profiles)
    return profiles


def generate_block_dto(block: AILessonScript):
    ret = BlockDto(
        block_id=block.script_id,
        block_no=block.script_index,
        block_name=block.script_name,
        block_desc=block.script_desc,
        block_type=block.script_type,
        block_index=block.script_index,
    )
    if block.script_type == SCRIPT_TYPE_FIX:
        ret.block_content = SolidContentDto(
            block.script_prompt, get_profiles(block.script_profile)
        )
    elif block.script_type == SCRIPT_TYPE_PORMPT:
        ret.block_content = AIDto(
            prompt=block.script_prompt,
            profiles=get_profiles(block.script_profile),
            model=block.script_model,
            temprature=block.script_temprature,
            other_conf=block.script_other_conf,
        )
    elif block.script_type == SCRIPT_TYPE_SYSTEM:
        ret.block_content = SystemPromptDto(
            prompt=block.script_prompt,
            profiles=get_profiles(block.script_profile),
            model=block.script_model,
            temprature=block.script_temprature,
            other_conf=block.script_other_conf,
        )
    if block.script_ui_type == UI_TYPE_BUTTON:
        ret.block_ui = ButtonDto(block.script_ui_content, block.script_ui_content)
    elif block.script_ui_type == UI_TYPE_INPUT:
        prompt = AIDto(
            prompt=block.script_check_prompt,
            profiles=get_profiles(block.script_ui_profile),
            model=block.script_model,
            temprature=block.script_temprature,
            other_conf=block.script_other_conf,
        )
        ret.block_ui = TextInputDto(
            text_input_name=block.script_ui_content,
            text_input_key=block.script_ui_content,
            text_input_placeholder=block.script_ui_content,
            prompt=prompt,
        )
    elif block.script_ui_type == UI_TYPE_CHECKCODE:
        ret.block_ui = CodeDto(
            text_input_name=block.script_ui_content,
            text_input_key=block.script_ui_content,
            text_input_placeholder=block.script_ui_content,
        )
    elif block.script_ui_type == UI_TYPE_PHONE:
        ret.block_ui = PhoneDto(
            text_input_name=block.script_ui_content,
            text_input_key=block.script_ui_content,
            text_input_placeholder=block.script_ui_content,
        )
    elif block.script_ui_type == UI_TYPE_LOGIN:
        ret.block_ui = LoginDto(
            button_name=block.script_ui_content, button_key=block.script_ui_content
        )
    elif block.script_ui_type == UI_TYPE_BRANCH:
        json_data = json.loads(block.script_other_conf)
        profile_key = json_data.get("var_name")
        items = []
        for item in json_data.get("jump_rule"):
            items.append(
                GotoDtoItem(
                    value=item.get("value"),
                    type="outline",
                    goto_id=item.get("lark_table_id"),
                )
            )

        ret.block_ui = GotoDto(
            button_name=block.script_ui_content,
            button_key=block.script_ui_content,
            goto_settings=GotoSettings(items=items, profile_key=profile_key),
        )
    elif block.script_ui_type == UI_TYPE_CONTINUED:
        ret.block_ui = None
    elif block.script_ui_type == UI_TYPE_TO_PAY:
        ret.block_ui = PaymentDto(block.script_ui_content, block.script_ui_content)
    elif block.script_ui_type == UI_TYPE_SELECTION:
        json_data = json.loads(block.script_other_conf)
        profile_key = json_data.get("var_name")
        items = []
        for item in json_data.get("btns"):
            items.append(
                ButtonDto(button_name=item.get("label"), button_key=item.get("value"))
            )
        ret.block_ui = OptionDto(
            block.script_ui_content, block.script_ui_content, profile_key, items
        )
    return ret


def convert_block_dto_to_model(block: BlockDto):
    pass


def get_block_list(app, user_id: str, outline_id: str):
    with app.app_context():
        lesson = AILesson.query.filter(
            AILesson.lesson_id == outline_id,
            AILesson.status == 1,
        ).first()
        if not lesson:
            raise_error("SCENARIO.LESSON_NOT_FOUND")
        # get sub outline list
        sub_outlines = (
            AILesson.query.filter(
                AILesson.status == 1,
                AILesson.course_id == lesson.course_id,
                AILesson.lesson_no.like(lesson.lesson_no + "%"),
            )
            .order_by(AILesson.lesson_no.asc())
            .all()
        )
        sub_outline_ids = [outline.lesson_id for outline in sub_outlines]
        blocks = (
            AILessonScript.query.filter(
                AILessonScript.lesson_id.in_(sub_outline_ids),
                AILessonScript.status == 1,
            )
            .order_by(AILessonScript.script_index.asc())
            .all()
        )

        ret = []
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
                ret.append(generate_block_dto(block))
        return ret
    pass


def save_block(app, user_id: str, outline_id: str, block: BlockDto):
    with app.app_context():
        lesson = AILesson.query.filter(
            AILesson.course_id == outline_id,
            AILesson.status == 1,
        ).first()
        if not lesson:
            raise_error("SCENARIO.LESSON_NOT_FOUND")
        block_model = convert_block_dto_to_model(block)

        db.session.add(block_model)
        db.session.commit()
        return generate_block_dto(block_model)
    pass


def delete_block(app, user_id: str, outline_id: str, block_id: str):
    with app.app_context():
        block = AILessonScript.query.filter(
            AILessonScript.lesson_id == outline_id,
            AILessonScript.status == 1,
            AILessonScript.script_id == block_id,
        ).first()
        if not block:
            raise_error("SCENARIO.BLOCK_NOT_FOUND")
        block.status = 0
        db.session.commit()
        return True
    pass


def get_block(app, user_id: str, outline_id: str, block_id: str):
    with app.app_context():
        block = AILessonScript.query.filter(
            AILessonScript.lesson_id == outline_id,
            AILessonScript.status == 1,
            AILessonScript.script_id == block_id,
        ).first()
        if not block:
            raise_error("SCENARIO.BLOCK_NOT_FOUND")
        return generate_block_dto(block)


# save block list
def save_block_list(app, user_id: str, outline_id: str, block_list: list[BlockDto]):
    with app.app_context():
        outline = AILesson.query.filter(
            AILesson.course_id == outline_id,
            AILesson.status == 1,
        ).first()
        if not outline:
            raise_error("SCENARIO.OUTLINE_NOT_FOUND")

        outline_id = outline.lesson_id

        sub_outlines = (
            AILesson.query.filter(
                AILesson.status == 1,
                AILesson.course_id == outline_id,
                AILesson.lesson_no.like(outline.lesson_no + "%"),
            )
            .order_by(AILesson.lesson_no.asc())
            .all()
        )
        sub_outline_ids = [outline.lesson_id for outline in sub_outlines]

        # get all blocks
        blocks = (
            AILessonScript.query.filter(
                AILessonScript.lesson_id.in_(sub_outline_ids),
                AILessonScript.status == 1,
            )
            .order_by(AILessonScript.script_index.asc())
            .all()
        )
        block_index = 1
        current_outline_id = outline_id
        for block in block_list:
            type = block.get("type")
            if type == "block":
                block_dto = convert_dict_to_block_dto(block)
                block_model = None
                if block_dto.block_id is not None and block_dto.block_id != "":
                    check_block = [
                        b for b in blocks if b.script_id == block_dto.block_id
                    ]
                    if len(check_block) > 0:
                        block_model = check_block[0]
                if block_model is None:
                    block_model = AILessonScript(
                        script_id=generate_id(app),
                        script_index=block_index,
                        script_name=block_dto.block_name,
                        script_desc=block_dto.block_desc,
                        script_type=block_dto.block_type,
                        created=datetime.now(),
                        created_user_id=user_id,
                        updated=datetime.now(),
                        updated_user_id=user_id,
                        status=1,
                    )
                update_block_model(block_model, block_dto)
                block_model.lesson_id = current_outline_id
                block_model.script_index = block_index
                block_model.updated = datetime.now()
                block_model.updated_user_id = user_id
                block_model.status = 1
                db.session.merge(block_model)
                block_index += 1
            elif type == "outline":
                # consider the outline level
                # pass the top outline
                pass
        db.session.commit()
        return [generate_block_dto(block_model) for block_model in block_list]
    pass


# delete block list
def delete_block_list(app, user_id: str, outline_id: str, block_list: list[dict]):
    with app.app_context():
        lesson = AILesson.query.filter(
            AILesson.course_id == outline_id,
            AILesson.status == 1,
        ).first()
        if not lesson:
            raise_error("SCENARIO.LESSON_NOT_FOUND")
        for block in block_list:
            block_model = convert_block_dto_to_model(block)
            db.session.delete(block_model)
        db.session.commit()
        return True
