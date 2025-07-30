from flask import Flask
from flaskr.service.study.plugin import (
    register_shifu_output_handler,
)
from flaskr.service.study.dtos import ScriptDTO
from flaskr.service.user.models import User
from flaskr.service.study.utils import get_script_ui_label
from flaskr.i18n import _
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.shifu.adapter import BlockDTO
from langfuse.client import StatefulTraceClient
from flaskr.service.shifu.dtos import InputDTO


@register_shifu_output_handler("input")
def _handle_output_text(
    app: Flask,
    user_info: User,
    attend_id: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
):
    inputDto: InputDTO = block_dto.block_content
    msg = get_script_ui_label(app, inputDto.placeholder)
    if not msg:
        msg = _("COMMON.INPUT")
    return ScriptDTO(
        "input",
        {"content": msg},
        outline_item_info.bid,
        outline_item_info.bid,
    )
