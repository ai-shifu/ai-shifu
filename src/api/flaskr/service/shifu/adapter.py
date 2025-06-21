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
    EmptyDto,
    BlockUpdateResultDto,
)
from sqlalchemy import func
from flaskr.i18n import _
from flask import current_app as app

from flaskr.service.lesson.models import AILessonScript
from flaskr.service.lesson.const import (
    SCRIPT_TYPE_FIX,
    SCRIPT_TYPE_SYSTEM,
    SCRIPT_TYPE_PROMPT,
    UI_TYPE_BUTTON,
    UI_TYPE_LOGIN,
    UI_TYPE_PHONE,
    UI_TYPE_CHECKCODE,
    UI_TYPE_SELECTION,
    UI_TYPE_TO_PAY,
    UI_TYPE_BRANCH,
    UI_TYPE_INPUT,
    UI_TYPE_EMPTY,
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
        raise_error(_("SHIFU.INVALID_BLOCK_TYPE"))
    block_info = BlockDto(**(block_dict.get("properties") or {}))
    block_info.block_ui = None
    block_info.block_content = None
    properties = block_dict.get("properties", {})
    content = properties.get("block_content")
    block_info.block_id = properties.get("block_id")

    if content:
        type = content.get("type")
        if type == "ai":
            block_info.block_content = AIDto(**(content.get("properties") or {}))
        elif type == "solidcontent":
            block_info.block_content = SolidContentDto(
                **(content.get("properties") or {})
            )
        elif type == "systemprompt":
            block_info.block_content = SystemPromptDto(
                **(content.get("properties") or {})
            )
        else:
            raise_error(_("SHIFU.INVALID_BLOCK_CONTENT_TYPE"))
    ui = properties.get("block_ui")
    if ui:
        type = ui.get("type")
        if type == "button":
            block_info.block_ui = ButtonDto(**(ui.get("properties") or {}))
        elif type == "login":
            block_info.block_ui = LoginDto(**(ui.get("properties") or {}))
        elif type == "phone":
            block_info.block_ui = PhoneDto(**(ui.get("properties") or {}))
        elif type == "code":
            block_info.block_ui = CodeDto(**(ui.get("properties") or {}))
        elif type == "payment":
            block_info.block_ui = PaymentDto(**(ui.get("properties") or {}))
        elif type == "goto":
            block_info.block_ui = GotoDto(**(ui.get("properties") or {}))
        elif type == "option":
            block_info.block_ui = OptionDto(**(ui.get("properties") or {}))
        elif type == "textinput":
            block_info.block_ui = TextInputDto(**(ui.get("properties") or {}))
        elif type == "empty":
            block_info.block_ui = EmptyDto()
        else:
            raise_error(_("SHIFU.INVALID_BLOCK_UI_TYPE"))

    return block_info


# convert outline dict to outline edit dto
def convert_dict_to_outline_edit_dto(outline_dict: dict) -> OutlineEditDto:
    type = outline_dict.get("type")
    if type != "outline":
        raise_error(_("SHIFU.INVALID_OUTLINE_TYPE"))
    outline_info = OutlineEditDto(**(outline_dict.get("properties") or {}))
    return outline_info


def check_button_dto(button_dto: ButtonDto):
    # The button title is allowed to be empty
    pass


def html_2_markdown(content):
    def video_repl(match):
        url = match.group("url")
        title = match.group("title")
        bvid_match = re.search(r"BV\w+", url)
        if bvid_match:
            bvid = bvid_match.group(0)
            return f'<iframe src="https://player.bilibili.com/player.html?isOutside=true&bvid={bvid}&p=1&high_quality=1" title="{title}" scrolling="no" border="0" frameborder="no" framespacing="0" allowfullscreen="true"></iframe>'  # noqa: E501 E261
        return url

    def profile_repl(match):
        var = match.group("var")
        var = var.strip("{}")
        return f"{{{var}}}"

    def image_repl(match):
        title = match.group("title")
        url = match.group("url")
        scale = match.group("scale")
        return f"<img src='{url}' alt='{title}' style='width: {scale}%;' />"

    content = re.sub(
        r'<span\s+data-tag="video"[^>]*data-url="(?P<url>[^"]+)"[^>]*data-title="(?P<title>[^"]+)"[^>]*>[^<]*</span>',
        video_repl,
        content,
    )
    content = re.sub(
        r'<span\s+data-tag="profile"[^>]*>(?P<var>\{[^}]+\})</span>',
        profile_repl,
        content,
    )
    content = re.sub(
        r'<span\s+data-tag="image"[^>]*data-url="(?P<url>[^"]+)"[^>]*data-title="(?P<title>[^"]+)"[^>]*data-scale="(?P<scale>[^"]+)"[^>]*>[^<]*</span>',
        image_repl,
        content,
    )

    return content


def markdown_2_html(content):
    import re

    def iframe_repl(match):
        bvid = match.group("bvid")
        title = match.group("title")
        return f'<span data-tag="video" data-url="https://www.bilibili.com/video/{bvid}/" data-title="{title}">{title}</span>'

    def profile_repl(match):
        var = match.group("var")
        return f'<span data-tag="profile">{{{var}}}</span>'

    def image_repl(match):
        title = match.group("title")
        url = match.group("url")
        scale = match.group("scale")
        return f'<span data-tag="image" data-url="{url}" data-title="{title}" data-scale="{scale}">{title}</span>'

    content = re.sub(
        r'(?s)<iframe[^>]*src="[^"]*bvid=(?P<bvid>BV\w+)[^"]*"[^>]*title="(?P<title>[^"]*)"[^>]*></iframe>',
        iframe_repl,
        content,
    )

    content = re.sub(
        r"{(?P<var>[^}]+)}",
        profile_repl,
        content,
    )

    content = re.sub(
        r'<img[^>]*?src=[\'"](?P<url>[^\'"]+)[\'"][^>]*?alt=[\'"](?P<title>[^\'"]+)[\'"][^>]*?style=[\'"][^>]*?width:\s*(?P<scale>[^%;\s]+)[%;][^>]*?(?:/>|>)',
        image_repl,
        content,
    )

    app.logger.info(f"content: {content}")
    return content


# update block model
def update_block_model(
    block_model: AILessonScript, block_dto: BlockDto, new_block: bool = False
) -> BlockUpdateResultDto:
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
            block_model.script_prompt = html_2_markdown(block_dto.block_content.prompt)
            if block_dto.block_content.profiles:
                block_model.script_profile = (
                    "[" + "][".join(block_dto.block_content.profiles) + "]"
                )
            if block_dto.block_content.model and block_dto.block_content.model != "":
                block_model.script_model = block_dto.block_content.model
            if (
                block_dto.block_content.temperature
                and block_dto.block_content.temperature != 0
            ):
                block_model.script_temperature = block_dto.block_content.temperature
        elif isinstance(block_dto.block_content, SolidContentDto):
            block_model.script_type = SCRIPT_TYPE_FIX
            block_model.script_prompt = html_2_markdown(block_dto.block_content.prompt)
        elif isinstance(block_dto.block_content, SystemPromptDto):
            block_model.script_type = SCRIPT_TYPE_SYSTEM
            block_model.script_prompt = html_2_markdown(block_dto.block_content.prompt)
            if block_dto.block_content.profiles:
                block_model.script_profile = (
                    "[" + "][".join(block_dto.block_content.profiles) + "]"
                )
            if block_dto.block_content.model and block_dto.block_content.model != "":
                block_model.script_model = block_dto.block_content.model
            if (
                block_dto.block_content.temperature
                and block_dto.block_content.temperature != 0
            ):
                block_model.script_temperature = block_dto.block_content.temperature
        else:
            return BlockUpdateResultDto(None, _("SHIFU.INVALID_BLOCK_CONTENT_TYPE"))
        if not new_block and (
            not block_model.script_prompt or not block_model.script_prompt.strip()
        ):
            return BlockUpdateResultDto(None, _("SHIFU.PROMPT_REQUIRED"))

    if block_dto.block_ui:
        if isinstance(block_dto.block_ui, LoginDto):
            error_message = check_button_dto(block_dto.block_ui)
            if error_message:
                return BlockUpdateResultDto(None, error_message)
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
            error_message = check_button_dto(block_dto.block_ui)
            if error_message:
                return BlockUpdateResultDto(None, error_message)
            block_model.script_ui_type = UI_TYPE_TO_PAY
            block_model.script_ui_content = block_dto.block_ui.button_key
            block_model.script_ui_content = block_dto.block_ui.button_name
        elif isinstance(block_dto.block_ui, GotoDto):

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
            error_message = check_button_dto(block_dto.block_ui)
            if error_message:
                return BlockUpdateResultDto(None, error_message)
            block_model.script_ui_type = UI_TYPE_BUTTON
            block_model.script_ui_content = block_dto.block_ui.button_key
            block_model.script_ui_content = block_dto.block_ui.button_name
        elif isinstance(block_dto.block_ui, OptionDto):
            block_model.script_ui_type = UI_TYPE_SELECTION
            if not block_dto.block_ui.profile_id:
                return BlockUpdateResultDto(None, _("SHIFU.PROFILE_KEY_REQUIRED"))
            profile_option_info = block_dto.profile_info
            if not profile_option_info:
                return BlockUpdateResultDto(None, _("SHIFU.PROFILE_NOT_FOUND"))
            # if profile_option_info.info.profile_type != PROFILE_TYPE_INPUT_SELECT:
            #     return BlockUpdateResultDto(None, _("SHIFU.PROFILE_TYPE_NOT_MATCH"))
            # if not block_dto.block_ui.option_key:
            #     return BlockUpdateResultDto(None, _("SHIFU.OPTION_KEY_REQUIRED"))
            # if not block_dto.block_ui.option_name:
            #     return BlockUpdateResultDto(None, _("SHIFU.OPTION_NAME_REQUIRED"))
            # if not block_dto.block_ui.profile_key:
            #     return BlockUpdateResultDto(None, _("SHIFU.PROFILE_KEY_REQUIRED"))
            for btn in block_dto.block_ui.buttons:
                if not btn.button_name:
                    return BlockUpdateResultDto(None, _("SHIFU.BUTTON_NAME_REQUIRED"))
                if not btn.button_key:
                    return BlockUpdateResultDto(None, _("SHIFU.BUTTON_KEY_REQUIRED"))

            # block_model.script_ui_content = block_dto.block_ui.option_key
            # block_model.script_ui_content = block_dto.block_ui.option_name
            block_model.script_ui_content = profile_option_info.profile_key
            block_dto.block_ui.profile_key = profile_option_info.profile_key
            block_model.script_ui_profile = "[" + block_dto.block_ui.profile_key + "]"

            # block_model.script_ui_content = profile_option_info.info.profile_key
            block_model.script_ui_profile_id = profile_option_info.profile_id
            block_dto.block_ui.profile_id = profile_option_info.profile_id
            # block_model.script_ui_profile = (
            #     "[" + profile_option_info.info.profile_key + "]"
            # )
            # profile_item_value_list = profile_option_info.list
            block_model.script_other_conf = json.dumps(
                {
                    "var_name": profile_option_info.profile_key,
                    "btns": [
                        {
                            # "label": profile_item_value.name,
                            # "value": profile_item_value.value,
                            "label": btn.button_name,
                            "value": btn.button_key,
                        }
                        # for profile_item_value in profile_item_value_list
                        for btn in block_dto.block_ui.buttons
                    ],
                }
            )

            # buttons = [
            #     ButtonDto(
            #         button_name=profile_item_value.name,
            #         button_key=profile_item_value.value,
            #     )
            #     for profile_item_value in profile_item_value_list
            # ]

            # block_dto.block_ui.buttons = buttons
            return BlockUpdateResultDto(
                SelectProfileDto(
                    profile_option_info.profile_key,
                    profile_option_info.profile_key,
                    [
                        ProfileValueDto(btn.button_name, btn.button_key)
                        for btn in block_dto.block_ui.buttons
                        # ProfileValueDto(
                        #     profile_item_value.name, profile_item_value.value
                        # )
                        # for profile_item_value in profile_item_value_list
                    ],
                )
            )
        elif isinstance(block_dto.block_ui, TextInputDto):
            if not block_dto.block_ui.prompt:
                return BlockUpdateResultDto(None, _("SHIFU.PROMPT_REQUIRED"))
            app.logger.info(f"block_dto.block_ui.prompt: {block_dto.block_ui}")
            block_model.script_ui_type = UI_TYPE_INPUT
            if not block_dto.block_ui.profile_ids:
                return BlockUpdateResultDto(None, _("SHIFU.PROFILE_KEY_REQUIRED"))
            if len(block_dto.block_ui.profile_ids) != 1:
                return BlockUpdateResultDto(None, _("SHIFU.PROFILE_IDS_NOT_CORRECT"))
            input_profile_info = block_dto.profile_info
            if not input_profile_info:
                return BlockUpdateResultDto(None, _("SHIFU.PROFILE_NOT_FOUND"))
            block_model.script_ui_content = input_profile_info.profile_remark
            block_model.script_ui_profile_id = input_profile_info.profile_id
            block_dto.block_ui.input_key = input_profile_info.profile_key
            block_dto.block_ui.input_name = input_profile_info.profile_remark
            block_dto.block_ui.input_placeholder = input_profile_info.profile_remark
            if (
                not block_dto.block_ui.prompt
                or not block_dto.block_ui.prompt.prompt
                or not block_dto.block_ui.prompt.prompt.strip()
            ):
                return BlockUpdateResultDto(None, _("SHIFU.TEXT_INPUT_PROMPT_REQUIRED"))
            if "json" not in block_dto.block_ui.prompt.prompt.strip().lower():
                return BlockUpdateResultDto(
                    None, _("SHIFU.TEXT_INPUT_PROMPT_JSON_REQUIRED")
                )
            block_model.script_check_prompt = block_dto.block_ui.prompt.prompt
            if block_dto.block_ui.prompt.model:
                block_model.script_model = block_dto.block_ui.prompt.model

            block_model.script_ui_profile = (
                "[" + "][".join(block_dto.block_ui.prompt.profiles) + "]"
            )
            return BlockUpdateResultDto(
                TextProfileDto(
                    block_dto.block_ui.input_key,
                    block_dto.block_ui.input_name,
                    block_dto.block_ui.prompt,
                    block_dto.block_ui.input_placeholder,
                )
            )
        elif isinstance(block_dto.block_ui, EmptyDto):
            block_model.script_ui_type = UI_TYPE_EMPTY
        else:
            return BlockUpdateResultDto(None, _("SHIFU.INVALID_BLOCK_UI_TYPE"))
    else:
        block_model.script_ui_type = UI_TYPE_EMPTY
    return BlockUpdateResultDto(None)


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
            prompt=markdown_2_html(block.script_prompt),
            profiles=get_profiles(block.script_profile),
        )
        ret.block_type = "solid"
    elif block.script_type == SCRIPT_TYPE_PROMPT:
        ret.block_content = AIDto(
            prompt=markdown_2_html(block.script_prompt),
            profiles=get_profiles(block.script_profile),
            model=block.script_model,
            temperature=block.script_temperature,
            other_conf=block.script_other_conf,
        )
        ret.block_type = "ai"
    elif block.script_type == SCRIPT_TYPE_SYSTEM:
        ret.block_content = SystemPromptDto(
            prompt=markdown_2_html(block.script_prompt),
            profiles=get_profiles(block.script_profile),
            model=block.script_model,
            temperature=block.script_temperature,
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
            temperature=block.script_temperature,
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
            profile_ids=[block.script_ui_profile_id],
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
    elif block.script_ui_type == UI_TYPE_EMPTY:
        ret.block_ui = EmptyDto()
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
        app.logger.info(f"profile_key: {profile_key}")
        app.logger.info(f"items: {items}")
        app.logger.info(f"block.script_ui_content: {block.script_ui_content}")
        ret.block_ui = OptionDto(
            block.script_ui_profile_id, profile_key, profile_key, profile_key, items
        )
    elif block.script_ui_type == UI_TYPE_EMPTY:
        ret.block_ui = EmptyDto()
    return ret
