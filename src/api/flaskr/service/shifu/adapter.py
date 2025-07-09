from flaskr.service.shifu.dtos import (
    OutlineEditDto,
    BlockUpdateResultDto,
    ReorderOutlineItemDto,
    BlockDTO,
    LabelDTO,
    ContentDTO,
    ButtonDTO,
    LoginDTO,
    PaymentDTO,
    OptionsDTO,
    InputDTO,
    BreakDTO,
    GotoDTO,
    CheckCodeDTO,
    PhoneDTO,
)
from flaskr.service.profile.dtos import ProfileItemDefinition
from flaskr.i18n import _
from flask import current_app as app

from flaskr.service.lesson.models import AILessonScript
from flaskr.service.lesson.const import (
    SCRIPT_TYPE_FIX,
    SCRIPT_TYPE_PROMPT,
    SCRIPT_TYPE_ACTION,
    UI_TYPE_BUTTON,
    UI_TYPE_LOGIN,
    UI_TYPE_PHONE,
    UI_TYPE_CHECKCODE,
    UI_TYPE_SELECTION,
    UI_TYPE_TO_PAY,
    UI_TYPE_BRANCH,
    UI_TYPE_INPUT,
    UI_TYPE_CONTENT,
    UI_TYPE_BREAK,
)

import json
from flaskr.service.common import raise_error
from flaskr.util import generate_id
import re


# convert outline dict to outline edit dto
def convert_dict_to_outline_edit_dto(outline_dict: dict) -> OutlineEditDto:
    type = outline_dict.get("type")
    if type != "outline":
        raise_error(_("SHIFU.INVALID_OUTLINE_TYPE"))
    outline_info = OutlineEditDto(**(outline_dict.get("properties") or {}))
    return outline_info


def html_2_markdown(content, variables_in_prompt):
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
        if var not in variables_in_prompt:
            variables_in_prompt.append(var)
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


def markdown_2_html(content, variables_in_prompt):
    import re

    def iframe_repl(match):
        bvid = match.group("bvid")
        title = match.group("title")
        return f'<span data-tag="video" data-url="https://www.bilibili.com/video/{bvid}/" data-title="{title}">{title}</span>'

    def profile_repl(match):
        var = match.group("var")
        if var not in variables_in_prompt:
            variables_in_prompt.append(var)
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


# # update block model
# def update_block_model(
#     block_model: AILessonScript, block_dto: BlockDto, new_block: bool = False
# ) -> BlockUpdateResultDto:
#     block_model.script_name = block_dto.block_name
#     block_model.script_desc = block_dto.block_desc
#     block_model.script_media_url = ""
#     block_model.script_check_prompt = ""
#     block_model.script_ui_profile = "[]"
#     block_model.script_ui_profile_id = ""
#     block_model.script_end_action = ""
#     block_model.script_other_conf = "{}"
#     block_model.script_prompt = ""
#     block_model.script_profile = ""
#     block_model.script_ui_content = ""
#     variables_in_prompt = []
#     if block_dto.block_content:
#         if isinstance(block_dto.block_content, AIDto):
#             block_model.script_type = SCRIPT_TYPE_PROMPT

#             block_model.script_prompt = html_2_markdown(
#                 block_dto.block_content.prompt, variables_in_prompt
#             )
#             if block_dto.block_content.variables:
#                 block_model.script_profile = (
#                     "["
#                     + "][".join(block_dto.block_content.variables + variables_in_prompt)
#                     + "]"
#                 )
#             if block_dto.block_content.model and block_dto.block_content.model != "":
#                 block_model.script_model = block_dto.block_content.model
#             if (
#                 block_dto.block_content.temperature
#                 and block_dto.block_content.temperature != 0
#             ):
#                 block_model.script_temperature = block_dto.block_content.temperature
#         elif isinstance(block_dto.block_content, SolidContentDto):
#             block_model.script_type = SCRIPT_TYPE_FIX
#             block_model.script_prompt = html_2_markdown(
#                 block_dto.block_content.prompt, variables_in_prompt
#             )
#             if block_dto.block_content.variables:
#                 block_model.script_profile = (
#                     "["
#                     + "][".join(block_dto.block_content.variables + variables_in_prompt)
#                     + "]"
#                 )
#         elif isinstance(block_dto.block_content, SystemPromptDto):
#             block_model.script_type = SCRIPT_TYPE_SYSTEM
#             block_model.script_prompt = html_2_markdown(
#                 block_dto.block_content.system_prompt, variables_in_prompt
#             )
#             if block_dto.block_content.variables:
#                 block_model.script_profile = (
#                     "["
#                     + "][".join(block_dto.block_content.variables + variables_in_prompt)
#                     + "]"
#                 )
#             if block_dto.block_content.model and block_dto.block_content.model != "":
#                 block_model.script_model = block_dto.block_content.model
#             if (
#                 block_dto.block_content.temperature
#                 and block_dto.block_content.temperature != 0
#             ):
#                 block_model.script_temperature = block_dto.block_content.temperature
#         else:
#             return BlockUpdateResultDto(None, _("SHIFU.INVALID_BLOCK_CONTENT_TYPE"))
#         if not new_block and (
#             not block_model.script_prompt or not block_model.script_prompt.strip()
#         ):
#             return BlockUpdateResultDto(None, _("SHIFU.PROMPT_REQUIRED"))

#     if block_dto.block_ui:
#         if isinstance(block_dto.block_ui, LoginDto):
#             error_message = check_button_dto(block_dto.block_ui)
#             if error_message:
#                 return BlockUpdateResultDto(None, error_message)
#             block_model.script_ui_type = UI_TYPE_LOGIN
#             block_model.script_ui_content = block_dto.block_ui.button_key
#             block_model.script_ui_content = block_dto.block_ui.button_name
#         elif isinstance(block_dto.block_ui, PhoneDto):
#             block_model.script_ui_type = UI_TYPE_PHONE
#             block_model.script_ui_content = block_dto.block_ui.input_key
#             block_model.script_ui_content = block_dto.block_ui.input_name
#         elif isinstance(block_dto.block_ui, CodeDto):
#             block_model.script_ui_type = UI_TYPE_CHECKCODE
#             block_model.script_ui_content = block_dto.block_ui.input_key
#             block_model.script_ui_content = block_dto.block_ui.input_name
#         elif isinstance(block_dto.block_ui, PaymentDto):
#             error_message = check_button_dto(block_dto.block_ui)
#             if error_message:
#                 return BlockUpdateResultDto(None, error_message)
#             block_model.script_ui_type = UI_TYPE_TO_PAY
#             block_model.script_ui_content = block_dto.block_ui.button_key
#             block_model.script_ui_content = block_dto.block_ui.button_name
#         elif isinstance(block_dto.block_ui, GotoDto):

#             app.logger.info(f"GOTODTO block_dto.block_ui: {block_dto.block_ui}")
#             block_model.script_ui_type = UI_TYPE_BRANCH
#             block_model.script_ui_content = block_dto.block_ui.button_name
#             block_model.script_other_conf = json.dumps(
#                 {
#                     "var_name": block_dto.block_ui.goto_settings.profile_key,
#                     "jump_type": "slient",
#                     "jump_rule": [
#                         {
#                             "value": item.value,
#                             "type": item.type,
#                             "goto_id": item.goto_id,
#                             "lark_id": item.goto_id,
#                         }
#                         for item in block_dto.block_ui.goto_settings.items
#                     ],
#                 }
#             )
#         elif isinstance(block_dto.block_ui, ButtonDto):
#             error_message = check_button_dto(block_dto.block_ui)
#             if error_message:
#                 return BlockUpdateResultDto(None, error_message)
#             block_model.script_ui_type = UI_TYPE_BUTTON
#             block_model.script_ui_content = block_dto.block_ui.button_key
#             block_model.script_ui_content = block_dto.block_ui.button_name
#         elif isinstance(block_dto.block_ui, OptionDto):
#             block_model.script_ui_type = UI_TYPE_SELECTION
#             if not block_dto.block_ui.profile_id:
#                 return BlockUpdateResultDto(None, _("SHIFU.PROFILE_KEY_REQUIRED"))
#             profile_option_info = block_dto.profile_info
#             if not profile_option_info:
#                 return BlockUpdateResultDto(None, _("SHIFU.PROFILE_NOT_FOUND"))
#             for btn in block_dto.block_ui.buttons:
#                 if not btn.button_name:
#                     return BlockUpdateResultDto(None, _("SHIFU.BUTTON_NAME_REQUIRED"))
#                 if not btn.button_key:
#                     return BlockUpdateResultDto(None, _("SHIFU.BUTTON_KEY_REQUIRED"))

#             block_model.script_ui_content = profile_option_info.profile_key
#             block_dto.block_ui.profile_key = profile_option_info.profile_key
#             block_model.script_ui_profile = "[" + block_dto.block_ui.profile_key + "]"

#             block_model.script_ui_profile_id = profile_option_info.profile_id
#             block_dto.block_ui.profile_id = profile_option_info.profile_id
#             block_model.script_other_conf = json.dumps(
#                 {
#                     "var_name": profile_option_info.profile_key,
#                     "btns": [
#                         {
#                             # "label": profile_item_value.name,
#                             # "value": profile_item_value.value,
#                             "label": btn.button_name,
#                             "value": btn.button_key,
#                         }
#                         # for profile_item_value in profile_item_value_list
#                         for btn in block_dto.block_ui.buttons
#                     ],
#                 }
#             )

#             return BlockUpdateResultDto(
#                 SelectProfileDto(
#                     profile_option_info.profile_key,
#                     profile_option_info.profile_key,
#                     [
#                         ProfileValueDto(btn.button_name, btn.button_key)
#                         for btn in block_dto.block_ui.buttons
#                     ],
#                 )
#             )
#         elif isinstance(block_dto.block_ui, TextInputDto):
#             if not block_dto.block_ui.prompt:
#                 return BlockUpdateResultDto(None, _("SHIFU.PROMPT_REQUIRED"))
#             app.logger.info(f"block_dto.block_ui.prompt: {block_dto.block_ui}")
#             block_model.script_ui_type = UI_TYPE_INPUT
#             if not block_dto.block_ui.profile_ids:
#                 return BlockUpdateResultDto(None, _("SHIFU.PROFILE_KEY_REQUIRED"))
#             if len(block_dto.block_ui.profile_ids) != 1:
#                 return BlockUpdateResultDto(None, _("SHIFU.PROFILE_IDS_NOT_CORRECT"))
#             input_profile_info = block_dto.profile_info
#             if not input_profile_info:
#                 return BlockUpdateResultDto(None, _("SHIFU.PROFILE_NOT_FOUND"))
#             input_profile_info.profile_remark = block_dto.block_ui.input_name
#             block_model.script_ui_content = input_profile_info.profile_remark
#             block_model.script_ui_profile_id = input_profile_info.profile_id
#             block_dto.block_ui.input_key = input_profile_info.profile_key
#             # block_dto.block_ui.input_name = input_profile_info.profile_remark
#             block_dto.block_ui.input_placeholder = input_profile_info.profile_remark
#             if (
#                 not block_dto.block_ui.prompt
#                 or not block_dto.block_ui.prompt.prompt
#                 or not block_dto.block_ui.prompt.prompt.strip()
#             ):
#                 return BlockUpdateResultDto(None, _("SHIFU.TEXT_INPUT_PROMPT_REQUIRED"))
#             if "json" not in block_dto.block_ui.prompt.prompt.strip().lower():
#                 return BlockUpdateResultDto(
#                     None, _("SHIFU.TEXT_INPUT_PROMPT_JSON_REQUIRED")
#                 )
#             block_model.script_check_prompt = block_dto.block_ui.prompt.prompt
#             if block_dto.block_ui.prompt.model is not None:
#                 block_model.script_model = block_dto.block_ui.prompt.model

#             block_model.script_ui_profile = (
#                 "[" + "][".join(block_dto.block_ui.prompt.variables) + "]"
#             )
#             return BlockUpdateResultDto(
#                 TextProfileDto(
#                     block_dto.block_ui.input_key,
#                     block_dto.block_ui.input_name,
#                     block_dto.block_ui.prompt,
#                     block_dto.block_ui.input_placeholder,
#                 )
#             )
#         elif isinstance(block_dto.block_ui, EmptyDto):
#             block_model.script_ui_type = UI_TYPE_EMPTY
#         else:
#             return BlockUpdateResultDto(None, _("SHIFU.INVALID_BLOCK_UI_TYPE"))
#     else:
#         block_model.script_ui_type = UI_TYPE_EMPTY
#     return BlockUpdateResultDto(None)


def get_profiles(profiles: str):

    profiles = re.findall(r"\[(.*?)\]", profiles)
    return profiles


# def generate_block_dto(block: AILessonScript, profile_items: list[ProfileItem]):
#     ret = BlockDto(
#         block_id=block.script_id,
#         block_no=block.script_index,
#         block_name=block.script_name,
#         block_desc=block.script_desc,
#         block_type=block.script_type,
#         block_index=block.script_index,
#     )

#     variables_in_prompt = []
#     if block.script_type == SCRIPT_TYPE_FIX:
#         ret.block_content = SolidContentDto(
#             prompt=markdown_2_html(block.script_prompt, variables_in_prompt),
#             variables=get_profiles(block.script_profile) + variables_in_prompt,
#         )
#         ret.block_type = "solid"
#     elif block.script_type == SCRIPT_TYPE_PROMPT:
#         ret.block_content = AIDto(
#             prompt=markdown_2_html(block.script_prompt, variables_in_prompt),
#             variables=get_profiles(block.script_profile) + variables_in_prompt,
#             model=block.script_model,
#             temperature=block.script_temperature,
#             other_conf=block.script_other_conf,
#         )
#         ret.block_type = "ai"
#     elif block.script_type == SCRIPT_TYPE_SYSTEM:
#         ret.block_content = SystemPromptDto(
#             prompt=markdown_2_html(block.script_prompt, variables_in_prompt),
#             variables=get_profiles(block.script_profile) + variables_in_prompt,
#             model=block.script_model,
#             temperature=block.script_temperature,
#             other_conf=block.script_other_conf,
#         )
#         ret.block_type = "system"
#     if block.script_ui_type == UI_TYPE_BUTTON:
#         ret.block_ui = ButtonDto(block.script_ui_content, block.script_ui_content)
#     elif block.script_ui_type == UI_TYPE_INPUT:

#         prompt = AIDto(
#             prompt=block.script_check_prompt,
#             variables=get_profiles(block.script_ui_profile) + variables_in_prompt,
#             model=block.script_model,
#             temperature=block.script_temperature,
#             other_conf=block.script_other_conf,
#         )

#         profile_items = [
#             p for p in profile_items if p.profile_id == block.script_ui_profile_id
#         ]
#         input_key = block.script_ui_profile.split("[")[1].split("]")[0]
#         if len(profile_items) > 0:
#             profile_item = profile_items[0]
#             prompt.prompt = profile_item.profile_raw_prompt
#             input_key = profile_item.profile_key

#         ret.block_ui = TextInputDto(
#             profile_ids=[block.script_ui_profile_id],
#             input_name=block.script_ui_content,
#             input_key=input_key,
#             input_placeholder=block.script_ui_content,
#             prompt=prompt,
#         )
#     elif block.script_ui_type == UI_TYPE_CHECKCODE:
#         ret.block_ui = CodeDto(
#             input_name=block.script_ui_content,
#             input_key=block.script_ui_content,
#             input_placeholder=block.script_ui_content,
#         )
#     elif block.script_ui_type == UI_TYPE_PHONE:
#         ret.block_ui = PhoneDto(
#             input_name=block.script_ui_content,
#             input_key=block.script_ui_content,
#             input_placeholder=block.script_ui_content,
#         )
#     elif block.script_ui_type == UI_TYPE_LOGIN:
#         ret.block_ui = LoginDto(
#             button_name=block.script_ui_content, button_key=block.script_ui_content
#         )
#     elif block.script_ui_type == UI_TYPE_BRANCH:
#         json_data = json.loads(block.script_other_conf)
#         profile_key = json_data.get("var_name")
#         items = []
#         for item in json_data.get("jump_rule"):
#             goto_id = item.get("goto_id", None)
#             if not goto_id and item.get("lark_table_id", None):
#                 lesson = AILesson.query.filter(
#                     AILesson.lesson_id == block.lesson_id
#                 ).first()
#                 course_id = lesson.course_id
#                 goto_lesson = AILesson.query.filter(
#                     AILesson.lesson_feishu_id == item.get("lark_table_id", ""),
#                     AILesson.status == 1,
#                     AILesson.course_id == course_id,
#                     func.length(AILesson.lesson_no) > 2,
#                 ).first()

#                 if goto_lesson:
#                     app.logger.info(
#                         f"migrate lark table id: {item.get('lark_table_id', '')} to goto_id: {goto_lesson.lesson_id}"
#                     )
#                     goto_id = goto_lesson.lesson_id

#             items.append(
#                 GotoDtoItem(
#                     value=item.get("value"),
#                     type="outline",
#                     goto_id=goto_id,
#                 )
#             )
#         ret.block_ui = GotoDto(
#             button_name=block.script_ui_content,
#             button_key=block.script_ui_content,
#             goto_settings=GotoSettings(items=items, profile_key=profile_key),
#         )
#     elif block.script_ui_type == UI_TYPE_EMPTY:
#         ret.block_ui = EmptyDto()
#     elif block.script_ui_type == UI_TYPE_TO_PAY:
#         ret.block_ui = PaymentDto(block.script_ui_content, block.script_ui_content)
#     elif block.script_ui_type == UI_TYPE_SELECTION:
#         json_data = json.loads(block.script_other_conf)
#         profile_key = json_data.get("var_name")
#         items = []
#         for item in json_data.get("btns", []):
#             items.append(
#                 ButtonDto(button_name=item.get("label"), button_key=item.get("value"))
#             )
#         app.logger.info(f"profile_key: {profile_key}")
#         app.logger.info(f"items: {items}")
#         app.logger.info(f"block.script_ui_content: {block.script_ui_content}")
#         ret.block_ui = OptionDto(
#             block.script_ui_profile_id, profile_key, profile_key, profile_key, items
#         )
#     elif block.script_ui_type == UI_TYPE_EMPTY:
#         ret.block_ui = EmptyDto()
#     return ret


def convert_outline_to_reorder_outline_item_dto(
    json_array: list[dict],
) -> ReorderOutlineItemDto:
    return [
        ReorderOutlineItemDto(
            bid=item.get("bid"),
            children=convert_outline_to_reorder_outline_item_dto(
                item.get("children", [])
            ),
        )
        for item in json_array
    ]


CONTENT_TYPE = {
    "content": ContentDTO,
    "label": LabelDTO,
    "button": ButtonDTO,
    "login": LoginDTO,
    "payment": PaymentDTO,
    "options": OptionsDTO,
    "input": InputDTO,
    "break": BreakDTO,
    "checkcode": CheckCodeDTO,
    "phone": PhoneDTO,
    "goto": GotoDTO,
}


def convert_to_blockDTO(json_object: dict) -> BlockDTO:
    type = json_object.get("type")
    if type not in CONTENT_TYPE:
        raise_error(f"Invalid type: {type}")
    return BlockDTO(
        bid=json_object.get("bid", ""),
        block_content=CONTENT_TYPE[type](**json_object.get("properties")),
        variable_bids=json_object.get("variable_bids", []),
        resource_bids=json_object.get("resource_bids", []),
    )


def _get_label_lang(label) -> LabelDTO:
    # get label from label.lang
    if isinstance(label, dict):
        return LabelDTO(lang=label)
    if label.startswith("{"):
        return LabelDTO(lang=json.loads(label))
    return LabelDTO(
        lang={
            "zh-CN": label,
            "en-US": label,
        }
    )


def _get_lang_dict(lang: str) -> dict[str, str]:
    from flask import current_app

    current_app.logger.info(f"lang: {lang} {type(lang)}")
    if isinstance(lang, dict):
        return lang
    if lang.startswith("{"):
        return json.loads(lang)
    return {
        "zh-CN": lang,
        "en-US": lang,
    }


def update_block_dto_to_model(
    block_dto: BlockDTO,
    block_model: AILessonScript,
    variable_definition_map: dict[str, ProfileItemDefinition],
) -> BlockUpdateResultDto:

    variables = []
    block_model.script_ui_profile_id = ",".join(block_dto.variable_bids)

    if block_dto.type == "content":
        raw_content = html_2_markdown(block_dto.block_content.content, variables)
        block_model.script_ui_type = UI_TYPE_CONTENT
        content: ContentDTO = block_dto.block_content  # type: ContentDTO
        block_model.script_prompt = raw_content
        block_model.script_profile = "[" + "][".join(variables) + "]"
        block_model.script_model = content.llm
        block_model.script_temperature = content.llm_temperature
        if content.llm_enabled:
            block_model.script_type = SCRIPT_TYPE_PROMPT
        else:
            block_model.script_type = SCRIPT_TYPE_FIX
        return BlockUpdateResultDto(None, None)
    block_model.script_type = SCRIPT_TYPE_ACTION
    if block_dto.type == "break":
        block_model.script_ui_type = UI_TYPE_BREAK
        return BlockUpdateResultDto(None, None)
    if block_dto.type == "button":
        block_model.script_ui_type = UI_TYPE_BUTTON
        content: ButtonDTO = block_dto.block_content  # type: ButtonDTO
        block_model.script_ui_content = json.dumps(content.label.lang)

        return BlockUpdateResultDto(None, None)

    if block_dto.type == "login":
        block_model.script_ui_type = UI_TYPE_LOGIN
        content: LoginDTO = block_dto.block_content  # type: LoginDTO
        block_model.script_ui_content = json.dumps(content.label.lang)
        return BlockUpdateResultDto(None, None)

    if block_dto.type == "payment":
        block_model.script_ui_type = UI_TYPE_TO_PAY
        content: PaymentDTO = block_dto.block_content  # type: PaymentDTO
        block_model.script_ui_content = json.dumps(content.label.lang)
        return BlockUpdateResultDto(None, None)

    if block_dto.type == "options":
        block_model.script_type = SCRIPT_TYPE_ACTION
        block_model.script_ui_type = UI_TYPE_SELECTION
        content: OptionsDTO = block_dto.block_content  # type: OptionsDTO
        block_model.script_ui_content = content.result_variable_bid
        variable_definition = variable_definition_map.get(
            content.result_variable_bid if content.result_variable_bid else "",
            None,
        )
        block_model.script_other_conf = json.dumps(
            {
                "var_name": (
                    variable_definition.profile_key if variable_definition else ""
                ),
                "btns": [
                    {
                        "label": content.label.lang,
                        "value": content.value,
                    }
                    for content in content.options
                ],
            }
        )
        return BlockUpdateResultDto(None, None)

    if block_dto.type == "input":
        block_model.script_ui_type = UI_TYPE_INPUT
        content: InputDTO = block_dto.block_content  # type: InputDTO
        block_model.script_ui_content = json.dumps(content.placeholder.lang)

        block_model.script_check_prompt = content.prompt
        block_model.script_model = content.llm
        block_model.script_temperature = content.llm_temperature
        variable_definition = variable_definition_map.get(
            (
                block_dto.variable_bids[0]
                if block_dto.variable_bids and len(block_dto.variable_bids) > 0
                else ""
            ),
            None,
        )
        block_model.script_ui_profile_id = (
            variable_definition.profile_id if variable_definition else ""
        )
        return BlockUpdateResultDto(None, None)
    if block_dto.type == "goto":
        variable_definition = variable_definition_map.get(
            (
                block_dto.variable_bids[0]
                if block_dto.variable_bids and len(block_dto.variable_bids) > 0
                else ""
            ),
            None,
        )
        block_model.script_ui_type = UI_TYPE_BRANCH
        content: GotoDTO = block_dto.block_content
        block_model.script_ui_content = ""
        block_model.script_other_conf = json.dumps(
            {
                "var_name": (
                    variable_definition.profile_key if variable_definition else ""
                ),
                "jump_rule": [
                    {
                        "goto_id": content.destination_bid,
                        "value": content.value,
                        "type": content.destination_type,
                    }
                    for content in content.conditions
                ],
            }
        )
        return BlockUpdateResultDto(None, None)

    if block_dto.type == "break":
        block_model.script_ui_type = UI_TYPE_BREAK
        return BlockUpdateResultDto(None, None)
    return BlockUpdateResultDto(None, None)


def generate_block_dto_from_model(
    block_model: AILessonScript, variable_bids: list[str]
) -> list[BlockDTO]:

    from flask import current_app

    current_app.logger.info(f"block_model: {block_model.script_ui_content}")
    ret = []

    if block_model.script_ui_profile_id:
        variable_bids = block_model.script_ui_profile_id.split(",")
    else:
        variable_bids = []

    variables_in_prompt = []
    if (
        block_model.script_type == SCRIPT_TYPE_FIX
        or block_model.script_type == SCRIPT_TYPE_PROMPT
    ):
        html_content = markdown_2_html(block_model.script_prompt, variables_in_prompt)
        ret.append(
            BlockDTO(
                bid=block_model.script_id,
                block_content=ContentDTO(
                    content=html_content,
                    llm_enabled=block_model.script_type == SCRIPT_TYPE_PROMPT,
                    llm_temperature=block_model.script_temperature,
                ),
                variable_bids=variable_bids,
                resource_bids=[],
            )
        )

    elif block_model.script_type == SCRIPT_TYPE_ACTION:
        pass

    if block_model.script_ui_type == UI_TYPE_CONTENT:
        pass
    elif block_model.script_ui_type == UI_TYPE_BREAK:
        ret.append(
            BlockDTO(
                bid=block_model.script_id,
                block_content=BreakDTO(),
                variable_bids=variable_bids,
                resource_bids=[],
            )
        )
    elif block_model.script_ui_type == UI_TYPE_BUTTON:
        ret.append(
            BlockDTO(
                bid=block_model.script_id,
                block_content=ButtonDTO(
                    label=_get_lang_dict(block_model.script_ui_content),
                ),
                variable_bids=variable_bids,
                resource_bids=[],
            )
        )
    elif block_model.script_ui_type == UI_TYPE_INPUT:
        ret.append(
            BlockDTO(
                bid=block_model.script_id,
                block_content=InputDTO(
                    placeholder=_get_lang_dict(block_model.script_ui_content),
                    result_variable_bids=variable_bids,
                    prompt=block_model.script_check_prompt,
                    llm="",
                    llm_temperature=0.0,
                ),
                variable_bids=variable_bids,
                resource_bids=[],
            )
        )
    elif block_model.script_ui_type == UI_TYPE_CHECKCODE:
        ret.append(
            BlockDTO(
                bid=block_model.script_id,
                block_content=CheckCodeDTO(
                    placeholder=_get_lang_dict(block_model.script_ui_content),
                ),
                variable_bids=variable_bids,
                resource_bids=[],
            )
        )
    elif block_model.script_ui_type == UI_TYPE_PHONE:
        ret.append(
            BlockDTO(
                bid=block_model.script_id,
                block_content=PhoneDTO(
                    placeholder=_get_lang_dict(block_model.script_ui_content),
                ),
                variable_bids=variable_bids,
                resource_bids=[],
            )
        )
    elif block_model.script_ui_type == UI_TYPE_LOGIN:
        ret.append(
            BlockDTO(
                bid=block_model.script_id,
                block_content=LoginDTO(
                    label=_get_lang_dict(block_model.script_ui_content),
                ),
                variable_bids=variable_bids,
                resource_bids=[],
            )
        )
    elif block_model.script_ui_type == UI_TYPE_TO_PAY:
        ret.append(
            BlockDTO(
                bid=block_model.script_id,
                block_content=PaymentDTO(
                    label=_get_lang_dict(block_model.script_ui_content),
                ),
                variable_bids=variable_bids,
                resource_bids=[],
            )
        )
    elif block_model.script_ui_type == UI_TYPE_BRANCH:
        ret.append(
            BlockDTO(
                bid=block_model.script_id,
                block_content=GotoDTO(
                    conditions=[
                        {
                            "destination_bid": content.get("goto_id", ""),
                            "value": content.get("value", ""),
                            "destination_type": content.get("type", ""),
                        }
                        for content in json.loads(block_model.script_other_conf).get(
                            "jump_rule", []
                        )
                    ],
                ),
                variable_bids=variable_bids,
                resource_bids=[],
            )
        )
    elif block_model.script_ui_type == UI_TYPE_SELECTION:
        ret.append(
            BlockDTO(
                bid=block_model.script_id,
                block_content=OptionsDTO(
                    result_variable_bid=block_model.script_ui_profile_id,
                    options=[
                        {
                            "label": _get_lang_dict(content.get("label", "")),
                            "value": content.get("value", ""),
                        }
                        for content in json.loads(block_model.script_other_conf).get(
                            "btns", []
                        )
                    ],
                ),
                variable_bids=variable_bids,
                resource_bids=[],
            )
        )
    if len(ret) > 1:
        ret[1].bid = generate_id(app)

    return ret
