from flask import Flask

from flaskr.service.learn.const import INPUT_TYPE_CHECKCODE
from flaskr.service.learn.plugin import (
    register_shifu_output_handler,
)
from flaskr.service.learn.utils import check_phone_number, get_script_ui_label
from flaskr.service.user.common import send_sms_code_without_check
from flaskr.service.learn.dtos import ScriptDTO
from flaskr.service.user.models import User
from flaskr.i18n import _
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.shifu.adapter import BlockDTO
from langfuse.client import StatefulTraceClient
from flaskr.service.shifu.dtos import CheckCodeDTO


@register_shifu_output_handler("checkcode")
def _handle_output_checkcode(
    app: Flask,
    user_info: User,
    attend_id: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
    is_preview: bool = False,
) -> ScriptDTO:
    checkcode: CheckCodeDTO = block_dto.block_content
    if check_phone_number(app, user_info, checkcode.phone):
        expires = send_sms_code_without_check(app, user_info, checkcode.phone)
        expires["content"] = _("COMMON.CHECKCODE")
        return ScriptDTO(
            INPUT_TYPE_CHECKCODE,
            expires,
            outline_item_info.bid,
            block_dto.bid,
        )
    else:
        app.logger.info(
            "handle_input_checkcode input is not phone number:" + checkcode.phone
        )
        msg = get_script_ui_label(app, checkcode.label)
        if not msg:
            msg = _("COMMON.CHECKCODE")
        return ScriptDTO(
            INPUT_TYPE_CHECKCODE,
            msg,
            outline_item_info.bid,
            block_dto.bid,
        )
