from flaskr.service.common.aidtos import AIDto, SystemPromptDto
from flaskr.service.shifu.dtos import (
    BlockDto,
    SolidContentDto,
    LoginDto,
    OptionDto,
    TextInputDto,
    ButtonDto,
    GotoDto,
    PhoneDto,
    CodeDto,
    PaymentDto,
    OutlineEditDto,
    GotoDtoItem,
    GotoSettings,
)
from sqlalchemy import func

from flaskr.service.lesson.models import AILessonScript
from flaskr.service.lesson.const import (
    SCRIPT_TYPE_FIX,
    SCRIPT_TYPE_SYSTEM,
    SCRIPT_TYPE_PROMPT,
    UI_TYPE_BUTTON,
    UI_TYPE_LOGIN,
    UI_TYPE_PHONE,
    UI_TYPE_CHECKCODE,
    UI_TYPE_CONTINUED,
    UI_TYPE_SELECTION,
    UI_TYPE_TO_PAY,
    UI_TYPE_BRANCH,
    UI_TYPE_INPUT,
)

from flaskr.service.profile.dtos import (
    TextProfileDto,
    SelectProfileDto,
    ProfileValueDto,
)
from flaskr.service.lesson.models import AILesson
from flaskr.service.profile.models import ProfileItem
import json
from flaskr.service.common import raise_error
import re

# convert block dict to block dto


def convert_dict_to_block_dto(block_dict: dict) -> BlockDto:
    type = block_dict.get("type")
    if type != "block":
        raise_error("SHIFU.INVALID_BLOCK_TYPE")
    block_info = BlockDto(**block_dict.get("properties"))
    block_info.block_ui = None
    block_info.block_content = None
    properties = block_dict.get("properties", {})
    content = properties.get("block_content")
    block_info.block_id = properties.get("block_id")

    if content:
        type = content.get("type")
        if type == "ai":
            block_info.block_content = AIDto(**content.get("properties"))
        elif type == "solidcontent":
            block_info.block_content = SolidContentDto(**content.get("properties"))
        elif type == "systemprompt":
            block_info.block_content = SystemPromptDto(**content.get("properties"))
        else:
            raise_error("SCENARIO.INVALID_BLOCK_CONTENT_TYPE")
    ui = properties.get("block_ui")
    if ui:
        type = ui.get("type")
        if type == "button":
            block_info.block_ui = ButtonDto(**ui.get("properties"))
        elif type == "login":
            block_info.block_ui = LoginDto(**ui.get("properties"))
        elif type == "phone":
            block_info.block_ui = PhoneDto(**ui.get("properties"))
        elif type == "code":
            block_info.block_ui = CodeDto(**ui.get("properties"))
        elif type == "payment":
            block_info.block_ui = PaymentDto(**ui.get("properties"))
        elif type == "goto":
            block_info.block_ui = GotoDto(**ui.get("properties"))
        elif type == "option":
            block_info.block_ui = OptionDto(**ui.get("properties"))
        elif type == "textinput":
            block_info.block_ui = TextInputDto(**ui.get("properties"))
        else:
            raise_error("SHIFU.INVALID_BLOCK_UI_TYPE")

    return block_info


# convert outline dict to outline edit dto
def convert_dict_to_outline_edit_dto(outline_dict: dict) -> OutlineEditDto:
    type = outline_dict.get("type")
    if type != "outline":
        raise_error("SHIFU.INVALID_OUTLINE_TYPE")
    outline_info = OutlineEditDto(**outline_dict.get("properties"))
    return outline_info


def check_button_dto(button_dto: ButtonDto):
    if not button_dto.button_name:
        raise_error("SHIFU.BUTTON_NAME_REQUIRED")
    if not button_dto.button_key:
        raise_error("SHIFU.BUTTON_KEY_REQUIRED")


# update block model
def update_block_model(
    block_model: AILessonScript, block_dto: BlockDto
) -> TextProfileDto | SelectProfileDto | None:
    block_model.script_name = block_dto.block_name
    block_model.script_desc = block_dto.block_desc
    block_model.script_media_url = ""
    block_model.script_check_prompt = ""
    block_model.script_ui_profile = "[]"
    block_model.script_ui_profile_id = ""
    block_model.script_end_action = ""
    block_model.script_other_conf = "{}"
    block_model.script_prompt = ""
    block_model.script_profile = ""
    block_model.script_ui_content = ""
    if block_dto.block_content:
        if isinstance(block_dto.block_content, AIDto):
            block_model.script_type = SCRIPT_TYPE_PROMPT
            block_model.script_prompt = block_dto.block_content.prompt
            if block_dto.block_content.profiles:
                block_model.script_profile = (
                    "[" + "][".join(block_dto.block_content.profiles) + "]"
                )
            if block_dto.block_content.model and block_dto.block_content.model != "":
                block_model.script_model = block_dto.block_content.model
            if (
                block_dto.block_content.temprature
                and block_dto.block_content.temprature != 0
            ):
                block_model.script_temprature = block_dto.block_content.temprature
        elif isinstance(block_dto.block_content, SolidContentDto):
            block_model.script_type = SCRIPT_TYPE_FIX
            block_model.script_prompt = block_dto.block_content.content
        elif isinstance(block_dto.block_content, SystemPromptDto):
            block_model.script_type = SCRIPT_TYPE_SYSTEM
            block_model.script_prompt = block_dto.block_content.prompt
            if block_dto.block_content.profiles:
                block_model.script_profile = (
                    "[" + "][".join(block_dto.block_content.profiles) + "]"
                )
            if block_dto.block_content.model and block_dto.block_content.model != "":
                block_model.script_model = block_dto.block_content.model
            if (
                block_dto.block_content.temprature
                and block_dto.block_content.temprature != 0
            ):
                block_model.script_temprature = block_dto.block_content.temprature
        else:
            raise_error("SHIFU.INVALID_BLOCK_CONTENT_TYPE")
    if block_dto.block_ui:
        if isinstance(block_dto.block_ui, LoginDto):
            check_button_dto(block_dto.block_ui)
            block_model.script_ui_type = UI_TYPE_LOGIN
            block_model.script_ui_content = block_dto.block_ui.button_key
            block_model.script_ui_content = block_dto.block_ui.button_name
        elif isinstance(block_dto.block_ui, PhoneDto):
            block_model.script_ui_type = UI_TYPE_PHONE
            block_model.script_ui_content = block_dto.block_ui.input_key
            block_model.script_ui_content = block_dto.block_ui.input_name
        elif isinstance(block_dto.block_ui, CodeDto):
            block_model.script_ui_type = UI_TYPE_CHECKCODE
            block_model.script_ui_content = block_dto.block_ui.input_key
            block_model.script_ui_content = block_dto.block_ui.input_name
        elif isinstance(block_dto.block_ui, PaymentDto):
            check_button_dto(block_dto.block_ui)
            block_model.script_ui_type = UI_TYPE_TO_PAY
            block_model.script_ui_content = block_dto.block_ui.button_key
            block_model.script_ui_content = block_dto.block_ui.button_name
        elif isinstance(block_dto.block_ui, GotoDto):
            from flask import current_app as app

            app.logger.info(f"GOTODTO block_dto.block_ui: {block_dto.block_ui}")
            block_model.script_ui_type = UI_TYPE_BRANCH
            block_model.script_ui_content = block_dto.block_ui.button_name
            block_model.script_other_conf = json.dumps(
                {
                    "var_name": block_dto.block_ui.goto_settings.profile_key,
                    "jump_type": "slient",
                    "jump_rule": [
                        {
                            "value": item.value,
                            "type": item.type,
                            "goto_id": item.goto_id,
                            "lark_id": item.goto_id,
                        }
                        for item in block_dto.block_ui.goto_settings.items
                    ],
                }
            )
        elif isinstance(block_dto.block_ui, ButtonDto):
            check_button_dto(block_dto.block_ui)
            block_model.script_ui_type = UI_TYPE_BUTTON
            block_model.script_ui_content = block_dto.block_ui.button_key
            block_model.script_ui_content = block_dto.block_ui.button_name

        elif isinstance(block_dto.block_ui, OptionDto):
            if not block_dto.block_ui.option_key:
                raise_error("SHIFU.OPTION_KEY_REQUIRED")
            if not block_dto.block_ui.option_name:
                raise_error("SHIFU.OPTION_NAME_REQUIRED")
            if not block_dto.block_ui.profile_key:
                raise_error("SHIFU.PROFILE_KEY_REQUIRED")
            for btn in block_dto.block_ui.buttons:
                if not btn.button_name:
                    raise_error("SHIFU.BUTTON_NAME_REQUIRED")
                if not btn.button_key:
                    raise_error("SHIFU.BUTTON_KEY_REQUIRED")
            block_model.script_ui_type = UI_TYPE_SELECTION
            block_model.script_ui_content = block_dto.block_ui.option_key
            block_model.script_ui_content = block_dto.block_ui.option_name
            block_model.script_ui_profile = "[" + block_dto.block_ui.profile_key + "]"
            block_model.script_other_conf = json.dumps(
                {
                    "var_name": block_dto.block_ui.option_key,
                    "btns": [
                        {
                            "label": btn.button_name,
                            "value": btn.button_key,
                        }
                        for btn in block_dto.block_ui.buttons
                    ],
                }
            )
            return SelectProfileDto(
                block_dto.block_ui.option_key,
                block_dto.block_ui.option_name,
                [
                    ProfileValueDto(btn.button_name, btn.button_key)
                    for btn in block_dto.block_ui.buttons
                ],
            )
        elif isinstance(block_dto.block_ui, TextInputDto):
            if not block_dto.block_ui.prompt:
                raise_error("SHIFU.PROMPT_REQUIRED")
            if not block_dto.block_ui.input_key:
                raise_error("SHIFU.INPUT_KEY_REQUIRED")
            if not block_dto.block_ui.input_name:
                raise_error("SHIFU.INPUT_NAME_REQUIRED")
            if not block_dto.block_ui.input_placeholder:
                raise_error("SHIFU.INPUT_PLACEHOLDER_REQUIRED")
            from flask import current_app as app

            app.logger.info(f"block_dto.block_ui.prompt: {block_dto.block_ui}")

            block_model.script_ui_type = UI_TYPE_INPUT
            if block_dto.block_ui.input_key:
                block_model.script_ui_content = block_dto.block_ui.input_key
            if block_dto.block_ui.input_name:
                block_model.script_ui_content = block_dto.block_ui.input_name
            if block_dto.block_ui.input_placeholder:
                block_model.script_ui_content = block_dto.block_ui.input_placeholder
            if block_dto.block_ui.prompt:
                block_model.script_check_prompt = block_dto.block_ui.prompt.prompt
            if block_dto.block_ui.prompt.model:
                block_model.script_model = block_dto.block_ui.prompt.model

            block_model.script_ui_profile = (
                "[" + "][".join(block_dto.block_ui.prompt.profiles) + "]"
            )
            return TextProfileDto(
                block_dto.block_ui.input_key,
                block_dto.block_ui.input_name,
                block_dto.block_ui.prompt,
                block_dto.block_ui.input_placeholder,
            )
        else:
            raise_error("SHIFU.INVALID_BLOCK_UI_TYPE")
    else:
        block_model.script_ui_type = UI_TYPE_CONTINUED
    return None


def get_profiles(profiles: str):

    profiles = re.findall(r"\[(.*?)\]", profiles)
    return profiles


def generate_block_dto(block: AILessonScript, profile_items: list[ProfileItem]):
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
        ret.block_type = "solid"
    elif block.script_type == SCRIPT_TYPE_PROMPT:
        ret.block_content = AIDto(
            prompt=block.script_prompt,
            profiles=get_profiles(block.script_profile),
            model=block.script_model,
            temprature=block.script_temprature,
            other_conf=block.script_other_conf,
        )
        ret.block_type = "ai"
    elif block.script_type == SCRIPT_TYPE_SYSTEM:
        ret.block_content = SystemPromptDto(
            prompt=block.script_prompt,
            profiles=get_profiles(block.script_profile),
            model=block.script_model,
            temprature=block.script_temprature,
            other_conf=block.script_other_conf,
        )
        ret.block_type = "system"
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

        profile_items = [
            p for p in profile_items if p.profile_id == block.script_ui_profile_id
        ]
        input_key = block.script_ui_profile.split("[")[1].split("]")[0]
        if len(profile_items) > 0:
            profile_item = profile_items[0]
            prompt.prompt = profile_item.profile_raw_prompt
            input_key = profile_item.profile_key

        ret.block_ui = TextInputDto(
            input_name=block.script_ui_content,
            input_key=input_key,
            input_placeholder=block.script_ui_content,
            prompt=prompt,
        )
    elif block.script_ui_type == UI_TYPE_CHECKCODE:
        ret.block_ui = CodeDto(
            input_name=block.script_ui_content,
            input_key=block.script_ui_content,
            input_placeholder=block.script_ui_content,
        )
    elif block.script_ui_type == UI_TYPE_PHONE:
        ret.block_ui = PhoneDto(
            input_name=block.script_ui_content,
            input_key=block.script_ui_content,
            input_placeholder=block.script_ui_content,
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
            goto_id = item.get("goto_id", None)
            if not goto_id and item.get("lark_table_id", None):
                lesson = AILesson.query.filter(
                    AILesson.lesson_id == block.lesson_id
                ).first()
                course_id = lesson.course_id
                goto_lesson = AILesson.query.filter(
                    AILesson.lesson_feishu_id == item.get("lark_table_id", ""),
                    AILesson.status == 1,
                    AILesson.course_id == course_id,
                    func.length(AILesson.lesson_no) > 2,
                ).first()

                if goto_lesson:
                    from flask import current_app as app

                    app.logger.info(
                        f"migrate lark table id: {item.get('lark_table_id', '')} to goto_id: {goto_lesson.lesson_id}"
                    )
                    goto_id = goto_lesson.lesson_id

            items.append(
                GotoDtoItem(
                    value=item.get("value"),
                    type="outline",
                    goto_id=goto_id,
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
        from flask import current_app as app

        app.logger.info(f"profile_key: {profile_key}")
        app.logger.info(f"items: {items}")
        app.logger.info(f"block.script_ui_content: {block.script_ui_content}")
        ret.block_ui = OptionDto(profile_key, profile_key, profile_key, items)
    return ret
