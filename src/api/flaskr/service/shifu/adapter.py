"""
Shifu adapter

This module contains adapter functions for shifu.

includes:
    - convert html to markdown
    - convert markdown to html
    - convert outline to reorder outline item dto
    - convert block dto to model
    - convert model to block dto

Author: yfge
Date: 2025-08-07
"""

from flaskr.service.shifu.dtos import (
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
from flaskr.i18n import _
from flask import current_app as app

from flaskr.service.lesson.models import (
    AILessonScript,
)
from flaskr.service.profile.dtos import (
    ProfileItemDefinition,
)
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
from .models import DraftBlock, PublishedBlock
from .consts import (
    BLOCK_TYPE_VALUES,
    BLOCK_TYPE_VALUES_REVERSE,
    BLOCK_TYPE_CONTENT,
    BLOCK_TYPE_BUTTON,
    BLOCK_TYPE_INPUT,
    BLOCK_TYPE_OPTIONS,
    BLOCK_TYPE_GOTO,
    BLOCK_TYPE_LOGIN,
    BLOCK_TYPE_PAYMENT,
    BLOCK_TYPE_BREAK,
)

from typing import Union


def html_2_markdown(content: str, variables_in_prompt: list[str]) -> str:
    """
    convert html to markdown
    Args:
        content: The html content to convert
        variables_in_prompt: The variables in prompt
    Returns:
        The markdown content
    """

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


def markdown_2_html(content: str, variables_in_prompt: list[str]) -> str:
    """
    convert markdown to html
    Args:
        content: The markdown content to convert
        variables_in_prompt: The variables in prompt
    Returns:
        The html content
    """

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
    """
    get profiles from string
    Args:
        profiles: The string to get profiles from
    Returns:
        The profiles
    """
    profiles = re.findall(r"\[(.*?)\]", profiles)
    return profiles


def convert_outline_to_reorder_outline_item_dto(
    json_array: list[dict],
) -> ReorderOutlineItemDto:
    """
    convert outline to reorder outline item dto
    Args:
        json_array: The json array to convert
    Returns:
        The reorder outline item dto
    """
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
    """
    convert json object to block dto
    Args:
        json_object: The json object to convert
    Returns:
        The block dto
    """
    type = json_object.get("type")
    if type not in CONTENT_TYPE:
        raise_error(f"Invalid type: {type}")
    return BlockDTO(
        bid=json_object.get("bid", ""),
        block_content=CONTENT_TYPE[type](**json_object.get("properties")),
        variable_bids=json_object.get("variable_bids", []),
        resource_bids=json_object.get("resource_bids", []),
    )


def _get_lang_dict(lang: str) -> dict[str, str]:
    """
    get lang dict
    Args:
        lang: The lang string to get
    Returns:
        The lang dict
    """
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


def generate_block_dto_from_model(
    block_model: AILessonScript,
    variable_definitions: list[ProfileItemDefinition],
) -> list[BlockDTO]:
    """
    deprecated: use generate_block_dto_from_model_internal instead, only used in migration
    Args:
        block_model: The block model to convert
        variable_definitions: The variable definitions to use
    Returns:
        The block dto
    """
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
        if len(variable_bids) == 0:
            variable_names = get_profiles(block_model.script_ui_profile)
            variable_bids = [
                variable_definition.profile_id
                for variable_definition in variable_definitions
                if variable_definition.profile_key in variable_names
            ]
        ret.append(
            BlockDTO(
                bid=block_model.script_id,
                block_content=OptionsDTO(
                    result_variable_bid=(variable_bids[0] if variable_bids else ""),
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


def check_content_block_dto(
    block_dto: BlockDTO,
    variable_definition_map: dict[str, ProfileItemDefinition],
) -> BlockUpdateResultDto:
    """
    check content block dto
    Args:
        block_dto: The block dto to check
        variable_definition_map: The variable definition map
    Returns:
        The block update result dto
    """
    if (
        not block_dto.block_content.content
        or not block_dto.block_content.content.strip()
    ):
        return BlockUpdateResultDto(None, _("SHIFU.PROMPT_REQUIRED"))
    return BlockUpdateResultDto(None, None)


def check_button_block_dto(
    block_dto: BlockDTO,
    variable_definition_map: dict[str, ProfileItemDefinition],
) -> BlockUpdateResultDto:
    """
    check button block dto
    Args:
        block_dto: The block dto to check
        variable_definition_map: The variable definition map
    Returns:
        The block update result dto
    """
    if not block_dto.block_content.label or not block_dto.block_content.label.lang:
        return BlockUpdateResultDto(None, _("SHIFU.BUTTON_LABEL_REQUIRED"))
    return BlockUpdateResultDto(None, None)


def check_input_block_dto(
    block_dto: BlockDTO,
    variable_definition_map: dict[str, ProfileItemDefinition],
) -> BlockUpdateResultDto:
    """
    check input block dto
    Args:
        block_dto: The block dto to check
        variable_definition_map: The variable definition map
    Returns:
        The block update result dto
    """
    content: InputDTO = block_dto.block_content
    if not content.prompt or not content.prompt.strip():
        return BlockUpdateResultDto(None, _("SHIFU.TEXT_INPUT_PROMPT_REQUIRED"))
    if content.result_variable_bids is None or len(content.result_variable_bids) == 0:
        return BlockUpdateResultDto(None, _("SHIFU.RESULT_VARIABLE_BIDS_REQUIRED"))
    if "json" not in content.prompt.strip().lower():
        return BlockUpdateResultDto(None, _("SHIFU.TEXT_INPUT_PROMPT_JSON_REQUIRED"))
    for variable_bid in content.result_variable_bids:
        variable_definition = variable_definition_map.get(variable_bid, None)
        if variable_definition is None:
            return BlockUpdateResultDto(None, _("SHIFU.PROFILE_NOT_FOUND"))
        if variable_definition.profile_key not in content.prompt.strip().lower():
            return BlockUpdateResultDto(
                None, _("SHIFU.TEXT_INPUT_PROMPT_VARIABLE_REQUIRED")
            )
    return BlockUpdateResultDto(None, None)


def check_options_block_dto(
    block_dto: BlockDTO,
    variable_definition_map: dict[str, ProfileItemDefinition],
) -> BlockUpdateResultDto:
    """
    check options block dto
    Args:
        block_dto: The block dto to check
        variable_definition_map: The variable definition map
    Returns:
        The block update result dto
    """
    content: OptionsDTO = block_dto.block_content
    if not content.options or len(content.options) == 0:
        return BlockUpdateResultDto(None, _("SHIFU.OPTIONS_REQUIRED"))
    if block_dto.variable_bids is None or len(block_dto.variable_bids) == 0:
        return BlockUpdateResultDto(None, _("SHIFU.OPTIONS_VARIABLE_BIDS_REQUIRED"))
    if (
        content.result_variable_bid is None
        or content.result_variable_bid not in block_dto.variable_bids
    ):
        return BlockUpdateResultDto(None, _("SHIFU.PROFILE_NOT_FOUND"))
    for option in content.options:
        if not option.value or not option.value.strip():
            return BlockUpdateResultDto(None, _("SHIFU.OPTION_VALUE_REQUIRED"))
        if not option.label or not option.label.lang:
            return BlockUpdateResultDto(None, _("SHIFU.OPTION_LABEL_REQUIRED"))
    return BlockUpdateResultDto(None, None)


def check_goto_block_dto(
    block_dto: BlockDTO,
    variable_definition_map: dict[str, ProfileItemDefinition],
) -> BlockUpdateResultDto:
    """
    Check if the goto block DTO is valid.

    Args:
        block_dto: The goto block DTO to validate
        variable_definition_map: Map of variable definitions

    Returns:
        BlockUpdateResultDto: Result with error message if validation fails
    """

    content: GotoDTO = block_dto.block_content
    if not content.conditions or len(content.conditions) == 0:
        return BlockUpdateResultDto(None, _("SHIFU.GOTO_CONDITIONS_REQUIRED"))
    if block_dto.variable_bids is None or len(block_dto.variable_bids) == 0:
        return BlockUpdateResultDto(None, _("SHIFU.GOTO_VARIABLE_BIDS_REQUIRED"))
    for variable_bid in block_dto.variable_bids:
        variable_definition = variable_definition_map.get(variable_bid, None)
        if variable_definition is None:
            return BlockUpdateResultDto(None, _("SHIFU.PROFILE_NOT_FOUND"))
    return BlockUpdateResultDto(None, None)


def check_login_block_dto(
    block_dto: BlockDTO,
    variable_definition_map: dict[str, ProfileItemDefinition],
) -> BlockUpdateResultDto:
    """
    Check if the login block DTO is valid.

    Args:
        block_dto: The login block DTO to validate
        variable_definition_map: Map of variable definitions

    Returns:
        BlockUpdateResultDto: Result with error message if validation fails
    """
    # Login blocks can rely on default copy when no label is specified.
    return BlockUpdateResultDto(None, None)


def check_payment_block_dto(
    block_dto: BlockDTO,
    variable_definition_map: dict[str, ProfileItemDefinition],
) -> BlockUpdateResultDto:
    """
    Check if the payment block DTO is valid.

    Args:
        block_dto: The payment block DTO to validate
        variable_definition_map: Map of variable definitions

    Returns:
        BlockUpdateResultDto: Result with error message if validation fails
    """
    # Payment blocks can fall back to default copy, so skip label validation.
    return BlockUpdateResultDto(None, None)


def check_break_block_dto(
    block_dto: BlockDTO,
    variable_definition_map: dict[str, ProfileItemDefinition],
) -> BlockUpdateResultDto:
    """
    check break block dto
    Args:
        block_dto: The block dto to check
        variable_definition_map: The variable definition map
    Returns:
        The block update result dto
    """
    return BlockUpdateResultDto(None, None)


def check_block_dto(
    block_dto: BlockDTO,
    variable_definition_map: dict[str, ProfileItemDefinition],
) -> BlockUpdateResultDto:
    """
    check block dto
    Args:
        block_dto: The block dto to check
        variable_definition_map: The variable definition map
    Returns:
        The block update result dto
    """
    func_map = {
        BLOCK_TYPE_CONTENT: check_content_block_dto,
        BLOCK_TYPE_BUTTON: check_button_block_dto,
        BLOCK_TYPE_INPUT: check_input_block_dto,
        BLOCK_TYPE_OPTIONS: check_options_block_dto,
        BLOCK_TYPE_GOTO: check_goto_block_dto,
        BLOCK_TYPE_LOGIN: check_login_block_dto,
        BLOCK_TYPE_PAYMENT: check_payment_block_dto,
        BLOCK_TYPE_BREAK: check_break_block_dto,
    }
    func = func_map.get(block_dto.type, None)
    if func is None:
        raise_error(f"Invalid block type: {block_dto.type}")
    return func(block_dto, variable_definition_map)


def update_block_dto_to_model_internal(
    block_dto: BlockDTO,
    block_model: DraftBlock,
    variable_definitions: list[ProfileItemDefinition],
    new_block: bool = False,
) -> BlockUpdateResultDto:
    """
    update block dto to model
    Args:
        block_dto: The block dto to update
        block_model: The block model to update
        variable_definitions: The variable definitions to use
        new_block: Whether the block is new
    Returns:
        The block update result dto
    """
    block_type = BLOCK_TYPE_VALUES.get(block_dto.type, None)
    if block_type is None:
        raise_error(f"Invalid block type: {block_dto.type}")

    variable_definition_map: dict[str, ProfileItemDefinition] = {
        variable_definition.profile_id: variable_definition
        for variable_definition in variable_definitions
    }
    if not new_block:
        result = check_block_dto(block_dto, variable_definition_map)
        if result.error_message:
            return result

    block_model.type = block_type
    block_model.content = json.dumps(
        block_dto.block_content.__json__(), ensure_ascii=False
    )
    block_model.variable_bids = ",".join(block_dto.variable_bids)
    block_model.resource_bids = ",".join(block_dto.resource_bids)
    if block_dto.type == BLOCK_TYPE_CONTENT:
        content: ContentDTO = block_dto.block_content
        content.content = html_2_markdown(content.content, [])
        block_model.content = json.dumps(
            content.__json__(),
            ensure_ascii=False,
        )
    if block_dto.type == BLOCK_TYPE_INPUT:
        content: InputDTO = block_dto.block_content
        content.prompt = html_2_markdown(content.prompt, [])
        block_model.content = json.dumps(
            content.__json__(),
            ensure_ascii=False,
        )

    return BlockUpdateResultDto(None, None)


def generate_block_dto_from_model_internal(
    block_model: Union[DraftBlock, PublishedBlock],
    convert_html: bool = False,
) -> BlockDTO:
    """
    generate block dto from model
    Args:
        block_model: The block model to generate
        convert_html: Whether to convert html to markdown
    Returns:
        The block dto
    """
    type = BLOCK_TYPE_VALUES_REVERSE.get(block_model.type, None)
    if type is None:
        raise_error(f"Invalid block type: {block_model.type}")
    block_dto = BlockDTO(
        bid=block_model.block_bid,
        block_content=CONTENT_TYPE[type](**json.loads(block_model.content)),
        variable_bids=(
            block_model.variable_bids.split(",") if block_model.variable_bids else []
        ),
        resource_bids=(
            block_model.resource_bids.split(",") if block_model.resource_bids else []
        ),
    )
    if convert_html:
        if block_dto.type == BLOCK_TYPE_CONTENT:
            content: ContentDTO = block_dto.block_content
            content.content = markdown_2_html(content.content, [])
            block_dto.block_content = content
        if block_dto.type == BLOCK_TYPE_INPUT:
            content: InputDTO = block_dto.block_content
            content.prompt = markdown_2_html(content.prompt, [])
            block_dto.block_content = content
    return block_dto
