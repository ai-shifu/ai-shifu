from flaskr.service.scenario.dtos import (
    AIDto,
    BlockDto,
    SystemPromptDto,
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
)

from flaskr.service.lesson.models import AILessonScript
from flaskr.service.lesson.const import (
    SCRIPT_TYPE_FIX,
    SCRIPT_TYPE_SYSTEM,
    SCRIPT_TYPE_PORMPT,
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
import json
from flaskr.service.common import raise_error


def convert_dict_to_block_dto(block_dict: dict) -> BlockDto:
    type = block_dict.get("type")
    if type != "block":
        raise ValueError("Invalid block type")
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
            raise_error("SCENARIO.INVALID_BLOCK_UI_TYPE")

    return block_info


def convert_dict_to_outline_edit_dto(outline_dict: dict) -> OutlineEditDto:
    type = outline_dict.get("type")
    if type != "outline":
        raise ValueError("Invalid outline type")
    outline_info = OutlineEditDto(**outline_dict.get("properties"))
    return outline_info


def update_block_model(block_model: AILessonScript, block_dto: BlockDto):
    block_model.script_name = block_dto.block_name
    block_model.script_desc = block_dto.block_desc
    block_model.script_media_url = ""
    block_model.script_check_prompt = ""
    block_model.script_ui_profile = "[]"
    block_model.script_ui_profile_id = ""
    block_model.script_end_action = ""
    block_model.script_other_conf = "{}"
    if block_dto.block_content:
        if isinstance(block_dto.block_content, AIDto):
            block_model.script_type = SCRIPT_TYPE_PORMPT
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
            from flask import current_app

            current_app.logger.error(
                f"Invalid block content type: {block_dto.block_content} {block_dto.block_content.__class__.__name__}"
            )
    if block_dto.block_ui:
        if isinstance(block_dto.block_ui, ButtonDto):
            block_model.script_ui_type = UI_TYPE_BUTTON
            block_model.script_ui_content = block_dto.block_ui.button_key
            block_model.script_ui_content = block_dto.block_ui.button_name
        elif isinstance(block_dto.block_ui, LoginDto):
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
            block_model.script_ui_type = UI_TYPE_TO_PAY
            block_model.script_ui_content = block_dto.block_ui.input_key
            block_model.script_ui_content = block_dto.block_ui.input_name
        elif isinstance(block_dto.block_ui, GotoDto):
            block_model.script_ui_type = UI_TYPE_BRANCH
            block_model.script_ui_content = block_dto.block_ui.input_name
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
        elif isinstance(block_dto.block_ui, OptionDto):
            block_model.script_ui_type = UI_TYPE_SELECTION
            block_model.script_ui_content = block_dto.block_ui.option_key
            block_model.script_ui_content = block_dto.block_ui.option_name
            block_model.script_ui_profile = "[" + block_dto.block_ui.profile_key + "]"
            block_model.script_other_conf = json.dumps(
                {
                    "var_name": block_dto.block_ui.option_key,
                    "btns": [
                        {
                            "lable": btn.button_name,
                            "key": btn.button_key,
                        }
                        for btn in block_dto.block_ui.buttons
                    ],
                }
            )
        elif isinstance(block_dto.block_ui, TextInputDto):
            block_model.script_ui_type = UI_TYPE_INPUT
            block_model.script_ui_content = block_dto.block_ui.input_key
            block_model.script_ui_content = block_dto.block_ui.input_name
            block_model.script_ui_content = block_dto.block_ui.input_placeholder
            block_model.script_check_prompt = block_dto.block_ui.prompt.prompt
            block_model.script_ui_profile = (
                "[" + "][".join(block_dto.block_ui.prompt.profiles) + "]"
            )
        else:
            raise_error("SCENARIO.INVALID_BLOCK_UI_TYPE")
    else:
        block_model.script_ui_type = UI_TYPE_CONTINUED
