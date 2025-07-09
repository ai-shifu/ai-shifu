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


def get_profiles(profiles: str):

    profiles = re.findall(r"\[(.*?)\]", profiles)
    return profiles


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

    if isinstance(lang, dict):
        return lang
    if lang.startswith("{"):
        try:
            return json.loads(lang)
        except Exception:
            return {
                "zh-CN": lang,
                "en-US": lang,
            }
    return {
        "zh-CN": lang,
        "en-US": lang,
    }


def update_block_dto_to_model(
    block_dto: BlockDTO,
    block_model: AILessonScript,
    variable_definitions: list[ProfileItemDefinition],
    new_block: bool = False,
) -> BlockUpdateResultDto:

    variables = []
    block_model.script_ui_profile_id = ",".join(block_dto.variable_bids)
    variable_definition_map = {
        variable_definition.profile_id: variable_definition
        for variable_definition in variable_definitions
    }

    if block_dto.type == "content":
        if not new_block and (
            not block_dto.block_content.content
            or not block_dto.block_content.content.strip()
        ):
            return BlockUpdateResultDto(None, _("SHIFU.PROMPT_REQUIRED"))

        raw_content = html_2_markdown(block_dto.block_content.content, variables)
        block_model.script_ui_type = UI_TYPE_CONTENT
        content: ContentDTO = block_dto.block_content  # type: ContentDTO

        block_model.script_prompt = raw_content
        block_model.script_profile = "[" + "][".join(variables) + "]"
        block_model.script_model = content.llm
        block_model.script_ui_profile = "[" + "][".join(variables) + "]"
        block_model.script_temperature = content.llm_temperature
        if content.llm_enabled:
            block_model.script_type = SCRIPT_TYPE_PROMPT
        else:
            block_model.script_type = SCRIPT_TYPE_FIX
        if block_dto.variable_bids:
            block_model.script_ui_profile_id = ",".join(block_dto.variable_bids)
        else:
            block_model.script_ui_profile_id = ",".join(
                [
                    variable_definition.profile_id
                    for variable_definition in variable_definitions
                    if variable_definition.profile_key in variables
                ]
            )
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
        if (not new_block) and variable_definition is None:
            return BlockUpdateResultDto(None, _("SHIFU.PROFILE_NOT_FOUND"))
        if (not new_block) and (not content.options or not content.options):
            return BlockUpdateResultDto(None, _("SHIFU.OPTIONS_REQUIRED"))

        if not new_block:
            for option in content.options:
                if not option.label or not option.label.lang:
                    return BlockUpdateResultDto(None, _("SHIFU.OPTION_NAME_REQUIRED"))
                if not option.value:
                    return BlockUpdateResultDto(None, _("SHIFU.OPTION_VALUE_REQUIRED"))

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
        block_model.script_ui_profile = (
            "[" + variable_definition.profile_key if variable_definition else "" + "]"
        )
        return BlockUpdateResultDto(None, None)

    if block_dto.type == "input":

        block_model.script_ui_type = UI_TYPE_INPUT
        content: InputDTO = block_dto.block_content  # type: InputDTO
        if (not new_block) and (not content.prompt or not content.prompt.strip()):
            return BlockUpdateResultDto(None, _("SHIFU.TEXT_INPUT_PROMPT_REQUIRED"))
        if (not new_block) and (
            content.result_variable_bids is None
            or len(content.result_variable_bids) == 0
        ):
            return BlockUpdateResultDto(None, "SHIFU.RESULT_VARIABLE_BIDS_REQUIRED")
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

        if (not new_block) and ("json" not in content.prompt.strip().lower()):
            return BlockUpdateResultDto(
                None, _("SHIFU.TEXT_INPUT_PROMPT_JSON_REQUIRED")
            )
        if (not new_block) and (
            variable_definition.profile_key not in content.prompt.strip().lower()
        ):
            return BlockUpdateResultDto(
                None, _("SHIFU.TEXT_INPUT_PROMPT_VARIABLE_REQUIRED")
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
        if not new_block and variable_definition is None:
            return BlockUpdateResultDto(None, _("SHIFU.PROFILE_NOT_FOUND"))
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
                        "goto_id": condition.destination_bid,
                        "value": condition.value,
                        "type": condition.destination_type,
                    }
                    for condition in content.conditions
                ],
            }
        )
        return BlockUpdateResultDto(None, None)

    return BlockUpdateResultDto(None, None)


def generate_block_dto_from_model(
    block_model: AILessonScript, variable_definitions: list[ProfileItemDefinition]
) -> list[BlockDTO]:

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
        variable_bids.extend(
            [
                variable_definition.profile_id
                for variable_definition in variable_definitions
                if variable_definition.profile_key in variables_in_prompt
            ]
        )
        variable_bids = list(set(variable_bids))
        ret.append(
            BlockDTO(
                bid=block_model.script_id,
                block_content=ContentDTO(
                    content=html_content,
                    llm=block_model.script_model,
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
        if len(variable_bids) == 0:
            variable_name = get_profiles(block_model.script_ui_profile)
            variable_bids = [
                variable_definition.profile_id
                for variable_definition in variable_definitions
                if variable_definition.profile_key == variable_name
            ]

        ret.append(
            BlockDTO(
                bid=block_model.script_id,
                block_content=InputDTO(
                    placeholder=_get_lang_dict(block_model.script_ui_content),
                    result_variable_bids=variable_bids,
                    prompt=block_model.script_check_prompt,
                    llm=block_model.script_model,
                    llm_temperature=block_model.script_temperature,
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
        if len(variable_bids) == 0:
            variable_name = get_profiles(block_model.script_ui_profile)
            variable_bids = [
                variable_definition.profile_id
                for variable_definition in variable_definitions
                if variable_definition.profile_key == variable_name
            ]
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
