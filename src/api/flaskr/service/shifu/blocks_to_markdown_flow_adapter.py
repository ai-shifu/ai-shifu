"""
MarkdownFlow adapter

This module contains functions for converting shifu's original structure based on blocks to MarkdownFlow.

Author: yfge
Date: 2025-09-14
"""

import re
from flaskr.service.shifu.dtos import (
    BlockDTO,
    LabelDTO,
    ContentDTO,
    LoginDTO,
    PaymentDTO,
    OptionsDTO,
    InputDTO,
    BreakDTO,
    GotoDTO,
    CheckCodeDTO,
    PhoneDTO,
    ButtonDTO,
)
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_CONTENT,
    BLOCK_TYPE_BREAK,
    BLOCK_TYPE_INPUT,
    BLOCK_TYPE_OPTIONS,
    BLOCK_TYPE_GOTO,
    BLOCK_TYPE_PAYMENT,
    BLOCK_TYPE_LOGIN,
    BLOCK_TYPE_PHONE,
    BLOCK_TYPE_CHECKCODE,
    BLOCK_TYPE_BUTTON,
)
from flaskr.service.common import raise_error
from flaskr.service.shifu.adapter import html_2_markdown


def __convert_label_to_mdflow(label: LabelDTO) -> str:
    if hasattr(label, "lang") and label.lang:
        return label.lang.get("zh-CN", "")
    return ""


def __convert_button_with_value_to_mdflow(label: LabelDTO, value: None | str) -> str:
    """
    Convert button with value or action to MarkdownFlow format
    Args:
        label: The label of the button
        value: The value or action to convert
    Returns:
        The MarkdownFlow format
    """
    if value:
        return f"?[{__convert_label_to_mdflow(label)}//{value}]"
    else:
        return f"?[{__convert_label_to_mdflow(label)}]"


def __convert_login_to_mdflow(login: LoginDTO, variable_map: dict[str, str]) -> str:
    if isinstance(login.label, dict):
        label_dto = LabelDTO(lang=login.label)
    else:
        label_dto = login.label
    return __convert_button_with_value_to_mdflow(label_dto, "login")


def __convert_pay_to_mdflow(payment: PaymentDTO, variable_map: dict[str, str]) -> str:
    if isinstance(payment.label, dict):
        label_dto = LabelDTO(lang=payment.label)
    else:
        label_dto = payment.label
    return __convert_button_with_value_to_mdflow(label_dto, "pay")


def __convert_options_to_mdflow(
    options: OptionsDTO, variable_map: dict[str, str]
) -> str:
    variable_name = variable_map.get(options.result_variable_bid, "")
    option_strings = []
    for option in options.options:
        if isinstance(option, dict):
            label_text = option.get("label", {}).get("zh-CN", "")
            value = option.get("value", "")
        else:
            label_text = __convert_label_to_mdflow(option.label)
            value = option.value
        option_strings.append(f"{label_text}//{value}")

    options_str = "|".join(option_strings)
    return f"?[%{{{{{variable_name}}}}}{options_str}]"


def __convert_input_to_mdflow(input: InputDTO, variable_map: dict[str, str]) -> str:
    if len(input.result_variable_bids) == 0:
        variable_name = "unknown"
    else:
        variable_name = variable_map.get(input.result_variable_bids[0], "")
    placeholder = __convert_label_to_mdflow(input.placeholder)
    return f"?[%{{{{{variable_name}}}}}...{placeholder}]"


def __convert_break_to_mdflow(break_dto: BreakDTO, variable_map: dict[str, str]) -> str:
    if hasattr(break_dto, "label") and break_dto.label:
        return __convert_button_with_value_to_mdflow(break_dto.label, "break")
    else:
        # Create a default label for break
        label_dto = LabelDTO(lang={"zh-CN": "休息"})
        return __convert_button_with_value_to_mdflow(label_dto, "break")


def __convert_content_to_markdownflow(
    content: ContentDTO, variable_map: dict[str, str]
) -> str:
    if content.content is None:
        content_text = ""
    else:
        content_text = html_2_markdown(content.content, [])
        content_text = re.sub(r"\n\s*\n+", "\n\n", content_text)
        content_text = content_text.strip()
    if content.llm_enabled:
        return content_text
    else:
        return f"==={content_text}==="


def __convert_goto_to_mdflow(goto: GotoDTO, variable_map: dict[str, str]) -> str:
    if hasattr(goto, "label") and goto.label:
        return __convert_button_with_value_to_mdflow(goto.label, "goto")
    else:
        # Create a default label for goto
        label_dto = LabelDTO(lang={"zh-CN": "跳转"})
        return __convert_button_with_value_to_mdflow(label_dto, "goto")


def __convert_phone_to_mdflow(phone: PhoneDTO, variable_map: dict[str, str]) -> str:
    if hasattr(phone, "label") and phone.label:
        return __convert_button_with_value_to_mdflow(phone.label, "phone")
    else:
        label_dto = LabelDTO(lang={"zh-CN": "手机验证"})
        return __convert_button_with_value_to_mdflow(label_dto, "phone")


def __convert_checkcode_to_mdflow(
    checkcode: CheckCodeDTO, variable_map: dict[str, str]
) -> str:
    if hasattr(checkcode, "label") and checkcode.label:
        return __convert_button_with_value_to_mdflow(checkcode.label, "checkcode")
    else:
        # Create a default label for checkcode
        label_dto = LabelDTO(lang={"zh-CN": "验证码"})
        return __convert_button_with_value_to_mdflow(label_dto, "checkcode")


def __convert_button_to_mdflow(button: ButtonDTO, variable_map: dict[str, str]) -> str:
    return __convert_button_with_value_to_mdflow(button.label, None)


def convert_block_to_mdflow(block: BlockDTO, variable_map: dict[str, str]) -> str:
    """
    Convert block to MarkdownFlow format
    Args:
        block: The block to convert
        variable_map: The variable map
    Returns:
        The MarkdownFlow format
    """
    if hasattr(block, "type") and block.type:
        block_type = block.type
    else:
        content_class = block.block_content.__class__.__name__
        block_type = content_class.replace("DTO", "").lower()

    convert_func_map = {
        BLOCK_TYPE_CONTENT: __convert_content_to_markdownflow,
        BLOCK_TYPE_BREAK: __convert_break_to_mdflow,
        BLOCK_TYPE_INPUT: __convert_input_to_mdflow,
        BLOCK_TYPE_OPTIONS: __convert_options_to_mdflow,
        BLOCK_TYPE_GOTO: __convert_goto_to_mdflow,
        BLOCK_TYPE_PAYMENT: __convert_pay_to_mdflow,
        BLOCK_TYPE_LOGIN: __convert_login_to_mdflow,
        BLOCK_TYPE_PHONE: __convert_phone_to_mdflow,
        BLOCK_TYPE_CHECKCODE: __convert_checkcode_to_mdflow,
        BLOCK_TYPE_BUTTON: __convert_button_to_mdflow,
    }

    convert_func = convert_func_map.get(block_type, None)
    if convert_func is None:
        raise_error(f"Invalid block type: {block_type} for block: {block.bid}")
    ret = convert_func(block.block_content, variable_map)
    return ret
