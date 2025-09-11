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


def __get_label_markdown_flow(label: LabelDTO) -> str:
    """
    Get the label to display in markdownflow
    """
    if hasattr(label, "lang") and label.lang:
        return label.lang.get("zh-CN", "")
    return ""


def __convert_to_markdown_button(label: LabelDTO, action: None | str) -> str:
    """
    Convert the label to markdownflow format
    """
    if action:
        return f"?[{__get_label_markdown_flow(label)}//{action}]"
    else:
        return f"?[{__get_label_markdown_flow(label)}]"


def __convert_login_to_markdownflow(
    login: LoginDTO, variable_map: dict[str, str]
) -> str:
    """
    Convert login to markdown flow
    """
    # Handle case where login.label is a dict
    if isinstance(login.label, dict):
        label_dto = LabelDTO(lang=login.label)
    else:
        label_dto = login.label
    return __convert_to_markdown_button(label_dto, "login")


def __convert_payment_to_markdownflow(
    payment: PaymentDTO, variable_map: dict[str, str]
) -> str:
    """
    Convert payment to markdown flow
    """
    # Handle case where payment.label is a dict
    if isinstance(payment.label, dict):
        label_dto = LabelDTO(lang=payment.label)
    else:
        label_dto = payment.label
    return __convert_to_markdown_button(label_dto, "pay")


def __convert_options_to_markdownflow(
    options: OptionsDTO, variable_map: dict[str, str]
) -> str:
    """
    Convert options to markdown flow
    """
    variable_name = variable_map.get(options.result_variable_bid, "")
    option_strings = []
    for option in options.options:
        if isinstance(option, dict):
            label_text = option.get("label", {}).get("zh-CN", "")
            value = option.get("value", "")
        else:
            label_text = __get_label_markdown_flow(option.label)
            value = option.value
        option_strings.append(f"{label_text}//{value}")

    options_str = "|".join(option_strings)
    return f"?[%{{{{{variable_name}}}}}{options_str}]"


def __convert_input_to_markdownflow(
    input: InputDTO, variable_map: dict[str, str]
) -> str:
    """
    Convert input to markdown flow
    """
    if len(input.result_variable_bids) == 0:
        variable_name = "unknown"
    else:
        variable_name = variable_map.get(input.result_variable_bids[0], "")
    placeholder = __get_label_markdown_flow(input.placeholder)
    # Input should return action format, not variable format
    return f"?[%{{{{{variable_name}}}}}...{placeholder}]"


def __convert_break_to_markdownflow(
    break_dto: BreakDTO, variable_map: dict[str, str]
) -> str:
    """
    Convert break to markdown flow
    """
    if hasattr(break_dto, "label") and break_dto.label:
        return __convert_to_markdown_button(break_dto.label, "break")
    else:
        # Create a default label for break
        label_dto = LabelDTO(lang={"zh-CN": "休息"})
        return __convert_to_markdown_button(label_dto, "break")


def __convert_content_to_markdownflow(
    content: ContentDTO, variable_map: dict[str, str]
) -> str:
    """
    Convert content to markdown flow
    """
    if content.content is None:
        content_text = ""
    else:
        content_text = html_2_markdown(content.content, [])
        # Remove empty lines (replace multiple consecutive newlines with single newline)

        content_text = re.sub(r"\n\s*\n+", "\n\n", content_text)
        # Remove leading and trailing whitespace
        content_text = content_text.strip()

    if content.llm_enabled:
        return content_text
    else:
        return f"==={content_text}==="


def __convert_goto_to_markdownflow(goto: GotoDTO, variable_map: dict[str, str]) -> str:
    """
    Convert goto to markdown flow
    """
    if hasattr(goto, "label") and goto.label:
        return __convert_to_markdown_button(goto.label, "goto")
    else:
        # Create a default label for goto
        label_dto = LabelDTO(lang={"zh-CN": "跳转"})
        return __convert_to_markdown_button(label_dto, "goto")


def __convert_phone_to_markdownflow(
    phone: PhoneDTO, variable_map: dict[str, str]
) -> str:
    """
    Convert phone input to markdownflow
    """
    if hasattr(phone, "label") and phone.label:
        return __convert_to_markdown_button(phone.label, "phone")
    else:
        # Create a default label for phone
        label_dto = LabelDTO(lang={"zh-CN": "手机验证"})
        return __convert_to_markdown_button(label_dto, "phone")


def __convert_checkcode_to_markdownflow(
    checkcode: CheckCodeDTO, variable_map: dict[str, str]
) -> str:
    """
    Convert checkcode to markdownflow
    """
    if hasattr(checkcode, "label") and checkcode.label:
        return __convert_to_markdown_button(checkcode.label, "checkcode")
    else:
        # Create a default label for checkcode
        label_dto = LabelDTO(lang={"zh-CN": "验证码"})
        return __convert_to_markdown_button(label_dto, "checkcode")


def __convert_button_to_markdownflow(
    button: ButtonDTO, variable_map: dict[str, str]
) -> str:
    """
    Convert button to markdownflow
    """
    return __convert_to_markdown_button(button.label, None)


def convert_block_to_markdownflow(block: BlockDTO, variable_map: dict[str, str]) -> str:
    """
    Convert block to markdownflow
    """
    # Determine block type from content if not present
    if hasattr(block, "type") and block.type:
        block_type = block.type
    else:
        # Infer type from content class name
        content_class = block.block_content.__class__.__name__
        block_type = content_class.replace("DTO", "").lower()

    convert_func_map = {
        BLOCK_TYPE_CONTENT: __convert_content_to_markdownflow,
        BLOCK_TYPE_BREAK: __convert_break_to_markdownflow,
        BLOCK_TYPE_INPUT: __convert_input_to_markdownflow,
        BLOCK_TYPE_OPTIONS: __convert_options_to_markdownflow,
        BLOCK_TYPE_GOTO: __convert_goto_to_markdownflow,
        BLOCK_TYPE_PAYMENT: __convert_payment_to_markdownflow,
        BLOCK_TYPE_LOGIN: __convert_login_to_markdownflow,
        BLOCK_TYPE_PHONE: __convert_phone_to_markdownflow,
        BLOCK_TYPE_CHECKCODE: __convert_checkcode_to_markdownflow,
        BLOCK_TYPE_BUTTON: __convert_button_to_markdownflow,
    }

    convert_func = convert_func_map.get(block_type, None)
    if convert_func is None:
        raise_error(f"Invalid block type: {block_type} for block: {block.bid}")
    ret = convert_func(block.block_content, variable_map)
    return ret
